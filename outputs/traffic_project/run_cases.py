"""Primary/secondary intersection case studies with left-turn lanes: python run_cases.py"""
import argparse
import copy
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.stats import t as student_t
import torch
from forecast import train, Transformer
from simulation import APPROACHES
import intersection as X
from run import write_csv, dump, COLORS, CONTROLLER_COLORS, CONTROLLERS

ROOT=Path(__file__).resolve().parent
_MODEL_CACHE={}


def with_mode(c,mode):
    c=copy.deepcopy(c); c['intersection']['roads'][0]['left_mode']=mode; return c


def run_seed(job):
    mode,scenario,seed,c,weights=job
    if weights not in _MODEL_CACHE:
        model=Transformer();model.load_state_dict(torch.load(weights,weights_only=True));model.eval();_MODEL_CACHE[weights]=model
    c=with_mode(c,mode); lay=X.Layout(c)
    # Same demand tape for every left mode and controller of a (scenario, seed) pair.
    tape=X.lane_tape(X.scenario_rates(c['duration_s'],scenario,lay),np.random.default_rng(seed),lay)
    detailed=seed==c['seeds'][0]
    results=[(controller,*X.run(tape,controller,scenario,seed,c,_MODEL_CACHE[weights],detailed=detailed)) for controller in CONTROLLERS]
    return mode,scenario,seed,tape,results


def plot_trace(d,title,path):
    trace=d['trace']; channels=d['motion']['layout']['channels']; times=[r['time_s'] for r in trace]
    fig,axes=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained',gridspec_kw=dict(height_ratios=[2,1.4,2]))
    for i,name in enumerate(APPROACHES):
        axes[0].plot(times,[r['queues'][i]+r['boundary'][i] for r in trace],label=name,color=COLORS[i],lw=1.2)
        left=[ch for ch,(a,_,kind) in enumerate(channels) if a==name and kind=='L']
        if left:axes[1].plot(times,[sum(r['lane_inventory'][ch]+r['lane_boundary'][ch] for ch in left) for r in trace],label=f'{name} left lane',color=COLORS[i],lw=1.2)
    axes[0].set_ylabel('Stopped queue + outside [veh]'); axes[0].legend(ncol=4,frameon=False)
    axes[1].set_ylabel('Exclusive left lane\ninventory [veh]')
    if axes[1].lines:axes[1].legend(ncol=2,frameon=False)
    else:axes[1].text(.5,.5,'No exclusive left lanes',transform=axes[1].transAxes,ha='center',color='#6b7378')
    # Signal timeline: one row per movement; green ball/arrow, yellow, and flashing-yellow-arrow (hatched).
    rows=[(i,m) for i in range(4) for m in ('T','L')]
    colors={'G':'#2e9e5b','Y':'#e3b505'}
    for k,(i,m) in enumerate(rows):
        states=[(r['through'] if m=='T' else r['arrow'])[i] for r in trace]
        fya=[m=='L' and r['permissive'][i]=='F' for r in trace]
        for state,color in colors.items():
            spans=_spans(times,[s==state for s in states])
            axes[2].broken_barh(spans,(k-.38,.76),color=color,lw=0)
        axes[2].broken_barh(_spans(times,fya),(k-.38,.76),facecolor='none',edgecolor='#c98b00',hatch='////',lw=0)
    axes[2].set_yticks(range(len(rows)),[f'{APPROACHES[i]} {"through" if m=="T" else "left"}' for i,m in rows])
    axes[2].invert_yaxis(); axes[2].set_xlabel('Simulation time [s]')
    axes[2].legend(handles=[Patch(color=colors['G'],label='Green ball / arrow'),Patch(color=colors['Y'],label='Yellow'),
        Patch(facecolor='none',edgecolor='#c98b00',hatch='////',label='Flashing yellow arrow (permissive)')],ncol=3,frameon=False,loc='upper center',bbox_to_anchor=(.5,-.18))
    for ax in axes:ax.grid(axis='y',color='#e3e7e9',lw=.6); ax.spines[['top','right']].set_visible(False)
    fig.suptitle(title); fig.savefig(path,dpi=140); plt.close(fig)


def _spans(times,mask):
    spans=[]; start=None
    for t,on in zip(times,mask):
        if on and start is None:start=t-1
        if not on and start is not None:spans.append((start,t-1-start)); start=None
    if start is not None:spans.append((start,times[-1]-start))
    return spans


def paired(metrics,mode,scenario,seeds,key):
    rows=[]
    for controller in CONTROLLERS[1:]:
        diff=[]
        for seed in seeds:
            lookup={r['controller']:r[key] for r in metrics if r['left_mode']==mode and r['scenario']==scenario and r['seed']==seed}
            diff.append(lookup[controller]-lookup['fixed'])
        n=len(diff); mean=float(np.mean(diff))
        half=float(student_t.ppf(.975,n-1)*np.std(diff,ddof=1)/np.sqrt(n)) if n>1 else None
        rows.append(dict(left_mode=mode,scenario=scenario,controller=controller,reference='fixed',metric=key,n_pairs=n,mean_difference=mean,
                         ci95_low=None if half is None else mean-half,ci95_high=None if half is None else mean+half))
    return rows


def grouped_bars(ax,groups,series,value,colors,ylabel):
    x=np.arange(len(groups)); width=.8/len(series)
    for j,s in enumerate(series):
        ax.bar(x+(j-(len(series)-1)/2)*width,[value(g,s) for g in groups],width*.92,label=s.replace('_',' '),color=colors[s])
    ax.set_xticks(x,[g.replace('_',' ') for g in groups]); ax.set_ylabel(ylabel)
    ax.grid(axis='y',color='#e3e7e9',lw=.6); ax.set_axisbelow(True); ax.spines[['top','right']].set_visible(False)


def summarize(out,c,metrics,pairs,scores):
    base=c['intersection']['roads'][0]['left_mode']; seeds=c['seeds']
    mean=lambda mode,s,ctl,key:float(np.mean([r[key] for r in metrics if r['left_mode']==mode and r['scenario']==s and r['controller']==ctl]))
    roads=c['intersection']['roads']
    lines=['# Primary/secondary intersection case studies','',
        f'{len(metrics)} intersection runs, {len(seeds)} seeds, {c["duration_s"]} s each. Synthetic demand only; not field validation.','',
        '## Layout','',
        '| Road | Approaches | Lanes (median to curb) | Left mode | Through factor/lane | Left factor | Right factor | Fixed through green [s] |','|---|---|---|---|---:|---:|---:|---:|']
    for road in roads:
        lines.append(f"| {road['name']} | {'/'.join(road['approaches'])} | {' '.join(road['lanes'])} | {road['left_mode']} | {road['through_factor']} | {road['left_factor']} | {road.get('right_factor',0)} | {road.get('fixed_green_s',c['fixed_green_s'])} |")
    lines+=['','Signal: NEMA dual-ring, lead-lead lefts, barrier between the primary and secondary roads. Left arrows run concurrently with the opposing left or with the same-approach through. The flashing yellow arrow is tied to the opposing through green, so the yellow trap cannot occur. Lefts on the secondary road use a shared lane and yield to the opposing through.','',
        f'## Main study (primary left mode: {base})','','### Mean total delay [veh h]','','| Scenario | '+' | '.join(CONTROLLERS)+' |','|---|'+'---:|'*len(CONTROLLERS)]
    for s in c['scenarios']:lines.append(f'| {s} | '+' | '.join(f'{mean(base,s,k,"total_delay_veh_s")/3600:.2f}' for k in CONTROLLERS)+' |')
    lines+=['','### Mean time loss per offered vehicle [s/veh]: left / through / right','',
        'Time loss includes outside waiting and stops at the analysis horizon. Unserved vehicles contribute partial time loss; these are not mean delays of completed trips. Read delay together with throughput and residual demand.','',
        '| Scenario | '+' | '.join(CONTROLLERS)+' |','|---|'+'---|'*len(CONTROLLERS)]
    for s in c['scenarios']:lines.append(f'| {s} | '+' | '.join(f'{mean(base,s,k,"mean_left_delay_s"):.0f} / {mean(base,s,k,"mean_through_delay_s"):.0f} / {mean(base,s,k,"mean_right_delay_s"):.0f}' for k in CONTROLLERS)+' |')
    lines+=['','### Mean stop-line throughput / unserved at horizon [veh]','','| Scenario | '+' | '.join(CONTROLLERS)+' |','|---|'+'---|'*len(CONTROLLERS)]
    for s in c['scenarios']:lines.append(f'| {s} | '+' | '.join(f'{mean(base,s,k,"throughput"):.0f} / {mean(base,s,k,"residual_veh"):.0f}' for k in CONTROLLERS)+' |')
    lines+=['','### Paired total-delay difference vs fixed [veh h], 95% Student-t CI','','| Scenario | Controller | Mean | 95% CI |','|---|---|---:|---|']
    for r in pairs:
        if r['left_mode']==base and r['metric']=='total_delay_veh_s':
            ci=f"[{r['ci95_low']/3600:.2f}, {r['ci95_high']/3600:.2f}]" if r['ci95_low'] is not None else 'one seed'
            lines.append(f"| {r['scenario']} | {r['controller']} | {r['mean_difference']/3600:.2f} | {ci} |")
    lines+=['','### Left-turn signal usage (mean per run)','','| Scenario | Controller | Arrow green [s] | Arrow with same-approach through [s] | Dual arrows [s] | Protected / permissive lefts | Left phases skipped | Min permissive PET [s] |','|---|---|---:|---:|---:|---|---:|---:|']
    for s in c['scenarios']:
        for k in CONTROLLERS:
            pets=[r['min_permissive_left_pet_s'] for r in metrics if r['left_mode']==base and r['scenario']==s and r['controller']==k and r['min_permissive_left_pet_s'] is not None]
            lines.append(f"| {s} | {k} | {mean(base,s,k,'arrow_green_s'):.0f} | {mean(base,s,k,'arrow_with_through_ball_s'):.0f} | {mean(base,s,k,'dual_arrow_s'):.0f} | "
                         f"{mean(base,s,k,'protected_left_turns'):.0f} / {mean(base,s,k,'permissive_left_turns'):.0f} | {mean(base,s,k,'left_phase_skips'):.1f} | {min(pets) if pets else float('nan'):.2f} |")
    study=c['left_mode_study']
    lines+=['','## Left-turn mode comparison (primary road)','','Same demand tapes for every mode. Total delay [veh h] / mean left delay [s/veh] / left vehicles still unserved at the end.','',
            '| Scenario | Mode | '+' | '.join(CONTROLLERS)+' |','|---|---|'+'---|'*len(CONTROLLERS)]
    for s in study['scenarios']:
        for mode in study['modes']:
            cells=[]
            for k in CONTROLLERS:
                unserved=float(np.mean([r['left_offered_veh']-r['left_throughput'] for r in metrics if r['left_mode']==mode and r['scenario']==s and r['controller']==k]))
                cells.append(f'{mean(mode,s,k,"total_delay_veh_s")/3600:.2f} / {mean(mode,s,k,"mean_left_delay_s"):.0f} / {unserved:.0f}')
            lines.append(f'| {s} | {mode} | '+' | '.join(cells)+' |')
    lines+=['','## 60 s forecast count MAE [veh/approach/horizon]','','| Scenario | Transformer |','|---|---:|']
    for s in c['scenarios']:lines.append(f"| {s} | {np.mean([r['mae_veh'] for r in scores if r['scenario']==s and r['left_mode']==base and r['horizon_s']==60]):.3f} |")
    lines+=['','## Verification over all runs','',
        f"Conservation error: {max(r['conservation_error'] for r in metrics)} veh. Red-light entries: {sum(r['red_crossings'] for r in metrics)}. "
        f"Collision-guard corrections: {sum(r['collision_guard_corrections'] for r in metrics)}. Minimum net gap: {min(r['min_gap_m'] for r in metrics if r['min_gap_m'] is not None):.3f} m. "
        f"Max delay-accounting error: {max(r['delay_accounting_error'] for r in metrics):.2e} veh s.",
        f"Smallest post-encroachment time between a permissive left and opposing through/right traffic: {min((r['min_permissive_left_pet_s'] for r in metrics if r['min_permissive_left_pet_s'] is not None),default=float('nan')):.2f} s.",
        '','## Saved interfaces','',
        '`movement_metrics.csv` contains one row per run, approach, lane and permitted movement. `*_seedN_vehicles.csv` preserves every offered vehicle, including boundary and upstream residuals, with a run-scoped vehicle UID, local link ports, exit direction, event times and partial time loss. `*_seedN_conflict_intervals.csv` records conflict-point occupancy. `schema.json` defines units, keys and censoring. `audit.json` independently reconciles these exports with every saved demand tape; rerun with `python audit_complex.py --results '+out.name+'`.','',
        '','## Scope of interpretation','',
        'Right turns share the through ball and FIFO curb lane; right turn on red is disabled. Permissive lefts conservatively yield to opposing rights as well as through vehicles, without assuming separate receiving lanes remove that conflict. Demand factors, 30 m left paths and 12 m right paths are illustrative assumptions. Turners retain the IDM desired speed. Left turners wait at the stop line rather than in the box. No pedestrians, lane changes, downstream receiving queues, or left-bay spillback into through lanes are modeled. Exports identify outbound flows but a future corridor simulator must implement downstream storage, travel time, spillback and vehicle handoff before intersections can interact. The MPC uses a lane-level fluid model with HCM-style permissive saturation flow and does not anticipate IDM start-up loss. Five seeds is pilot scale and no multiple-comparison correction is applied.']
    (out/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--quick',action='store_true'); parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--config',type=Path,default=ROOT/'config.json'); parser.add_argument('--cases',type=Path,default=ROOT/'config_complex.json')
    args=parser.parse_args()
    c=json.loads(args.config.read_text(encoding='utf-8')); c.update(json.loads(args.cases.read_text(encoding='utf-8')))
    if args.quick:c.update(seeds=[101],duration_s=360,training_days=10,epochs=4)
    lay=X.Layout(c); c['approach_demand_factors']=lay.approach_factors.tolist()
    out=ROOT/('results_complex_quick' if args.quick else 'results_complex'); out.mkdir(exist_ok=True)
    dump(out/'config_used.json',c)
    print('Training Transformer on primary/secondary approach totals...',flush=True)
    _,losses=train(c,out); dump(out/'training_loss.json',losses)
    base=c['intersection']['roads'][0]['left_mode']; study=c['left_mode_study']
    runs=[(base,s) for s in c['scenarios']]+[(m,s) for m in study['modes'] for s in study['scenarios'] if (m,s) not in [(base,x) for x in c['scenarios']]]
    jobs=[(mode,s,seed,c,str(out/'transformer.pt')) for mode,s in runs for seed in c['seeds']]
    metrics,scores,motion,replay,movement_metrics=[],[],{},{},[]
    with ProcessPoolExecutor(max_workers=max(1,args.workers)) as pool:
        for mode,scenario,seed,tape,results in pool.map(run_seed,jobs):
            np.save(out/f'lane_demand_{mode}_{scenario}_{seed}.npy',tape)
            for controller,m,d in results:
                m['left_mode']=mode; metrics.append(m)
                movement_metrics.extend(d['movement_metrics'])
                for key in ('vehicles','movement_metrics','conflict_intervals'):
                    path=out/f'{mode}_{scenario}_{controller}_seed{seed}_{key}.csv'
                    if d[key]:write_csv(path,d[key])
                    else:path.write_text('',encoding='utf-8')
                for h in ([30,60] if d['forecast_errors'] else []):
                    scores.append(dict(left_mode=mode,scenario=scenario,seed=seed,controller=controller,horizon_s=h,
                        mae_veh=float(np.mean([r['absolute_error_veh'] for r in d['forecast_errors'] if r['horizon_s']==h]))))
                if seed==c['seeds'][0]:
                    stem=f'{mode}_{scenario}_{controller}'
                    for key in ['observations','commands','forecasts','forecast_errors','departures']:write_csv(out/f'{stem}_{key}.csv',d[key])
                    dump(out/f'{stem}_trace.json',d['trace'])
                    plot_trace(d,f'{scenario} | {controller} | primary left: {mode} | seed {seed}',out/f'{stem}.png')
                    if mode==base or scenario=='left_surge':
                        # Replay keeps every second trajectory sample (0.4 s) to bound the HTML size.
                        replay[stem]=d['trace']; m=d['motion']
                        motion[stem]=dict(m,dt_s=m['dt_s']*2,tracks=[[i,ch,s,xs[::2],vs[::2],b,mv] for i,ch,s,xs,vs,b,mv in m['tracks']])
            print(f'Completed {mode} / {scenario}, seed {seed}',flush=True)
    metrics.sort(key=lambda r:(r['left_mode'],r['scenario'],r['seed'],CONTROLLERS.index(r['controller'])))
    write_csv(out/'metrics.csv',metrics); write_csv(out/'forecast_scores.csv',scores)
    write_csv(out/'movement_metrics.csv',movement_metrics)
    dump(out/'schema.json',dict(version=1,time_units='seconds from run start',delay_units='vehicle seconds',
        movement_axis=list(X.MOVEMENTS),vehicle_key=['run_id','vehicle_id'],
        run_key=['intersection_id','left_mode','scenario','seed','controller'],
        approach_labels='Origin compass leg; outbound_approach is the destination compass leg',
        lane_id='1-based, median to curb, within an inbound approach',
        throughput='Front-bumper stop-line crossings, including vehicles still inside the junction',
        residual_veh='Unserved before the stop line; total local-domain inventory is offered_veh minus exited_veh',
        position_m='Final observed front-bumper distance from the stop line along the movement path, not a world coordinate',
        outbound_entry_time_s='Front bumper reaches the end of its movement path (receiving-link entry)',
        junction_clear_time_s='Rear bumper clears that path',exit_time_s='Front bumper reaches idm.exit_distance_m',
        missing_times='Blank means event not observed by observed_until_s; residual vehicles are censored, not discarded',
        delay_s='Time loss to the stop line, including external waiting; partial time loss for unserved vehicles',
        links='Local port IDs; a future network must map outbound ports to downstream inbound ports and enforce receiving capacity'))
    pairs=[row for mode,s in runs for key in ('total_delay_veh_s','mean_left_delay_s','mean_right_delay_s') for row in paired(metrics,mode,s,c['seeds'],key)]
    write_csv(out/'paired_comparisons.csv',pairs)
    mean=lambda mode,s,ctl,key:np.mean([r[key] for r in metrics if r['left_mode']==mode and r['scenario']==s and r['controller']==ctl])
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    grouped_bars(ax,c['scenarios'],CONTROLLERS,lambda s,k:mean(base,s,k,'total_delay_veh_s')/3600,CONTROLLER_COLORS,'Mean total delay incl. outside queue [veh h]')
    ax.legend(frameon=False,ncol=3); ax.set_title(f'Primary/secondary intersection | primary left: {base} | {len(c["seeds"])} seeds')
    fig.savefig(out/'comparison.png',dpi=160); plt.close(fig)
    fig,axes=plt.subplots(2,len(study['scenarios']),figsize=(4*len(study['scenarios'])+1,7),layout='constrained',squeeze=False)
    for j,s in enumerate(study['scenarios']):
        grouped_bars(axes[0,j],study['modes'],CONTROLLERS,lambda m,k:mean(m,s,k,'total_delay_veh_s')/3600,CONTROLLER_COLORS,'Total delay [veh h]' if j==0 else '')
        grouped_bars(axes[1,j],study['modes'],CONTROLLERS,lambda m,k:mean(m,s,k,'mean_left_delay_s'),CONTROLLER_COLORS,'Mean left-turn delay [s/veh]' if j==0 else '')
        axes[0,j].set_title(s.replace('_',' '))
        for ax in axes[:,j]:ax.tick_params(axis='x',labelsize=8)
    axes[0,0].legend(frameon=False,fontsize=8)
    fig.suptitle('Primary-road left-turn mode comparison (same demand tapes)')
    fig.savefig(out/'left_mode_comparison.png',dpi=160); plt.close(fig)
    dump(out/'replay_data.json',replay); dump(out/'replay_motion.json',motion)
    from build_replay import build
    build(out,template='replay_complex_template.html')
    from audit_complex import audit
    audit(out)
    summarize(out,c,metrics,pairs,scores)
    print(f'Done: {out}',flush=True)


if __name__=='__main__':main()

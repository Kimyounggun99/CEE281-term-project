"""One reproducible entry point: python run.py"""
import argparse
import csv
import json
from pathlib import Path
import platform
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import t as student_t
import torch
from concurrent.futures import ProcessPoolExecutor
from forecast import demand_rates, train, Transformer
from simulation import APPROACHES
from microscopic import run, VERSION
from freeway import run_freeway

ROOT = Path(__file__).resolve().parent
COLORS = ['#007f73','#be405a','#5277bc','#a78119']
CONTROLLER_COLORS = {'fixed':'#007f73','responsive':'#be405a','mpc_transformer':'#a78119'}
CONTROLLERS = ['fixed','responsive','mpc_transformer']
_MODEL_CACHE={}


def run_seed(job):
    scenario,seed,c,weights=job
    if weights not in _MODEL_CACHE:
        model=Transformer();model.load_state_dict(torch.load(weights,weights_only=True));model.eval();_MODEL_CACHE[weights]=model
    rng=np.random.default_rng(seed)
    rates=demand_rates(np.arange(c['duration_s']),c['duration_s'],scenario,day=2)
    arrivals=rng.poisson(rates[:,:,None]*np.array(c['lane_demand_factors']))
    results=[(controller,*run(arrivals,controller,scenario,seed,c,_MODEL_CACHE[weights],detailed=seed==c['seeds'][0])) for controller in CONTROLLERS]
    return scenario,seed,arrivals,results


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def plot_trace(data, title, path):
    fig, axes=plt.subplots(3,1,figsize=(11,8),sharex=True,layout='constrained')
    times=[r['time_s'] for r in data['trace']]
    for i,name in enumerate(APPROACHES):
        q=[r['queues'][i]+r['boundary'][i] for r in data['trace']]
        axes[0].plot(times,q,label=name,color=COLORS[i],lw=1)
        axes[1].plot(times,[r['delay_veh_s'][i]/3600 for r in data['trace']],color=COLORS[i])
    phases={'0:green':0,'1:green':1,'0:yellow':2,'1:yellow':2,'0:all_red':3,'1:all_red':3}
    axes[2].step(times,[phases[r['phase']] for r in data['trace']],where='pre',color='#007f73',lw=.8)
    axes[0].set_ylabel('Queue + boundary [veh]'); axes[0].legend(ncol=4)
    axes[1].set_ylabel('Cumulative delay [veh h]')
    axes[2].set_yticks([0,1,2,3],['NS green','EW green','Yellow','All red'])
    axes[2].set_xlabel('Simulation time [s]')
    fig.suptitle(title)
    fig.savefig(path,dpi=140); plt.close(fig)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--quick',action='store_true'); parser.add_argument('--config',type=Path,default=ROOT/'config.json')
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args(); c=json.loads(args.config.read_text(encoding='utf-8'))
    if args.quick:
        c.update(seeds=[101],duration_s=360,training_days=10,epochs=4)
    assert c['duration_s']%10==0 and c['forecast_horizon_s']==60 and c['observation_s']==10
    assert c['decision_s']==5 and 0<c['min_green_s']<=c['fixed_green_s']<=c['max_green_s']
    assert c['yellow_s']>0 and c['all_red_s']>0 and c['storage_veh']>0
    assert c['lanes_per_approach'] in (1,2) and len(c['lane_demand_factors'])==c['lanes_per_approach']
    assert all(v>=0 for v in c['lane_demand_factors'])
    out=ROOT/('results_quick' if args.quick else 'results'); out.mkdir(exist_ok=True)
    dump(out/'config_used.json',c)
    print('Training Transformer on separate synthetic days...',flush=True)
    model,losses=train(c,out); dump(out/'training_loss.json',losses)
    metrics, scores, paired, details, motion = [], [], [], {}, {}
    jobs=[(scenario,seed,c,str(out/'transformer.pt')) for scenario in c['scenarios'] for seed in c['seeds']]
    with ProcessPoolExecutor(max_workers=max(1,args.workers)) as pool:
        for scenario,seed,arrivals,results in pool.map(run_seed,jobs):
            np.save(out/f'demand_{scenario}_{seed}.npy',arrivals.sum(axis=2))
            np.save(out/f'lane_demand_{scenario}_{seed}.npy',arrivals)
            for controller,m,d in results:
                metrics.append(m)
                for horizon in ([30,60] if d['forecast_errors'] else []):
                    errors=[r['absolute_error_veh'] for r in d['forecast_errors'] if r['horizon_s']==horizon]
                    scores.append(dict(scenario=scenario,seed=seed,controller=controller,horizon_s=horizon,
                                       mae_veh=float(np.mean(errors))))
                if seed==c['seeds'][0]:
                    stem=f'{scenario}_{controller}'; details[stem]=d['trace']
                    motion[stem]=d['motion']
                    dump(out/f'{stem}_motion.json',d['motion'])
                    dump(out/f'{stem}_trace.json',d['trace'])
                    for key in ['observations','commands','forecasts','forecast_errors','departures']:
                        write_csv(out/f'{stem}_{key}.csv',d[key])
                    plot_trace(d,f'{scenario} | {controller} | seed {seed}',out/f'{stem}.png')
            print(f'Completed {scenario}, seed {seed}',flush=True)
    write_csv(out/'metrics.csv',metrics); write_csv(out/'forecast_scores.csv',scores)
    for scenario in c['scenarios']:
        for controller in CONTROLLERS[1:]:
            differences=[]
            for seed in c['seeds']:
                lookup={r['controller']:r['total_delay_veh_s'] for r in metrics if r['scenario']==scenario and r['seed']==seed}
                differences.append(lookup[controller]-lookup['fixed'])
            n=len(differences); mean=float(np.mean(differences))
            half=float(student_t.ppf(.975,n-1)*np.std(differences,ddof=1)/np.sqrt(n)) if n>1 else None
            paired.append(dict(scenario=scenario,controller=controller,reference='fixed',n_pairs=n,
                mean_delay_difference_veh_s=mean,ci95_low=None if half is None else mean-half,ci95_high=None if half is None else mean+half))
    write_csv(out/'paired_comparisons.csv',paired)
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    x=np.arange(len(c['scenarios']))
    for j,controller in enumerate(CONTROLLERS):
        means=[np.mean([r['total_delay_veh_s']/3600 for r in metrics if r['scenario']==s and r['controller']==controller]) for s in c['scenarios']]
        width=.8/len(CONTROLLERS)
        ax.bar(x+(j-(len(CONTROLLERS)-1)/2)*width,means,width,label=controller,color=CONTROLLER_COLORS[controller])
    ax.set_xticks(x,c['scenarios']); ax.set_ylabel('Mean total delay including boundary [veh h]'); ax.legend(ncol=2)
    ax.set_title(f'Paired synthetic experiments | {len(c["seeds"])} seeds | {c["duration_s"]} s')
    fig.savefig(out/'comparison.png',dpi=160); plt.close(fig)
    freeway_metrics=[]
    for control,dt,model_name,headway in [('fixed',.25,'idm',1.5),('feedback',.25,'idm',1.5),('feedback',.125,'idm',1.5),('feedback',.25,'ovm',1.5),('feedback',.25,'idm',2.0)]:
        m,d=run_freeway(dt=dt,controller=control,model=model_name,headway=headway)
        freeway_metrics.append(m)
        stem=f'freeway_{control}_{dt}_{model_name}_{headway}'
        for key,rows in d.items(): write_csv(out/f'{stem}_{key}.csv',rows)
        if control=='feedback' and dt==.25 and model_name=='idm' and headway==1.5:
            fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
            tr=d['trajectory']; scatter=ax.scatter([r['time_s'] for r in tr],[r['position_m'] for r in tr],c=[r['speed_mps'] for r in tr],s=1,cmap='viridis',vmin=0,vmax=30)
            fig.colorbar(scatter,ax=ax,label='Speed [m/s]'); ax.set(xlabel='Time [s]',ylabel='Front-bumper position [m]',title='Freeway IDM | feedback meter | seed 101')
            fig.savefig(out/'freeway_trajectories.png',dpi=150); plt.close(fig)
    write_csv(out/'freeway_metrics.csv',freeway_metrics)
    dump(out/'replay_data.json',details)
    dump(out/'replay_motion.json',motion)
    from build_replay import build
    build(out)
    versions=dict(python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,model_version=VERSION)
    dump(out/'versions.json',versions)
    from summarize import summarize
    summarize(out)
    from audit_results import audit
    audit(out)
    print(f'Done: {out}',flush=True)


if __name__=='__main__': main()

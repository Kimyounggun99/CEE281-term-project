"""Independently reconcile saved complex runs: python audit_complex.py --results results_complex."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

NAMES=('N','S','E','W')
MOVES=('through','left','right')
DEST={'N':('S','E','W'),'S':('N','W','E'),'E':('W','S','N'),'W':('E','N','S')}
OPPOSITE={'N':'S','S':'N','E':'W','W':'E'}


def number(value):
    return None if value is None or value=='' else float(value)


def audit_run(metric,tape,data,c):
    """Check physical and accounting invariants using input tapes and exported records, not the plant."""
    vehicles=data['vehicles']; duration=len(tape); p=c['idm']; entry=-p['approach_length_m']+p['vehicle_length_m']
    roads={a:r for r in c['intersection']['roads'] for a in r['approaches']}
    channels=[(a,lane+1,kind) for a in NAMES for lane,kind in enumerate(roads[a]['lanes'])]
    lane_counts=[len(roads[a]['lanes']) for a in NAMES]
    assert number(metric['lanes_per_approach'])==(lane_counts[0] if len(set(lane_counts))==1 else None)
    for a,count in zip(NAMES,lane_counts):assert int(metric[a+'_inbound_lanes'])==count
    assert len(vehicles)==int(tape.sum()),'Offered vehicles missing from journal'
    assert len({r['vehicle_uid'] for r in vehicles})==len(vehicles),'Duplicate vehicle identity'
    offered=np.zeros_like(tape); delays=np.zeros(tape.shape[1:]); served=np.zeros(tape.shape[1:],int)
    pending=np.zeros_like(served); outgoing=np.zeros_like(served); exited=np.zeros_like(served)
    context=('run_id','intersection_id','scenario','seed','controller','left_mode')
    for r in vehicles:
        for field in context:assert str(r[field])==str(metric[field]),field
        a=r['approach']; m=MOVES.index(r['movement']); lane=int(r['lane_id']); ch=channels.index((a,lane,roads[a]['lanes'][lane-1]))
        assert 'TLR'[m] in channels[ch][2],'Forbidden lane movement'
        assert r['outbound_approach']==DEST[a][m],'Wrong exit direction'
        assert r['inbound_link_id']==f'{metric["intersection_id"]}:{a}:in'
        assert r['outbound_link_id']==f'{metric["intersection_id"]}:{DEST[a][m]}:out'
        assert r['vehicle_uid']==f'{metric["run_id"]}:{r["vehicle_id"]}'
        born=number(r['offered_time_s']); assert born is not None and 1<=born<=duration and born==int(born)
        offered[int(born)-1,ch,m]+=1
        assert number(r['observed_until_s'])==duration
        last=born; missing=False
        for field in ('admitted_time_s','departure_time_s','outbound_entry_time_s','junction_clear_time_s','exit_time_s'):
            value=number(r[field])
            if value is None:missing=True;continue
            assert not missing and np.isfinite(value) and last<=value<=duration+1e-7,(field,value,last)
            last=value
        departure=number(r['departure_time_s']); position=number(r['position_m']); admitted=number(r['admitted_time_s'])
        if departure is not None:
            expected=departure-born+entry/p['desired_speed_mps']; served[ch,m]+=1
            assert r['status']==('exited' if number(r['exit_time_s']) is not None else 'downstream')
        elif admitted is not None:
            assert position is not None and entry<=position<0 and r['status']=='upstream'
            expected=duration-born-(position-entry)/p['desired_speed_mps']
        else:
            expected=duration-born; pending[ch,m]+=1
            assert r['status']=='boundary' and position is None
        delay=number(r['delay_s']); assert delay is not None and np.isfinite(delay) and delay>=-1e-7
        assert abs(delay-expected)<1e-6,'Wrong per-vehicle time loss'
        delays[ch,m]+=delay
        outgoing[ch,m]+=number(r['outbound_entry_time_s']) is not None
        exited[ch,m]+=number(r['exit_time_s']) is not None
    np.testing.assert_array_equal(offered,tape)
    counts=tape.sum(axis=0)
    assert int(served.sum())==int(metric['throughput'])
    assert int(counts.sum()-served.sum())==int(metric['residual_veh'])
    assert int(pending.sum())==int(metric['boundary_residual_veh'])
    assert abs(delays.sum()-float(metric['total_delay_veh_s']))<1e-5
    for m,move in enumerate(MOVES[:tape.shape[2]]):
        assert int(counts[:,m].sum())==int(metric[move+'_offered_veh'])
        assert int(served[:,m].sum())==int(metric[move+'_throughput'])
        assert abs(delays[:,m].sum()-float(metric[move+'_delay_veh_s']))<1e-5
        assert abs(delays[:,m].sum()/max(1,counts[:,m].sum())-float(metric['mean_'+move+'_delay_s']))<1e-6
    seen=set()
    for r in data['movement_metrics']:
        for field in context:assert str(r[field])==str(metric[field]),field
        a=r['approach']; lane=int(r['lane_id']); kind=roads[a]['lanes'][lane-1]; ch=channels.index((a,lane,kind)); m=MOVES.index(r['movement'])
        assert (ch,m) not in seen; seen.add((ch,m))
        assert 'TLR'[m] in kind and r['lane_kind']==kind and r['outbound_approach']==DEST[a][m]
        for field,value in (('offered_veh',counts[ch,m]),('throughput',served[ch,m]),('residual_veh',counts[ch,m]-served[ch,m]),
                            ('boundary_residual_veh',pending[ch,m]),('outbound_entries',outgoing[ch,m]),('exited_veh',exited[ch,m]),('duration_s',duration)):
            assert int(r[field])==value,field
        assert abs(float(r['delay_veh_s'])-delays[ch,m])<1e-6
    assert seen=={(ch,m) for ch,(_,_,kind) in enumerate(channels) for m in range(tape.shape[2]) if 'TLR'[m] in kind}
    best=float('inf'); intervals=data['conflict_intervals']; by_id={int(r['vehicle_id']):r for r in vehicles}
    for r in intervals:
        v=by_id[int(r['vehicle_id'])]; assert r['approach']==v['approach'] and r['movement']==v['movement']
        start=number(r['enter_time_s']); end=number(r['clear_time_s'])
        assert start is None or number(v['departure_time_s'])<=start<=duration+1e-7
        assert end is None or start is not None and start<=end<=duration+1e-7
    for r in intervals:
        if r['movement']!='left' or str(r['permissive']).lower()!='true' or number(r['enter_time_s']) is None:continue
        start=number(r['enter_time_s']); end=number(r['clear_time_s'])
        for s in intervals:
            if s['approach']!=OPPOSITE[r['approach']] or s['movement']=='left' or number(s['enter_time_s']) is None:continue
            other_start=number(s['enter_time_s']); other_end=number(s['clear_time_s'])
            assert max(other_start-(end if end is not None else duration),start-(other_end if other_end is not None else duration))>=-1e-7,'Overlapping conflict occupancy'
            if end is not None and other_end is not None:best=min(best,max(0,other_start-end,start-other_end))
    reported=number(metric['min_permissive_left_pet_s'])
    assert (reported is None and not np.isfinite(best)) or reported is not None and abs(reported-best)<1e-6
    if np.isfinite(best):assert best>=c['intersection'].get('gap_safety_s',1.)-1e-6,'Insufficient PET'
    assert int(metric['red_crossings'])==0 and int(metric['collision_guard_corrections'])==0
    if 'trace' in data:
        cumulative=tape.sum(axis=2).cumsum(axis=0)
        previous={'through':'RRRR','arrow':'RRRR'}
        for k,r in enumerate(data['trace']):
            assert r['time_s']==k+1
            np.testing.assert_array_equal(np.asarray(r['lane_inventory'])+r['lane_boundary'],cumulative[k]-r['lane_throughput'])
            assert max(r['lane_inventory'])<=int(r['lane_storage_capacity'])
            assert max(r['lane_queue_length_m'])<=p['approach_length_m']+1e-7
            greens=[(NAMES[a],'through') for a in range(4) if r['through'][a]=='G']+[(NAMES[a],'left') for a in range(4) if r['arrow'][a]=='G']
            for i,(a,m) in enumerate(greens):
                for b,n in greens[i+1:]:assert a==b or OPPOSITE[a]==b and m==n,'Conflicting greens'
            for a in range(4):
                if r['permissive'][a]=='F':assert r['through'][NAMES.index(OPPOSITE[NAMES[a]])]=='G' and r['arrow'][a]!='G'
            starts=[(NAMES[a],move) for field,move in (('through','through'),('arrow','left')) for a in range(4) if r[field][a]=='G' and previous[field][a]!='G']
            previous=r
            if not starts:continue
            for vehicle in vehicles:
                departure=number(vehicle['departure_time_s']); clear=number(vehicle['junction_clear_time_s'])
                if departure is None or departure>k or clear is not None and clear<=k:continue
                a=vehicle['approach']; left=vehicle['movement']=='left'
                for b,move in starts:
                    assert a==b or OPPOSITE[a]==b and left==(move=='left'),'Protected movement started before a conflicting vehicle cleared'
        for r in vehicles:
            time=number(r['departure_time_s'])
            if time is None:continue
            phase=data['trace'][min(int(time),duration-1)]; a=NAMES.index(r['approach'])
            if r['movement']!='left':assert phase['through'][a] in 'GY','Through/right entered on red'
    if 'motion' in data:audit_motion(data['motion'],c)
    return len(vehicles)


def audit_motion(motion,c):
    """Check saved IDM trajectory bounds independently of the plant's diagnostic counters."""
    p=c['idm']; dt=motion['dt_s']; channels=motion['layout']['channels']; tracks=motion['tracks']
    entry=-p['approach_length_m']+p['vehicle_length_m']
    for uid,ch,start,xs,vs,born,m in tracks:
        x=np.asarray(xs); v=np.asarray(vs)
        assert len(x)==len(v) and len(x)>0 and 0<=ch<len(channels)
        assert np.isfinite(x).all() and np.isfinite(v).all() and (np.diff(x)>=0).all()
        assert x.min()>=entry-.001 and v.min()>=0 and v.max()<=p['desired_speed_mps']+.001
        acc=np.diff(v)/dt
        assert acc.min(initial=0)>=-p['max_braking_mps2']-.002 and acc.max(initial=0)<=p['acceleration_mps2']+.002
    for ch in range(len(channels)):
        lane=sorted((r for r in tracks if r[1]==ch),key=lambda r:r[2])
        for leader,follower in zip(lane,lane[1:]):
            start=max(leader[2],follower[2]); end=min(leader[2]+(len(leader[3])-1)*dt,follower[2]+(len(follower[3])-1)*dt)
            times=np.arange(start,end+1e-8,dt)
            if not len(times):continue
            x_leader=np.interp((times-leader[2])/dt,np.arange(len(leader[3])),leader[3])
            x_follower=np.interp((times-follower[2])/dt,np.arange(len(follower[3])),follower[3])
            assert (x_leader-x_follower>=p['vehicle_length_m']-.01).all(),'Overlapping vehicles in an inbound lane'


def read_csv(path):
    with path.open(newline='',encoding='utf-8') as stream:return list(csv.DictReader(stream))


def audit(folder):
    folder=Path(folder); c=json.loads((folder/'config_used.json').read_text(encoding='utf-8')); metrics=read_csv(folder/'metrics.csv')
    expected={(mode,s,seed,ctl) for mode,s in [(c['intersection']['roads'][0]['left_mode'],s) for s in c['scenarios']]+
              [(mode,s) for mode in c['left_mode_study']['modes'] for s in c['left_mode_study']['scenarios']] for seed in c['seeds'] for ctl in ('fixed','responsive','mpc_transformer')}
    assert {(r['left_mode'],r['scenario'],int(r['seed']),r['controller']) for r in metrics}==expected and len(metrics)==len(expected)
    assert len({r['run_id'] for r in metrics})==len(metrics),'Run identities are not unique'
    vehicles=0; traces=0; trajectories=0; tapes={}; aggregate=[]
    motion=json.loads((folder/'replay_motion.json').read_text(encoding='utf-8'))
    for r in metrics:
        mode,s,ctl,seed=r['left_mode'],r['scenario'],r['controller'],int(r['seed'])
        tape=np.load(folder/f'lane_demand_{mode}_{s}_{seed}.npy')
        key=(s,seed)
        if key in tapes:np.testing.assert_array_equal(tape,tapes[key])
        else:tapes[key]=tape
        stem=f'{mode}_{s}_{ctl}'
        data={key:read_csv(folder/f'{stem}_seed{seed}_{key}.csv') for key in ('vehicles','movement_metrics','conflict_intervals')}
        if seed==c['seeds'][0]:data['trace']=json.loads((folder/f'{stem}_trace.json').read_text(encoding='utf-8'));traces+=1
        if seed==c['seeds'][0] and stem in motion:data['motion']=motion[stem];trajectories+=1
        vehicles+=audit_run(r,tape,data,c); aggregate.extend(data['movement_metrics'])
    saved=read_csv(folder/'movement_metrics.csv')
    sort=lambda row:(row['run_id'],row['approach'],int(row['lane_id']),row['movement'])
    assert sorted(saved,key=sort)==sorted(aggregate,key=sort),'Aggregate movement table disagrees with per-run exports'
    result=dict(status='passed',metric_records=len(metrics),full_traces=traces,trajectory_sets=trajectories,vehicle_records=vehicles,
        checks=['saved-input counts by second, lane and movement','identities and exit routing','event order and censoring',
                'independent time-loss calculation','movement and aggregate reconciliation','matched demand across modes/controllers',
                'conflict occupancy and PET including opposing rights','per-step conservation, storage and signal conflicts',
                'trajectory speed/acceleration bounds, lane separation and protected-movement clearance'])
    (folder/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--results',type=Path,default=Path(__file__).parent/'results_complex')
    audit(parser.parse_args().results)

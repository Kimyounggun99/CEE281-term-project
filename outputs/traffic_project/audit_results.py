"""Independent audit of saved first-seed traces and all experiment inputs."""
import csv
import json
from itertools import groupby
from pathlib import Path
import numpy as np


def audit(out):
    c=json.loads((out/'config_used.json').read_text(encoding='utf-8'))
    with (out/'metrics.csv').open(encoding='utf-8',newline='') as f: metrics=list(csv.DictReader(f))
    audited=0
    for scenario in c['scenarios']:
        seed=c['seeds'][0]
        demand=np.load(out/f'demand_{scenario}_{seed}.npy')
        for controller in ['fixed','responsive','mpc_transformer']:
            trace=json.loads((out/f'{scenario}_{controller}_trace.json').read_text(encoding='utf-8'))
            cumulative=demand.cumsum(axis=0)
            previous=np.zeros(4); integrated=np.zeros(4)
            for k,r in enumerate(trace):
                queue=np.array(r.get('inventory',r['queues']))+r['boundary']
                np.testing.assert_array_equal(cumulative[k],queue+np.array(r['throughput']))
                integrated+=previous
                if r.get('model')!='idm':np.testing.assert_array_equal(integrated,r['delay_veh_s'])
                assert max(r['queues'])<=c['storage_veh']*c.get('lanes_per_approach',1)
                if 'lane_queues' in r:
                    if 'lane_storage_capacity' in r:
                        assert np.max(r['lane_inventory'])<=r['lane_storage_capacity']
                        assert np.max(r['lane_queue_length_m'])<=c['idm']['approach_length_m']+1e-8
                    assert np.max(r['lane_queues'])<=c['storage_veh']
                    lane_demand=np.load(out/f'lane_demand_{scenario}_{seed}.npy') if k==0 else lane_demand
                    np.testing.assert_array_equal(lane_demand[:k+1].sum(axis=0),
                        np.array(r.get('lane_inventory',r['lane_queues']))+r['lane_boundary']+np.array(r['lane_throughput']))
                previous=queue
            segments=[(label,len(list(rows))) for label,rows in groupby(r['phase'] for r in trace)]
            for label,length in segments[:-1]:
                stage=label.split(':')[1]
                if stage=='green': assert c['min_green_s']<=length<=c['max_green_s']
                elif stage=='yellow': assert length==c['yellow_s']
                else: assert length>=c['all_red_s']
            if trace[-1].get('model')=='idm':
                motion=json.loads((out/f'{scenario}_{controller}_motion.json').read_text(encoding='utf-8'))
                tracks={v[0]:v for v in motion['tracks']};v0=motion['parameters']['desired_speed_mps'];road=motion['parameters']['approach_length_m']-motion['parameters']['vehicle_length_m']
                with (out/f'{scenario}_{controller}_departures.csv').open(encoding='utf-8',newline='') as f: departures=list(csv.DictReader(f))
                discharged={int(r['vehicle_id']) for r in departures};computed=sum(float(r['delay_s']) for r in departures)
                uid=0
                for k,counts in enumerate(lane_demand):
                    for count in counts.ravel():
                        for _ in range(int(count)):
                            if uid not in discharged:
                                progress=tracks[uid][3][-1]+road if uid in tracks else 0
                                computed+=len(trace)-(k+1)-progress/v0
                            uid+=1
                assert abs(computed-sum(trace[-1]['delay_veh_s']))<.01
                for track in tracks.values():
                    assert min(track[3])>=-road-.0001
                    assert min(track[4])>=0 and max(track[4])<=v0+.001
                    accelerations=np.diff(track[4])/motion['dt_s']
                    assert np.min(accelerations,initial=0)>=-motion['parameters']['max_braking_mps2']-.002
                    assert np.max(accelerations,initial=0)<=motion['parameters']['acceleration_mps2']+.002
                    moving=np.array(track[4][1:])>0
                    distance=np.diff(track[3])
                    expected=(np.array(track[4][:-1])+track[4][1:])*motion['dt_s']/2
                    assert np.max(np.abs(distance[moving]-expected[moving]),initial=0)<.0002
                for k,row in enumerate(trace):
                    if not row['phase'].endswith('green') or (k and trace[k-1]['phase']==row['phase']):continue
                    active=int(row['phase'].split(':')[0])
                    for tr in tracks.values():
                        if tr[1]//c['lanes_per_approach']//2==active:continue
                        sample=(k-tr[2])/motion['dt_s']
                        if sample<0 or sample>len(tr[3])-1:continue
                        j=int(round(sample));pos=tr[3][j]
                        assert not (0<=pos<motion['parameters']['intersection_length_m']+motion['parameters']['vehicle_length_m']-.001)
            audited+=1
    for r in metrics:
        demand=np.load(out/f"demand_{r['scenario']}_{r['seed']}.npy")
        assert demand.sum()==int(r['throughput'])+int(r['residual_veh'])
        assert int(r['conservation_error'])==0
        if 'red_crossings' in r:
            assert int(r['red_crossings'])==0
            assert int(r['collision_guard_corrections'])==0
        if 'max_queue_length_m' in r:
            assert float(r['max_queue_length_m'])<=c['idm']['approach_length_m']+1e-8
    result=dict(status='passed',metric_records=len(metrics),full_traces=audited,
                checks=['per-step conservation','per-lane conservation and storage','independent delay integration','storage capacity',
                        'green bounds','yellow duration','all-red duration','saved-input conservation','IDM speed/acceleration and conflict clearance when present'])
    (out/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__': print(audit(Path(__file__).parent/'results'))

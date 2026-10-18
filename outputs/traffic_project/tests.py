import unittest
import numpy as np
import json
from pathlib import Path
from simulation import Signal, step_signal, run
from freeway import acceleration, run_freeway
import torch
from forecast import Transformer

C=json.loads((Path(__file__).parent/'config.json').read_text(encoding='utf-8'))


class Verification(unittest.TestCase):
    def test_signal_constraints(self):
        s=Signal(); labels=[]
        for t in range(500):
            mask,label=step_signal(s,True,C); labels.append(label)
            self.assertFalse(mask[:2].any() and mask[2:].any())
        segments=[]
        for label in labels:
            if segments and segments[-1][0]==label: segments[-1][1]+=1
            else: segments.append([label,1])
        for label,length in segments[:-1]:
            if label.endswith('green'): self.assertGreaterEqual(length,10); self.assertLessEqual(length,50)
            if label.endswith('yellow'): self.assertEqual(length,3)
            if label.endswith('all_red'): self.assertEqual(length,1)

    def test_forced_maximum(self):
        s=Signal()
        labels=[step_signal(s,False,C)[1] for _ in range(55)]
        self.assertEqual(labels.count('0:green'),50)
        self.assertEqual(labels[54],'1:green')

    def test_storage_conservation_and_delay(self):
        arrivals=np.full((180,4),2)
        m,d=run(arrivals,'fixed','heavy',1,C,None,True)
        self.assertEqual(m['throughput']+m['residual_veh'],int(arrivals.sum()))
        self.assertGreater(m['boundary_residual_veh'],0)
        self.assertTrue(all(max(r['queues'])<=C['storage_veh'] for r in d['trace']))
        self.assertEqual(m['conservation_error'],0)

    def test_detector_counting_and_recovery(self):
        arrivals=np.ones((180,4),int)
        m,d=run(arrivals,'responsive','detector_fault',1,C,None,True)
        for row in d['observations']:
            if row['quality_flag']=='ok': self.assertEqual(row['count'],10)
            else: self.assertIsNone(row['count'])
        self.assertGreater(m['fallback_decisions'],0)
        # Responsive issues no forecast; check that the detector feed itself recovered after the fault.
        self.assertTrue(all(r['quality_flag']=='ok' for r in d['observations'][-4:]))
        self.assertEqual(d['forecasts'],[])

    def test_empty(self):
        m,_=run(np.zeros((180,4),int),'fixed','balanced',1,C,None)
        self.assertEqual(m['total_delay_veh_s'],0)
        self.assertEqual(m['throughput'],0)

    def test_discharge_upper_bound(self):
        m,d=run(np.full((180,4),3),'fixed','heavy',1,C,None,True)
        for i in range(4):
            green=sum(r['phase']==f'{i//2}:green' for r in d['trace'])
            self.assertLessEqual(m[f'{["N","S","E","W"][i]}_throughput'],green*.5)

    def test_idm_equilibrium(self):
        v=15.; s=(2+v*1.5)/np.sqrt(1-(v/30)**4)
        self.assertAlmostEqual(float(acceleration(v,s,v)),0,places=10)
        self.assertGreater(float(acceleration(10.,1e9,10.)),0)

    def test_two_lanes_independent_service(self):
        a=np.full((30,4,2),3)
        m,d=run(a,'fixed','heavy',1,C,None,True)
        self.assertEqual(m['N_throughput'],28)
        self.assertEqual(d['trace'][-1]['lane_throughput'][0],[14,14])
        self.assertTrue(all(max(max(q) for q in r['lane_queues'])<=C['storage_veh'] for r in d['trace']))
        self.assertEqual(m['throughput']+m['residual_veh'],int(a.sum()))

    def test_empty_lane_cannot_lend_capacity(self):
        a=np.zeros((30,4,2),int); a[:,:,0]=3
        m,d=run(a,'fixed','heavy',1,C,None,True)
        self.assertEqual(m['N_throughput'],14)
        self.assertEqual(d['trace'][-1]['lane_throughput'][0],[14,0])

    def test_saturated_discharge_exact(self):
        m,_=run(np.full((30,4),3),'fixed','heavy',1,C,None)
        # First vehicles arrive at t=1; full service is at t=3,5,...,29.
        self.assertEqual(m['N_throughput'],14)
        self.assertEqual(m['S_throughput'],14)
        self.assertEqual(m['E_throughput'],0)

    def test_controller_cannot_see_future_arrivals(self):
        a=np.ones((90,4),int); b=a.copy(); b[60:]=8
        torch.manual_seed(0); model=Transformer().eval()
        _,left=run(a,'mpc_transformer','balanced',1,C,model,True)
        _,right=run(b,'mpc_transformer','balanced',1,C,model,True)
        self.assertEqual(left['trace'][:60],right['trace'][:60])
        self.assertEqual([r for r in left['commands'] if r['issue_time_s']<60],
                         [r for r in right['commands'] if r['issue_time_s']<60])

    def test_freeway_boundaries(self):
        m,_=run_freeway(duration=120)
        self.assertEqual(m['conservation_error'],0)
        self.assertGreater(m['minimum_gap_m'],0)
        self.assertEqual(m['collision_guard_corrections'],0)


if __name__=='__main__': unittest.main(verbosity=2)

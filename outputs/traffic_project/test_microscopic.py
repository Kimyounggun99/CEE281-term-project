import unittest
import numpy as np
from microscopic import Plant, run

C=dict(idm={'approach_length_m':45.},storage_veh=30,lanes_per_approach=2,lane_demand_factors=[1,1],min_green_s=10,max_green_s=50,fixed_green_s=30,
       yellow_s=3,all_red_s=1,decision_s=5,forecast_horizon_s=60,saturation_veh_s=.5,beam_width=24)


class IDMVerification(unittest.TestCase):
    def drive(self,p,start,end,label):
        for k in range(round((end-start)/p.dt)):p.step(start+k*p.dt,label)

    def test_free_green_no_detector_braking(self):
        p=Plant(C,detailed=True);a=np.zeros((4,2),int);a[0,0]=1;p.add(a,0)
        self.drive(p,0,15,'0:green')
        track=p.tracks[0]
        v0=p.p['desired_speed_mps']
        self.assertTrue(all(abs(v-v0)<1e-5 for v in track[4]))
        self.assertAlmostEqual(p.departures[0]['departure_time_s'],-p.entry_x/v0,places=5)

    def test_red_stop_and_bounded_restart(self):
        p=Plant(C,detailed=True);a=np.zeros((4,2),int);a[0,0]=1;p.add(a,0)
        self.drive(p,0,30,'1:green')
        v=p.cars[0][0];self.assertLess(v.x,0);self.assertLess(v.v,.01)
        # Braking from 15 m/s, IDM settles slightly inside s0=2 m (about 1.8 m), still behind the line.
        self.assertAlmostEqual(v.x,-2,delta=.25)
        self.drive(p,30,45,'0:green')
        self.assertGreater(p.served[0,0],0);self.assertLessEqual(p.max_acc,p.p['acceleration_mps2'])
        self.assertLess(p.departures[0]['speed_mps'],p.p['desired_speed_mps'])
        self.assertEqual(p.guards,0)

    def test_closed_loop_accounting(self):
        a=np.random.default_rng(11).poisson(.22,size=(120,4,2))
        m,_=run(a,'fixed','balanced',11,C,None,True)
        self.assertEqual(m['conservation_error'],0);self.assertEqual(m['red_crossings'],0)
        self.assertEqual(m['collision_guard_corrections'],0)
        self.assertLess(m['delay_accounting_error'],1e-5)
        self.assertGreater(m['min_gap_m'],0)
        self.assertLessEqual(m['max_speed_mps'],15.00001)

    def test_step_sensitivity(self):
        a=np.random.default_rng(12).poisson(.18,size=(120,4,2))
        x,_=run(a,'fixed','balanced',12,C,None)
        y,_=run(a,'fixed','balanced',12,dict(C,idm={'dt_s':.1,'approach_length_m':45.}),None)
        self.assertLess(abs(x['total_delay_veh_s']/y['total_delay_veh_s']-1),.1)
        self.assertLessEqual(abs(x['throughput']-y['throughput']),5)

    def test_no_late_yellow_reacceleration(self):
        from forecast import demand_rates
        rates=demand_rates(np.arange(40),900,'balanced',day=2)
        a=np.random.default_rng(102).poisson(rates[:,:,None]*np.ones(2))
        m,_=run(a,'fixed','balanced',102,C,None,True)
        self.assertEqual(m['collision_guard_corrections'],0)
        self.assertEqual(m['red_crossings'],0)

    def test_long_approach_storage_constraint(self):
        p=Plant(dict(C,idm={'approach_length_m':200.}),detailed=True)
        a=np.zeros((4,2),int);a[0,:]=80;p.add(a,0)
        self.drive(p,0,200,'1:green')
        inventory,queue,boundary=p.counts()
        self.assertEqual(p.capacity,28)  # 200 m // (5 m car + 2 m s0)
        self.assertGreaterEqual(queue[0,0],26)
        self.assertTrue(np.all(inventory<=28))
        self.assertLessEqual(p.queue_lengths().max(),200.)
        self.assertTrue(all(v.x-p.p['vehicle_length_m']>=-200 for lane in p.cars for v in lane))
        self.assertEqual(int((inventory+boundary+p.served).sum()),160)


if __name__=='__main__':unittest.main(verbosity=2)

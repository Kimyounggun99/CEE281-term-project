import copy
import json
import unittest
from pathlib import Path
import numpy as np
import microscopic
import intersection as X
from forecast import demand_rates

ROOT=Path(__file__).parent
LEGACY=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
COMPLEX={**LEGACY,**json.loads((ROOT/'config_complex.json').read_text(encoding='utf-8'))}


def with_mode(mode):
    c=copy.deepcopy(COMPLEX); c['intersection']['roads'][0]['left_mode']=mode; return c


def green_moves(lay,key):
    T,A,P=lay.indications(key)
    return [(a,0) for a in range(4) if T[a]=='G']+[(a,1) for a in range(4) if A[a]=='G']


class RingBarrierSignal(unittest.TestCase):
    def walk(self,mode,seconds=4000,seed=3):
        """Drive the signal with random requests and calls; return the per-second indication keys."""
        lay=X.Layout(with_mode(mode)); c={**COMPLEX,**X.LEFT_DEFAULTS}; rng=np.random.default_rng(seed)
        state=lay.initial(); keys=[]
        for _ in range(seconds):
            state,key=X.step_rings(state,lay,tuple(rng.random(2)<.3),rng.random()<.3,tuple(rng.random(2)<.6),c); keys.append(key)
        return lay,keys

    def test_no_conflicting_greens_and_fya_tied_to_opposing_through(self):
        for mode in X.MODES:
            lay,keys=self.walk(mode)
            for key in set(keys):
                moves=green_moves(lay,key); T,A,P=lay.indications(key)
                for i,(a,m) in enumerate(moves):
                    for b,n in moves[i+1:]:self.assertFalse(X.conflicts(a,m,b,n),(mode,key))
                for a in range(4):
                    # FYA only while the opposing through is green; never together with the arrow (no yellow trap).
                    if P[a]:self.assertEqual(T[X.OPP[a]],'G');self.assertNotEqual(A[a],'G')
                    if mode=='protected' and a<2:self.assertFalse(P[a])

    def test_left_arrow_runs_with_same_approach_through_and_opposing_left(self):
        lay,keys=self.walk('protected_permissive')
        seen=set()
        for key in keys:
            T,A,P=lay.indications(key)
            for a in (0,1):
                if A[a]=='G' and T[a]=='G':seen.add('arrow+ball')
                if A[a]=='G' and A[1-a]=='G':seen.add('dual arrows')
        self.assertEqual(seen,{'arrow+ball','dual arrows'})

    def test_interval_lengths(self):
        lay,keys=self.walk('protected')
        for r in range(2):
            labels=[(k[0],lay.seq[k[0]][r][k[1][r][0]][0],k[1][r][1]) for k in keys]
            runs=[]
            for label in labels:
                if runs and runs[-1][0]==label:runs[-1][1]+=1
                else:runs.append([label,1])
            for (b,kind,stage),n in runs[1:-1]:
                if stage=='yellow':self.assertEqual(n,COMPLEX['yellow_s'])
                if stage=='all_red':self.assertEqual(n,COMPLEX['all_red_s'])
                if stage=='green' and kind=='L':self.assertTrue(COMPLEX['intersection']['min_left_green_s']<=n<=COMPLEX['intersection']['max_left_green_s'])
                if stage=='green' and kind=='T':self.assertGreaterEqual(n,COMPLEX['min_green_s'])

    def test_barrier_ends_both_rings_together(self):
        lay,keys=self.walk('protected_permissive')
        for k in keys:self.assertEqual(k[1][0][1]=='yellow' and lay.seq[k[0]][0][k[1][0][0]][0]=='T',
                                        k[1][1][1]=='yellow' and lay.seq[k[0]][1][k[1][1][0]][0]=='T')

    def test_uncalled_left_is_skipped(self):
        lay=X.Layout(with_mode('protected')); c={**COMPLEX,**X.LEFT_DEFAULTS}
        state=(1,((0,'green',0),(0,'green',0)))
        while state[0]==1:state,_=X.step_rings(state,lay,(False,False),True,(True,False),c)
        self.assertEqual([lay.seq[0][r][state[1][r][0]][0] for r in range(2)],['L','T'])


class TravelTime(unittest.TestCase):
    def test_matches_free_idm_vehicle(self):
        # Gap acceptance relies on travel_time; it must match a plant vehicle under IDM free-road acceleration.
        # Constant-a kinematics gives 4.18 s here, about 0.11 s too fast for the turner seen in seed 104.
        p=microscopic.Plant(COMPLEX); a=np.zeros((4,2),int); a[0,0]=1; p.add(a,0); p.step(0,'0:green')
        v=p.cars[0][0]; v.x=-40.; v.v=8.; t=0.
        while v.x<2.3:
            x0=v.x; p.step(t,'0:green'); t+=p.dt
        t-=p.dt*(v.x-2.3)/(v.x-x0)
        pp=p.p; expected=X.travel_time(42.3,8.,pp['acceleration_mps2'],pp['desired_speed_mps'],pp['acceleration_exponent'])
        self.assertAlmostEqual(t,expected,delta=.02)


class PermissiveLeft(unittest.TestCase):
    def setUp(self):
        self.c=with_mode('protected_permissive'); self.lay=X.Layout(self.c)
        self.left=self.lay.left_lanes[0][0]; self.through_s=[ch for ch in range(len(self.lay.channels)) if self.lay.ch_app[ch]==1 and self.lay.ch_kind[ch]=='T'][0]

    def drive(self,p,start,end,ind):
        for k in range(round((end-start)/p.dt)):p.step(start+k*p.dt,ind)

    def counts(self,**lanes):
        a=np.zeros((len(self.lay.channels),2),int)
        for ch,(m,n) in lanes.items():a[int(ch),m]=n
        return a

    def test_permissive_left_waits_for_gap(self):
        p=X.Plant(self.c,self.lay); fya=(('G','G','R','R'),('R','R','R','R'),(True,True,False,False))
        p.add(self.counts(**{str(self.left):(1,1)}),0)
        # Opposing (S) through traffic arriving continuously, starting before the turner can reach the line: it must hold.
        for t in range(6):
            p.add(self.counts(**{str(self.through_s):(0,1)}),t); self.drive(p,t,t+1,(('R','G','R','R'),('R','R','R','R'),(True,False,False,False)))
        for t in range(6,30):
            p.add(self.counts(**{str(self.through_s):(0,1)}),t); self.drive(p,t,t+1,fya)
        self.assertEqual(p.served[self.left,1],0)
        # A single lane admits the 30 opposing vehicles more slowly than they were offered.
        self.drive(p,30,180,fya)
        self.assertEqual(p.served[self.left,1],1); self.assertEqual(p.red_crossings,0)
        self.assertGreater(p.min_pet(),self.lay.g['gap_safety_s'])

    def test_protected_only_left_never_turns_on_ball(self):
        c=with_mode('protected'); lay=X.Layout(c); p=X.Plant(c,lay)
        a=np.zeros((len(lay.channels),2),int); a[lay.left_lanes[0][0],1]=1; p.add(a,0)
        T,A,P=lay.indications((0,((1,'green'),(1,'green'))))
        self.assertFalse(P[0]); self.drive(p,0,40,(T,A,P))
        self.assertEqual(p.served[:,1].sum(),0)
        self.drive(p,40,60,(('R','R','R','R'),('G','G','R','R'),(False,)*4))
        self.assertEqual(p.served[:,1].sum(),1)

    def test_permissive_capacity(self):
        self.assertAlmostEqual(X.permissive_capacity(0,4.5,2.5),1/2.5)
        caps=[X.permissive_capacity(v,4.5,2.5) for v in (.05,.2,.5,1.)]
        self.assertTrue(all(x>y for x,y in zip(caps,caps[1:])))


class ClosedLoop(unittest.TestCase):
    def test_reduces_exactly_to_legacy_two_phase_model(self):
        rates=demand_rates(np.arange(240),240,'balanced',day=2)
        tape=np.random.default_rng(21).poisson(rates[:,:,None]*np.ones(2))
        for controller in ('fixed','responsive'):
            old,_=microscopic.run(tape,controller,'detector_fault',21,LEGACY,None)
            new,_=X.run(tape,controller,'detector_fault',21,LEGACY,None)
            for k,v in old.items():
                if k in ('model_version','controller_version','demand_id'):continue
                if k=='delay_accounting_error':self.assertLess(abs(new[k]-v),1e-6);continue
                self.assertEqual(new[k],v,(controller,k))

    def test_complex_closed_loop_accounting_and_safety(self):
        import torch
        from forecast import Transformer
        torch.manual_seed(0); model=Transformer().eval()
        for mode in X.MODES:
            c=dict(with_mode(mode),beam_width=8); lay=X.Layout(c)
            tape=X.lane_tape(X.scenario_rates(240,'left_surge',lay),np.random.default_rng(5),lay)
            for controller in ('fixed','responsive','mpc_transformer'):
                m,d=X.run(tape,controller,'left_surge',5,c,model,True)
                self.assertEqual(m['conservation_error'],0); self.assertEqual(m['red_crossings'],0)
                self.assertEqual(m['collision_guard_corrections'],0); self.assertLess(m['delay_accounting_error'],1e-5)
                self.assertEqual(m['throughput']+m['residual_veh'],int(tape.sum()))
                if m['min_permissive_left_pet_s'] is not None:self.assertGreater(m['min_permissive_left_pet_s'],1.)
                if mode=='protected':self.assertTrue(all(r['permissive'][:2]=='--' for r in d['trace']))
                if mode=='permissive':self.assertEqual(m['arrow_green_s'],0)


class RightTurns(unittest.TestCase):
    def setUp(self):
        self.c=with_mode('protected_permissive')
        self.c['intersection']['id']='J1'
        self.c['intersection']['roads'][0].update(lanes=['L','T','TR'],right_factor=.15)
        self.c['intersection']['roads'][1].update(lanes=['LT','TR'],right_factor=.1)

    def test_right_turn_uses_ball_and_keeps_shared_lane_fifo(self):
        lay=X.Layout(self.c); p=X.Plant(self.c,lay)
        ch=2
        counts=np.zeros((10,3),int); counts[ch,2]=1; p.add(counts,0)
        counts[:]=0; counts[ch,0]=1; p.add(counts,1)
        red=(('R',)*4,('G','G','R','R'),(False,)*4)
        for k in range(200):p.step(k*p.dt,red)
        self.assertEqual(p.served.sum(),0)
        green=(('G','G','R','R'),('R',)*4,(True,True,False,False))
        for k in range(200,650):p.step(k*p.dt,green)
        self.assertEqual([r['movement'] for r in p.departures],['right','through'])
        self.assertEqual([r['outbound_approach'] for r in p.departures],['W','S'])
        self.assertEqual(p.red_crossings,0)
        self.assertEqual(p.protected_lefts+p.permissive_lefts,0)

    def test_permissive_left_yields_to_opposing_right_and_clearance_sees_it(self):
        lay=X.Layout(self.c); p=X.Plant(self.c,lay)
        turner=X.Vehicle(0,0,0,-2,0,1)
        p.cars[5]=[X.Vehicle(1,5,0,-1,5,2)]
        self.assertFalse(p.gap_ok(0,turner,'G'))
        p.cars[5][0].x=1
        self.assertFalse(p.clear([(0,1)]))
        p.cars[5][0].x=100
        self.assertTrue(p.gap_ok(0,turner,'G'))
        self.assertTrue(p.clear([(0,1)]))

    def test_clearance_waits_for_accepted_left_before_it_crosses_stop_line(self):
        lay=X.Layout(self.c); p=X.Plant(self.c,lay)
        p.cars[0]=[X.Vehicle(0,0,0,-1,2,1,accepted=True)]
        self.assertFalse(p.clear([(2,0)]))

    def test_lane_permissions_and_invalid_arrivals_are_rejected(self):
        lay=X.Layout(self.c); p=X.Plant(self.c,lay)
        for ch,m in ((0,0),(1,1),(1,2),(2,1),(6,2),(7,1)):
            counts=np.zeros((10,3),int); counts[ch,m]=1
            with self.subTest(channel=ch,movement=m),self.assertRaises(ValueError):p.add(counts,0)
        for bad in (-1,.5,float('nan')):
            counts=np.zeros((10,3)); counts[2,2]=bad
            with self.subTest(count=bad),self.assertRaises(ValueError):p.add(counts,0)

    def test_movement_exports_reconcile_and_include_censored_vehicles(self):
        lay=X.Layout(self.c); tape=np.zeros((100,10,3),int)
        for ch,m in ((0,1),(1,0),(2,2),(3,1),(4,0),(5,2),(6,0),(6,1),(7,2),(8,1),(9,2)):
            tape[0,ch,m]=1
        tape[-1,2,2]=1
        metrics,data=X.run(tape,'fixed','balanced',9,self.c,None)
        self.assertIsNone(metrics['lanes_per_approach'])
        self.assertEqual([metrics[a+'_inbound_lanes'] for a in ('N','S','E','W')],[3,3,2,2])
        self.assertEqual(metrics['right_offered_veh'],5)
        self.assertEqual(sum(r['offered_veh'] for r in data['movement_metrics']),12)
        self.assertEqual(sum(r['throughput'] for r in data['movement_metrics']),metrics['throughput'])
        self.assertAlmostEqual(sum(r['delay_veh_s'] for r in data['movement_metrics']),metrics['total_delay_veh_s'])
        vehicles=data['vehicles']; self.assertEqual(len(vehicles),12)
        self.assertEqual(len({r['vehicle_uid'] for r in vehicles}),12)
        last=vehicles[-1]; self.assertEqual(last['offered_time_s'],100)
        self.assertIsNone(last['admitted_time_s']); self.assertIsNone(last['departure_time_s'])
        self.assertEqual(last['status'],'boundary'); self.assertEqual(last['intersection_id'],'J1')
        expected={'N':{'through':'S','left':'E','right':'W'},'S':{'through':'N','left':'W','right':'E'},
                  'E':{'through':'W','left':'S','right':'N'},'W':{'through':'E','left':'N','right':'S'}}
        for r in vehicles:
            self.assertEqual(r['outbound_approach'],expected[r['approach']][r['movement']])
            if r['exit_time_s'] is not None:
                self.assertLess(r['departure_time_s'],r['exit_time_s'])
                self.assertEqual(r['status'],'exited')
        self.assertEqual(len(vehicles),metrics['throughput']+metrics['residual_veh'])

    def test_three_movement_closed_loop(self):
        import torch
        from forecast import Transformer
        torch.manual_seed(0); model=Transformer().eval()
        for mode in X.MODES:
            c=copy.deepcopy(self.c); c['intersection']['roads'][0]['left_mode']=mode; c['beam_width']=8
            lay=X.Layout(c); tape=X.lane_tape(X.scenario_rates(240,'left_surge',lay),np.random.default_rng(12),lay)
            self.assertEqual(tape.shape,(240,10,3))
            for ctl in ('fixed','responsive','mpc_transformer'):
                with self.subTest(mode=mode,controller=ctl):
                    m,d=X.run(tape,ctl,'left_surge',12,c,model,True)
                    self.assertGreater(m['right_throughput'],0)
                    self.assertEqual(m['red_crossings'],0); self.assertEqual(m['collision_guard_corrections'],0)
                    self.assertEqual(m['throughput']+m['residual_veh'],int(tape.sum()))
                    self.assertLess(m['delay_accounting_error'],1e-5)
                    if m['min_permissive_left_pet_s'] is not None:self.assertGreater(m['min_permissive_left_pet_s'],1.)

    def test_export_audit_detects_corrupt_counts_delays_and_routes(self):
        from audit_complex import audit_run
        tape=np.zeros((90,10,3),int); tape[0,2,2]=1; tape[-1,2,2]=1
        metric,data=X.run(tape,'fixed','balanced',9,self.c,None,True)
        audit_run(metric,tape,data,self.c)
        for field,value in (('delay_s',-10),('outbound_approach','E'),('departure_time_s',-1)):
            broken=copy.deepcopy(data); broken['vehicles'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):audit_run(metric,tape,broken,self.c)
        broken=copy.deepcopy(data); broken['vehicles'].pop()
        with self.assertRaises(AssertionError):audit_run(metric,tape,broken,self.c)
        broken=copy.deepcopy(data); broken['motion']['tracks'][0][4][0]=-1
        with self.assertRaises(AssertionError):audit_run(metric,tape,broken,self.c)

    def test_left_only_lane_never_counts_as_opposing_priority_traffic(self):
        c=copy.deepcopy(self.c); c['intersection']['roads'][0].update(left_mode='permissive',left_factor=0)
        lay=X.Layout(c); q=np.zeros(10); q[3]=1
        key=(0,((0,'green'),(0,'green')))
        self.assertAlmostEqual(lay.service(key,q,np.zeros(10),c)[0],.4)

    def test_road_types_work_on_either_axis_and_with_matching_road_types(self):
        from audit_complex import audit_run
        import torch
        from forecast import Transformer
        torch.manual_seed(0); model=Transformer().eval()
        templates=self.c['intersection']['roads']
        for kinds in ((0,0),(0,1),(1,0),(1,1)):
            c=copy.deepcopy(self.c); c['beam_width']=8
            c['intersection']['roads']=[dict(copy.deepcopy(templates[k]),approaches=approaches) for k,approaches in zip(kinds,(['N','S'],['E','W']))]
            lay=X.Layout(c); tape=X.lane_tape(X.scenario_rates(120,'balanced',lay),np.random.default_rng(17),lay)
            for controller in ('fixed','responsive','mpc_transformer'):
                with self.subTest(road_types=kinds,controller=controller):
                    m,d=X.run(tape,controller,'balanced',17,c,model,True)
                    self.assertGreater(m['right_throughput'],0)
                    audit_run(m,tape,d,c)

    def test_paths_must_fit_inside_the_observed_domain(self):
        for field,value in (('left_path_m',80),('right_path_m',80),('right_path_m',0),('right_conflict_m',13)):
            c=copy.deepcopy(self.c); c['intersection'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):X.Layout(c)

    def test_replay_rebuild_selects_the_saved_model_template(self):
        import tempfile
        from build_replay import build
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder); (out/'replay_data.json').write_text('{}')
            for complex_model in (False,True):
                motion={'case':{'layout':{'channels':[]}}} if complex_model else {'case':{'tracks':[]}}
                (out/'replay_motion.json').write_text(json.dumps(motion))
                build(out)
                html=(out/'replay.html').read_text()
                self.assertEqual('<select id="mode">' in html,complex_model)


if __name__=='__main__':unittest.main(verbosity=2)

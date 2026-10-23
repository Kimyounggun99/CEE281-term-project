"""Primary/secondary IDM intersection with left-turn lanes and NEMA dual-ring phasing.

Generalizes microscopic.py: each approach has a configurable lane list ('L' exclusive left,
'T' through, 'LT' left/through, 'TR' through/right), with a lead-lead dual-ring controller.
With the legacy layout (through lanes only) it reproduces microscopic.run exactly.
"""
from collections import deque
from dataclasses import dataclass
import numpy as np
from forecast import predict, demand_rates
from microscopic import DEFAULTS
from simulation import APPROACHES

VERSION='3.2.0'
OPP=(1,0,3,2)
EXITS=((1,2,3),(0,3,2),(3,1,0),(2,0,1))
MOVEMENTS=('through','left','right')
MODES=('permissive','protected','protected_permissive')
LEFT_DEFAULTS=dict(left_path_m=30.,left_conflict_m=14.,through_conflict_m=12.,critical_gap_s=4.5,follow_up_s=2.5,
                   right_path_m=12.,right_conflict_m=6.,gap_safety_s=1.,min_left_green_s=5,max_left_green_s=25,fixed_left_green_s=10)


def conflicts(a,m,b,n):
    """Conservative conflicts: an opposing left yields to both through and right traffic."""
    if a==b:return False
    if OPP[a]==b:return (m==1)!=(n==1)
    return True


def travel_time(distance,v,a,vmax):
    """Shortest time to cover distance from speed v with acceleration a up to vmax."""
    if distance<=0:return 0.
    if v>=vmax:return distance/max(v,1e-9)
    d1=(vmax*vmax-v*v)/(2*a)
    if distance<=d1:return (-v+np.sqrt(v*v+2*a*distance))/a
    return (vmax-v)/a+(distance-d1)/vmax


def permissive_capacity(v,tc,tf):
    """Gap-acceptance saturation flow [veh/s] against opposing flow v [veh/s] (HCM/Drew form)."""
    if v<1e-6:return 1/tf
    return v*np.exp(-v*tc)/(1-np.exp(-v*tf))


class Layout:
    """Lanes, phase sequences and indications derived from the 'intersection' config block."""
    def __init__(self,c,lanes=2):
        spec=c.get('intersection')
        if spec is None:
            factors=c.get('lane_demand_factors',[1.]*lanes)
            spec=dict(roads=[dict(name='NS',approaches=['N','S'],lanes=['T']*lanes,left_mode='permissive',lane_factors=factors),
                             dict(name='EW',approaches=['E','W'],lanes=['T']*lanes,left_mode='permissive',lane_factors=factors)])
        self.g={**LEFT_DEFAULTS,**{k:v for k,v in spec.items() if k!='roads'}}
        self.id=spec.get('id','intersection_1')
        if not isinstance(self.id,str) or not self.id.strip():raise ValueError('intersection.id must be a nonempty string')
        self.roads=spec['roads']
        if len(self.roads)!=2 or sorted(sum((r['approaches'] for r in self.roads),[]))!=sorted(APPROACHES):
            raise ValueError('Two roads must cover N, S, E and W exactly once')
        self.road_of=[0]*4; self.mode=['permissive']*4
        for b,road in enumerate(self.roads):
            if road['left_mode'] not in MODES:raise ValueError('Unknown left mode: '+str(road['left_mode']))
            if not set(road['lanes'])<={'L','T','LT','TR'} or not any('T' in k for k in road['lanes']):
                raise ValueError('Lanes must be L, T, LT or TR, with at least one through lane')
            if road['left_mode']!='permissive' and 'L' not in road['lanes']:raise ValueError('Protected left phases need an exclusive left lane')
            for name in road['approaches']:
                a=APPROACHES.index(name); self.road_of[a]=b; self.mode[a]=road['left_mode']
            if {APPROACHES.index(n) for n in road['approaches']} not in ({0,1},{2,3}):raise ValueError('Each road must join opposing approaches')
            if len(road.get('lane_factors',road['lanes']))!=len(road['lanes']):raise ValueError('One lane factor is required per lane')
            for movement in ('left','right'):
                factor=road.get(movement+'_factor',0.)
                if factor and not any(movement[0].upper() in k for k in road['lanes']):raise ValueError(movement+' demand has no permitted lane')
        self.movements=MOVEMENTS[:3 if any('R' in k for r in self.roads for k in r['lanes']) else 2]
        self.channels=[]; self.demand=[]
        for a in range(4):
            road=self.roads[self.road_of[a]]; kinds=road['lanes']; n_left=sum('L' in k for k in kinds); n_right=sum('R' in k for k in kinds)
            for lane,kind in enumerate(kinds):
                self.channels.append((a,lane,kind))
                through=road.get('lane_factors',[road.get('through_factor',1.)]*len(kinds))[lane] if 'T' in kind else 0.
                self.demand.append((through,road.get('left_factor',0.)/n_left if 'L' in kind else 0.,
                                    road.get('right_factor',0.)/n_right if 'R' in kind else 0.)[:len(self.movements)])
        n=len(self.channels); self.demand=np.array(self.demand)
        if not np.isfinite(self.demand).all() or (self.demand<0).any():raise ValueError('Demand factors must be finite and nonnegative')
        self.ch_app=np.array([a for a,_,_ in self.channels]); self.ch_kind=[k for _,_,k in self.channels]
        self.allowed=np.array([[letter in kind for letter in 'TLR'[:len(self.movements)]] for kind in self.ch_kind])
        self.M=np.zeros((4,n)); self.M[self.ch_app,np.arange(n)]=1
        self.has_left=[any('L' in self.ch_kind[ch] for ch in range(n) if self.ch_app[ch]==a) for a in range(4)]
        self.left_lanes=[[ch for ch in range(n) if self.ch_app[ch]==a and self.ch_kind[ch]=='L'] for a in range(4)]
        self.approach_factors=self.M@self.demand.sum(axis=1)
        total=self.demand.sum(axis=1); self.prior_share=total/np.maximum(1e-9,(self.M@total)[self.ch_app])
        self.p_left=self.demand[:,1]/np.maximum(1e-9,total)
        # A permissive left also yields to opposing rights, conservatively treating their merge as a conflict.
        self.priority_w=np.where([('T' in k or 'R' in k) for k in self.ch_kind],1-self.p_left,0.)
        # seq[b][r]: phases of ring r in barrier b; ring 0 = [L(A), T(B)], ring 1 = [L(B), T(A)] (lead-lead).
        self.seq=[]
        for road in self.roads:
            A,B=(APPROACHES.index(x) for x in road['approaches'])
            lefts=road['left_mode']!='permissive'
            self.seq.append([([('L',A)] if lefts else [])+[('T',B)],([('L',B)] if lefts else [])+[('T',A)]])
        self.barrier_moves=[[(a,m) for a in range(4) if self.road_of[a]==b for m in range(len(self.movements))] for b in range(2)]
        # The plant's turner starts from the stop line, so its usable gap is the larger of the HCM
        # critical gap and the time needed to clear the conflict point (plus margin).
        p={**DEFAULTS,**c.get('idm',{})}; g=self.g
        paths=((p['intersection_length_m'],g['through_conflict_m']),(g['left_path_m'],g['left_conflict_m']),(g['right_path_m'],g['right_conflict_m']))
        for m,(distance,point) in enumerate(paths):
            if m==1 and not any(self.has_left) or m==2 and len(self.movements)<3:continue
            if not np.isfinite([distance,point,p['exit_distance_m']]).all() or not 0<=point<=distance or distance<=0 or distance+p['vehicle_length_m']>p['exit_distance_m']:
                raise ValueError('Movement path and rear clearance must fit inside the exit boundary; conflict points must lie on the path')
        self.effective_gap_s=max(g['critical_gap_s'],travel_time(p['minimum_gap_m']+g['left_conflict_m']+p['vehicle_length_m'],0.,
                                 p['acceleration_mps2'],p['desired_speed_mps'])+g['gap_safety_s'])
        self.opp_w=[self.M[OPP[a]]*self.priority_w for a in range(4)]
        self.opp_lanes=[int((w>0).sum()) for w in self.opp_w]
        self._ind={}; self._svc={}

    def start(self,b,r,call):
        seq=self.seq[b][r]
        return 0 if seq[0][0]=='L' and call else len(seq)-1

    def initial(self):
        return (0,tuple((self.start(0,r,False),'green',0) for r in range(2)))

    def indications(self,key):
        """Through ball, left arrow and permissive (flashing-yellow-arrow) state per approach."""
        if key not in self._ind:
            b,rings=key; T=['R']*4; A=['R']*4
            for r,(pos,stage) in enumerate(rings):
                kind,a=self.seq[b][r][pos]
                (T if kind=='T' else A)[a]={'green':'G','yellow':'Y'}.get(stage,'R')
            # FYA is tied to the opposing through green, so it ends with it: no yellow trap.
            P=[self.has_left[a] and self.mode[a]!='protected' and T[OPP[a]]=='G' and A[a]!='G' for a in range(4)]
            self._ind[key]=(tuple(T),tuple(A),tuple(P))
        return self._ind[key]

    def calls(self,q,b,threshold):
        """Left-phase calls for both rings of barrier b from per-lane values q (presence or fluid queue)."""
        return tuple(self.seq[b][r][0][0]=='L' and q[self.left_lanes[self.seq[b][r][0][1]]].sum()>=threshold for r in range(2))

    def service(self,key,q,lam,c):
        """Fluid discharge rate [veh/s] of each lane in the indication state `key`."""
        sat=c['saturation_veh_s']; g=self.g
        if key not in self._svc:
            T,A,P=self.indications(key); base=np.zeros(len(self.channels)); yielding=[]
            for ch,(a,_,kind) in enumerate(self.channels):
                if kind in ('T','TR') or (kind=='LT' and not P[a]):base[ch]=sat*(T[a]=='G')*(kind!='LT')
                elif kind=='L' and A[a]=='G':base[ch]=sat
                elif P[a] and (kind=='L' or T[a]=='G'):yielding.append((ch,a,self.p_left[ch] if kind=='LT' else 1.))
            self._svc[key]=(base,yielding)
        base,yielding=self._svc[key]
        if not yielding:return base
        rate=base.copy()
        for ch,a,p in yielding:
            # Opposing priority traffic discharging a queue leaves no usable gaps; otherwise use its arrival rate.
            w=self.opp_w[a]; v=sat*self.opp_lanes[a] if w@q>.5 else float(w@lam)
            perm=min(sat,permissive_capacity(v,self.effective_gap_s,g['follow_up_s']))
            rate[ch]=1/((1-p)/sat+p/max(perm,1e-6))
        return rate


def step_rings(state,lay,end_left,switch,calls,c):
    """Return the indication key for [t,t+1), then advance both ring clocks.

    end_left[r] ends ring r's left arrow (after min left green); switch ends both through
    phases together at the barrier (after min green). calls[r] decides whether ring r of the
    next barrier starts with its left phase or skips it.
    """
    b,rings=state; seqs=lay.seq[b]; rings=[list(r) for r in rings]
    for r,ring in enumerate(rings):
        if ring[1]=='green' and seqs[r][ring[0]][0]=='L' and ((end_left[r] and ring[2]>=c['min_left_green_s']) or ring[2]>=c['max_left_green_s']):
            ring[1],ring[2]='yellow',0
    if all(ring[1]=='green' and seqs[r][ring[0]][0]=='T' for r,ring in enumerate(rings)):
        e=[ring[2] for ring in rings]
        if min(e)>=c['min_green_s'] and (switch or max(e)>=c['max_green_s']):
            for ring in rings:ring[1],ring[2]='yellow',0
    key=(b,tuple((ring[0],ring[1]) for ring in rings))
    for r,ring in enumerate(rings):
        if ring[1]=='done':continue
        ring[2]+=1
        if ring[1]!='green' and ring[2]>=(c['yellow_s'] if ring[1]=='yellow' else c['all_red_s']):
            ring[2]=0
            if ring[1]=='yellow':ring[1]='all_red'
            elif ring[0]<len(seqs[r])-1:ring[0]+=1;ring[1]='green'
            else:ring[1]='done'
    if all(ring[1]=='done' for ring in rings):
        b=1-b; rings=[[lay.start(b,r,calls[r]),'green',0] for r in range(2)]
    return (b,tuple(map(tuple,rings))),key


def ring_options(state,lay,c):
    b,rings=state; seqs=lay.seq[b]
    left=[[False,True] if ring[1]=='green' and seqs[r][ring[0]][0]=='L' and ring[2]>=c['min_left_green_s'] else [False] for r,ring in enumerate(rings)]
    through=all(ring[1]=='green' and seqs[r][ring[0]][0]=='T' and ring[2]>=c['min_green_s'] for r,ring in enumerate(rings))
    return [((l0,l1),sw) for l0 in left[0] for l1 in left[1] for sw in ([False,True] if through else [False])]


def optimize_rings(q,state,arrivals,lay,c):
    """Beam search over end-left / barrier-switch decisions with a per-lane fluid model."""
    beam=[(0.,q.copy(),state,None)]
    for k in range(0,c['forecast_horizon_s'],c['decision_s']):
        candidates=[]
        for cost,queue,s,first in beam:
            for end_left,switch in ring_options(s,lay,c):
                ss,qq,value=s,queue.copy(),cost
                for j in range(c['decision_s']):
                    calls=lay.calls(qq,1-ss[0],.5)
                    ss,key=step_rings(ss,lay,end_left if j==0 else (False,False),switch and j==0,calls,c)
                    value+=qq.sum()
                    lam=arrivals[(k+j)//10]/10
                    qq=np.maximum(0,qq+lam-lay.service(key,qq,lam,c))
                candidates.append((value,qq,ss,(end_left,switch) if k==0 else first))
        beam=sorted(candidates,key=lambda x:x[0])[:c['beam_width']]
    return beam[0][3],float(beam[0][0])


@dataclass
class Vehicle:
    id: int
    channel: int
    born: float
    x: float
    v: float
    mov: int=0
    committed: bool=False
    accepted: bool=False


class Plant:
    def __init__(self,c,lay,detailed=False):
        self.p={**DEFAULTS,**c.get('idm',{})}; self.dt=self.p['dt_s']; self.g=lay.g
        assert abs(round(1/self.dt)*self.dt-1)<1e-9
        self.lay=lay; self.c=c; self.detailed=detailed; n=len(lay.channels)
        self.capacity=min(c['storage_veh'],int(self.p['approach_length_m']//(self.p['vehicle_length_m']+self.p['minimum_gap_m'])))
        if self.capacity<1:raise ValueError('Approach must store at least one vehicle with its standstill gap')
        self.entry_x=-self.p['approach_length_m']+self.p['vehicle_length_m']
        self.cars=[[] for _ in range(n)]; self.pending=[deque() for _ in range(n)]; self.waiting=np.zeros((n,len(lay.movements)),int)
        self.offered=self.waiting.copy(); self.served=self.offered.copy()
        self.delay=np.zeros((4,len(lay.movements))); self.next_id=0; self.tracks={}; self.departures=[]; self.vehicles={}
        self.guards=0; self.red_crossings=0; self.yellow_crossings=0
        self.protected_lefts=0; self.permissive_lefts=0; self.conflict_times={}
        self.last_T=['X']*4; self.last_A=['X']*4
        self.min_gap=float('inf'); self.max_acc=0.; self.min_acc=0.; self.max_speed=0.

    def add(self,counts,t):
        counts=np.asarray(counts)
        if counts.shape==(len(self.lay.channels),2) and len(self.lay.movements)==3:counts=np.pad(counts,((0,0),(0,1)))
        if counts.shape!=self.offered.shape or not np.isfinite(counts).all() or (counts<0).any() or (counts!=np.floor(counts)).any():
            raise ValueError('Arrivals must be nonnegative integer counts with one row per lane and one column per movement')
        if (counts[~self.lay.allowed]>0).any():raise ValueError('Arrival movement is not permitted in its lane')
        counts=counts.astype(int)
        self.offered+=counts
        for ch,q in enumerate(self.pending):
            a,lane,_=self.lay.channels[ch]
            for m in range(len(self.lay.movements)):
                for _ in range(int(counts[ch,m])):
                    uid=self.next_id; q.append((uid,t,m)); self.next_id+=1
                    out=APPROACHES[EXITS[a][m]]
                    self.vehicles[uid]=dict(vehicle_id=uid,approach=APPROACHES[a],lane_id=lane+1,movement=MOVEMENTS[m],
                        inbound_link_id=f'{self.lay.id}:{APPROACHES[a]}:in',outbound_link_id=f'{self.lay.id}:{out}:out',outbound_approach=out,
                        offered_time_s=float(t),admitted_time_s=None,departure_time_s=None,outbound_entry_time_s=None,
                        junction_clear_time_s=None,exit_time_s=None,delay_s=None,position_m=None,speed_mps=None,status='boundary')
            self.waiting[ch]+=counts[ch]

    def path(self,mov):
        return self.g['left_path_m'] if mov==1 else self.g['right_path_m'] if mov==2 else self.p['intersection_length_m']

    def conflict_point(self,mov):
        return self.g['left_conflict_m'] if mov==1 else self.g['right_conflict_m'] if mov==2 else self.g['through_conflict_m']

    def clear(self,moves):
        """No conflicting box occupant or already-accepted left still approaching the stop line."""
        length=self.p['vehicle_length_m']
        return not any((0<=v.x<self.path(v.mov)+length or v.x<0 and v.accepted) and any(conflicts(self.lay.ch_app[ch],v.mov,b,m) for b,m in moves)
                       for ch,cars in enumerate(self.cars) for v in cars)

    def counts(self):
        inventory=np.array([sum(v.x<0 for v in cars) for cars in self.cars])
        queue=np.array([sum(v.x<0 and v.v<.5 for v in cars) for cars in self.cars])
        boundary=np.array([len(q) for q in self.pending])
        return inventory,queue,boundary

    def presence(self,zone_m=12.):
        """Stop-bar presence loop per lane: any vehicle body over the last zone_m before the stop line."""
        length=self.p['vehicle_length_m']
        return np.array([float(any(-zone_m<v.x and v.x-length<0 for v in cars)) for cars in self.cars])

    def queue_lengths(self):
        return np.array([max((-v.x+self.p['vehicle_length_m'] for v in cars if v.x<0 and v.v<.5),default=0.) for cars in self.cars])

    def gap_ok(self,a,v,opposing):
        """Permissive left: accept if every opposing through/right vehicle reaches its conflict point
        later than both the critical gap and the time this turner needs to clear it. Once the
        opposing through shows yellow, its uncommitted approaching vehicles will stop (sneakers)."""
        p=self.p; g=self.g; length=p['vehicle_length_m']; acc=p['acceleration_mps2']; v0=p['desired_speed_mps']
        need=max(g['critical_gap_s'],travel_time(-v.x+g['left_conflict_m']+length,v.v,acc,v0)+g['gap_safety_s'])
        for ch,cars in enumerate(self.cars):
            if self.lay.ch_app[ch]!=OPP[a]:continue
            for u in cars:
                point=self.conflict_point(u.mov)
                if u.mov==1 or u.x-length>=point:continue
                # Test the stop condition directly: this lane may not have made its yellow decision yet this step.
                if opposing!='G' and u.x<0 and not u.committed and -u.x>u.v*u.v/(2*p['yellow_decision_braking_mps2']):continue
                if travel_time(point-u.x,u.v,acc,v0)<need:return False
        return True

    def mark(self,v,x0,x1,t):
        """Record when a vehicle's front reaches and rear clears its conflict point (for PET)."""
        point=self.conflict_point(v.mov)
        record=self.conflict_times.setdefault(v.id,[self.lay.ch_app[v.channel],v.mov,v.accepted,None,None])
        for k,threshold in ((3,point),(4,point+self.p['vehicle_length_m'])):
            if record[k] is None and x0<threshold<=x1:record[k]=t+self.dt*(threshold-x0)/(x1-x0)

    def step(self,t,ind):
        p=self.p; dt=self.dt; v0=p['desired_speed_mps']; length=p['vehicle_length_m']; lay=self.lay
        T,A,P=ind
        # Permissive turning is allowed while the opposing through is green (FYA) or yellow (clearing).
        permit=[lay.has_left[a] and lay.mode[a]!='protected' and A[a]!='G' and T[OPP[a]] in 'GY' for a in range(4)]
        y_T=[T[a]=='Y' and self.last_T[a]!='Y' for a in range(4)]; y_A=[A[a]=='Y' and self.last_A[a]!='Y' for a in range(4)]
        self.last_T=list(T); self.last_A=list(A)
        for ch,cars in enumerate(self.cars):
            approach=lay.ch_app[ch]; lane=lay.channels[ch][1]; kind=lay.ch_kind[ch]
            if self.pending[ch] and sum(v.x<0 for v in cars)<self.capacity:
                gap=cars[-1].x-self.entry_x-length if cars else 1e6
                if gap>=p['minimum_gap_m']+.2:
                    uid,born,m=self.pending[ch].popleft(); self.waiting[ch,m]-=1
                    # Largest entry speed whose IDM desired gap s*(v,v-lead) fits the gap: k v^2+(T-k lead)v-(gap-s0)=0.
                    k=1/(2*np.sqrt(p['acceleration_mps2']*p['comfortable_braking_mps2'])); h=p['headway_s']-k*(cars[-1].v if cars else v0)
                    speed=min(v0,(-h+np.sqrt(h*h+4*k*max(0,gap-p['minimum_gap_m'])))/(2*k))
                    v=Vehicle(uid,ch,born,self.entry_x,speed,m); cars.append(v)
                    self.vehicles[uid].update(admitted_time_s=float(t),status='upstream')
                    if self.detailed:self.tracks[uid]=[uid,ch,round(t,5),[round(v.x,4)],[round(v.v,4)],born,m]
            self.delay[approach]+=self.waiting[ch]*dt
            if not cars:continue
            x=np.array([v.x for v in cars]); speed=np.array([v.v for v in cars])
            gap=np.r_[1e6,x[:-1]-x[1:]-length]; lead_speed=np.r_[v0,speed[:-1]]
            blocked=np.zeros(len(cars),bool); legal=[False]*len(cars); yellow_go=[False]*len(cars)
            for j,v in enumerate(cars):
                head=j==0 or cars[j-1].x>=0
                state,started=(A[approach],y_A[approach]) if v.mov==1 and kind=='L' else ((T[approach],y_T[approach]) if v.mov!=1 else ('R',False))
                green=state=='G'; yellow=state=='Y'
                if green:v.committed=False
                leader_committed=head or cars[j-1].committed
                if yellow and started and v.x<0 and v.v>.5 and leader_committed and -v.x<=v.v*v.v/(2*p['yellow_decision_braking_mps2']):
                    v.committed=True
                go=green or (yellow and v.committed); yellow_go[j]=yellow
                if v.mov==1 and not go and v.x<0:
                    if v.accepted:go=True
                    elif head and permit[approach] and (kind=='L' or T[approach] in 'GY') and \
                         -v.x<=v.v*v.v/(2*p['comfortable_braking_mps2'])+p['minimum_gap_m']+1 and self.gap_ok(approach,v,T[OPP[approach]]):
                        v.accepted=go=True
                legal[j]=go or yellow
                blocked[j]=v.x<0 and not go
            red_leader=blocked & (-x<gap)
            gap=np.where(red_leader,-x,gap); lead_speed=np.where(red_leader,0,lead_speed)
            desired=p['minimum_gap_m']+np.maximum(0,speed*p['headway_s']+speed*(speed-lead_speed)/(2*np.sqrt(p['acceleration_mps2']*p['comfortable_braking_mps2'])))
            acc=p['acceleration_mps2']*(1-(speed/v0)**p['acceleration_exponent']-(desired/np.maximum(gap,.01))**2)
            acc=np.clip(acc,-p['max_braking_mps2'],p['acceleration_mps2'])
            nv=np.maximum(0,speed+acc*dt); dx=speed*dt+.5*acc*dt*dt
            stopping=speed+acc*dt<0; dx[stopping]=-speed[stopping]**2/(2*acc[stopping])
            nx=x+np.maximum(0,dx)
            for j,v in enumerate(cars):
                cap=nx[j-1]-length-.05 if j else float('inf')
                if blocked[j]:cap=min(cap,-.01)
                if nx[j]>cap:
                    self.guards+=1; nx[j]=max(x[j],cap); nv[j]=min(nv[j],nv[j-1] if j else 0.)
                if j:self.min_gap=min(self.min_gap,float(nx[j-1]-nx[j]-length))
                if x[j]<0:
                    distance=nx[j]-x[j]
                    fraction=min(1.,-x[j]/distance) if distance>0 else 1.
                    self.delay[approach,v.mov]+=fraction*dt-min(distance,-x[j])/v0
                    if nx[j]>=0:
                        crossing=t+fraction*dt
                        self.served[ch,v.mov]+=1
                        self.red_crossings+=int(not legal[j]); self.yellow_crossings+=int(yellow_go[j])
                        if v.mov==1:
                            if v.accepted:self.permissive_lefts+=1
                            else:self.protected_lefts+=1
                        event=dict(vehicle_id=v.id,approach=APPROACHES[approach],lane_id=lane+1,
                            movement=MOVEMENTS[v.mov],outbound_approach=APPROACHES[EXITS[approach][v.mov]],arrival_time_s=v.born,departure_time_s=crossing,
                            delay_s=crossing-v.born+self.entry_x/v0,speed_mps=float(nv[j]),
                            signal_stage='permissive' if v.accepted else ('yellow' if yellow_go[j] else 'green'))
                        self.departures.append(event); self.vehicles[v.id].update(departure_time_s=crossing,delay_s=event['delay_s'],status='downstream')
                for field,threshold in (('outbound_entry_time_s',self.path(v.mov)),('junction_clear_time_s',self.path(v.mov)+length),('exit_time_s',p['exit_distance_m'])):
                    if x[j]<threshold<=nx[j]:
                        self.vehicles[v.id][field]=t+dt*(threshold-x[j])/(nx[j]-x[j])
                        if field=='exit_time_s':self.vehicles[v.id].update(status='exited',position_m=float(nx[j]),speed_mps=float(nv[j]))
                if nx[j]>=0 and x[j]<self.path(v.mov)+length:self.mark(v,x[j],nx[j],t)
                self.max_speed=max(self.max_speed,float(nv[j])); self.max_acc=max(self.max_acc,float(acc[j])); self.min_acc=min(self.min_acc,float(acc[j]))
                v.x=float(nx[j]);v.v=float(nv[j])
                if self.detailed:
                    self.tracks[v.id][3].append(round(v.x,4));self.tracks[v.id][4].append(round(v.v,4))
            # shortcut: downstream vehicles retain their inbound-lane leader, replace with receiving-link queues when coupling junctions.
            self.cars[ch]=[v for v in cars if v.x<p['exit_distance_m']]

    def verify_delay(self,t):
        remaining=sum(t-born for q in self.pending for _,born,_ in q)
        remaining+=sum(t-v.born-(v.x-self.entry_x)/self.p['desired_speed_mps'] for cars in self.cars for v in cars if v.x<0)
        return abs(sum(d['delay_s'] for d in self.departures)+remaining-self.delay.sum())

    def min_pet(self):
        """Smallest PET between a permissive left and opposing through/right traffic."""
        records=[r for r in self.conflict_times.values() if r[3] is not None and r[4] is not None]
        best=float('inf')
        for a in range(4):
            lefts=[(r[3],r[4]) for r in records if r[0]==a and r[1]==1 and r[2]]
            through=np.array([(r[3],r[4]) for r in records if r[0]==OPP[a] and r[1]!=1]).reshape(-1,2)
            for t_in,t_out in lefts:
                if len(through):best=min(best,float(np.maximum(0,np.maximum(through[:,0]-t_out,t_in-through[:,1])).min()))
        return best


def lane_tape(rates,rng,lay):
    """Poisson arrivals per lane and movement, ordered through / left / right (if enabled)."""
    return rng.poisson(rates[:,lay.ch_app]*lay.demand[None])


def scenario_rates(duration,scenario,lay,day=2):
    """Base rates per second, approach and movement; 'left_surge' triples the left demand of the
    first primary approach only in the second half (unequal opposing lefts)."""
    t=np.arange(duration)
    base=demand_rates(t,duration,'balanced' if scenario=='left_surge' else scenario,day=day)
    rates=np.repeat(base[:,:,None],len(lay.movements),axis=2)
    if scenario=='left_surge':
        rates[t>=duration/2,APPROACHES.index(lay.roads[0]['approaches'][0]),1]*=3.
    return rates


def run(tape,controller,scenario,seed,c,model,detailed=False):
    """Closed loop on a (seconds, lanes, movements) tape, or a legacy through-only tape."""
    if 'intersection' not in c:
        legacy=tape[:,:,None] if tape.ndim==2 else tape
        lanes=legacy.shape[2]; tape=np.zeros((len(legacy),4*lanes,2),int); tape[:,:,0]=legacy.reshape(len(legacy),-1)
        c=dict(c,lanes_per_approach=lanes); lay=Layout(c,lanes)
    else:lay=Layout(c)
    c={**LEFT_DEFAULTS,**{k:v for k,v in lay.g.items() if k.endswith('green_s')},**c}
    tape=np.asarray(tape); n=len(lay.channels)
    if tape.ndim!=3 or not len(tape) or tape.shape[1:]!=(n,len(lay.movements)):raise ValueError('Demand tape must have shape (seconds, lanes, movements)')
    if not np.isfinite(tape).all() or (tape<0).any() or (tape!=np.floor(tape)).any() or (tape[:,~lay.allowed]>0).any():
        raise ValueError('Demand tape contains invalid counts or forbidden lane movements')
    plant=Plant(c,lay,detailed); g=lay.g
    state=lay.initial(); history=[]; latest=-1; estimate=np.zeros(n); prior=1.8*lay.approach_factors
    pred=np.tile(prior,(6,1)); last_out=plant.served.sum(axis=1); pending=[]; lane_history=[]
    trace=[]; observations=[]; commands=[]; forecasts=[]; errors=[]; issued=[]
    maximum=np.zeros(4,int); max_error=0; fallback=0; clearance_holds=0; max_length=0.; max_backlog=0
    skipped=0; arrow_s=np.zeros(4,int); arrow_with_ball_s=0; dual_arrow_s=0; fya_s=np.zeros(4,int); end_left=(False,False)
    lefts_present=any(seq[0][0]=='L' for seqs in lay.seq for seq in seqs)
    for t in range(len(tape)):
        if t and t%10==0:
            missing=scenario=='detector_fault' and len(tape)*.4<=t<len(tape)*.65
            lag=30 if scenario=='delayed' else 0
            out=plant.served.sum(axis=1)
            pending.append(dict(deliver=t+lag,end=t,missing=missing,inc=tape[t-10:t].sum(axis=(0,2)),
                out=out-last_out,inventory=(plant.offered-plant.served).sum(axis=1)))
            last_out=out.copy()
        for packet in list(pending):
            if packet['deliver']>t:continue
            pending.remove(packet); good=not packet['missing'] and t-packet['end']<=10
            for i,name in enumerate(APPROACHES):
                lanes_i=[ch for ch in range(n) if lay.ch_app[ch]==i]
                observations.append(dict(sensor_id=name,interval_start_s=packet['end']-10,interval_end_s=packet['end'],
                    delivery_time_s=t,count=None if packet['missing'] else int(packet['inc'][lanes_i].sum()),
                    departure_count=None if packet['missing'] else int(packet['out'][lanes_i].sum()),
                    lane_arrival_counts=None if packet['missing'] else packet['inc'][lanes_i].tolist(),
                    lane_departure_counts=None if packet['missing'] else packet['out'][lanes_i].tolist(),
                    mean_speed_mps=None,quality_flag='ok' if good else 'missing_or_stale'))
            if good:
                # Per-lane cumulative entry/exit balance; exclusive left lanes therefore measure left inventory.
                estimate=packet['inventory'].astype(float); latest=t
                history.append(lay.M@packet['inc']); lane_history.append(packet['inc'])
            else:history.append(np.mean(history[-3:],axis=0) if history else prior.copy())
        if t%10==0 and controller=='mpc_transformer':
            pred=predict(model,history,t,prior_count=prior)
            if t>=120 and t+60<=len(tape):
                for h in [30,60]:issued.append((t,h,pred[:h//10].sum(axis=0)))
            for i,name in enumerate(APPROACHES):forecasts.append(dict(issue_time_s=t,target_time_s=t+60,segment_id=name,
                estimated_state=float(estimate[lay.ch_app==i].sum()),predicted_value=float(pred[:,i].sum()),variable_name='arrival_count',units='veh',quality='observed' if latest==t else 'imputed'))
        stale=latest<0 or t-latest>10
        actuated=controller!='fixed' and not stale
        # Left calls come from stop-bar presence loops (as in field actuation); pretimed always serves lefts.
        presence=plant.presence() if lefts_present else None
        calls=lay.calls(presence,1-state[0],1) if actuated and lefts_present else (True,True)
        switch=False; reason='hold'; objective=None
        if t%c['decision_s']==0:
            b,rings=state
            in_left=[rings[r][1]=='green' and lay.seq[b][r][rings[r][0]][0]=='L' for r in range(2)]
            in_through=all(rings[r][1]=='green' and lay.seq[b][r][rings[r][0]][0]=='T' for r in range(2))
            if not actuated:
                end_left=tuple(in_left[r] and rings[r][2]>=c['fixed_left_green_s'] for r in range(2))
                switch=in_through and min(r[2] for r in rings)>=lay.roads[b].get('fixed_green_s',c['fixed_green_s'])
                reason='fixed_plan' if controller=='fixed' else 'fallback_stale_observation'; fallback+=int(stale and controller!='fixed')
            elif controller=='responsive':
                # Gap-out: end a left arrow once its stop-bar presence loop is empty.
                waiting=lay.calls(presence,b,1) if lefts_present else (True,True)
                end_left=tuple(in_left[r] and not waiting[r] for r in range(2))
                sums=lay.M@estimate; own=sums[[a for a in range(4) if lay.road_of[a]==b]].sum(); other=sums.sum()-own
                switch=other>own+2; reason='left_queue_cleared_or_opposing_inventory'
            else:
                # Lane-level forecast: approach Transformer forecast split by observed lane shares.
                recent=np.sum(lane_history[-6:],axis=0) if lane_history else np.zeros(n)
                share=(recent+10*lay.prior_share)/((lay.M@recent)[lay.ch_app]+10)
                (end_left,switch),objective=optimize_rings(estimate,state,pred[:,lay.ch_app]*share,lay,c)
                reason='minimum_predicted_inventory_integral'
            commands.append(dict(issue_time_s=t,apply_time_s=t,actuator_id=lay.id,
                action='request_switch' if switch else ('end_left' if any(end_left) else 'hold'),value=int(switch),units='boolean',
                end_left_ring1=int(end_left[0]),end_left_ring2=int(end_left[1]),reason=reason,barrier=b,
                ring_phases=[lay.seq[b][r][rings[r][0]][0]+APPROACHES[lay.seq[b][r][rings[r][0]][1]] for r in range(2)],
                stage=[rings[r][1] for r in range(2)],estimated_inventory=estimate.tolist(),objective_veh_s=objective))
        else:end_left=(False,False)
        # Clearance interlock: hold a ring's all-red until no conflicting vehicle remains in the box.
        b,rings=state; rings=[list(r) for r in rings]
        if all(r[1]=='all_red' and r[2]>=c['all_red_s']-1 and r[0]==len(lay.seq[b][k])-1 for k,r in enumerate(rings)):
            if not plant.clear(lay.barrier_moves[1-b]):
                for r in rings:r[2]=c['all_red_s']-2
                clearance_holds+=1
        else:
            for k,r in enumerate(rings):
                if r[1]=='all_red' and r[2]>=c['all_red_s']-1 and r[0]<len(lay.seq[b][k])-1:
                    _,a=lay.seq[b][k][r[0]+1]
                    if not plant.clear([(a,0)]):r[2]=c['all_red_s']-2;clearance_holds+=1
        state=(b,tuple(map(tuple,rings)))
        before=state[0]
        state,key=step_rings(state,lay,end_left,switch,calls,c)
        if state[0]!=before:skipped+=sum(lay.seq[state[0]][r][0][0]=='L' and lay.seq[state[0]][r][state[1][r][0]][0]=='T' for r in range(2))
        ind=lay.indications(key); T,A,P=ind
        arrow_s+=[x=='G' for x in A]; fya_s+=[bool(x) for x in P]
        arrow_with_ball_s+=int(any(A[a]=='G' and T[a]=='G' for a in range(4)))
        dual_arrow_s+=int(any(A[a]=='G' and A[OPP[a]]=='G' for a in range(4)))
        for sub in range(round(1/plant.dt)):plant.step(t+sub*plant.dt,ind)
        plant.add(tape[t],t+1)
        inventory,queue,boundary=plant.counts(); residual=lay.M@(inventory+boundary)
        maximum=np.maximum(maximum,(lay.M@queue).astype(int))
        lengths=plant.queue_lengths();max_length=max(max_length,float(lengths.max()))
        max_backlog=max(max_backlog,int((lay.M@(queue+boundary)).max()))
        assert np.max(inventory)<=plant.capacity
        assert lengths.max()<=plant.p['approach_length_m']+1e-8
        error=int(np.max(np.abs((plant.offered-plant.served).sum(axis=1)-inventory-boundary)));max_error=max(max_error,error);assert error==0
        if detailed:trace.append(dict(time_s=t+1,phase=f'{key[0]}:'+'/'.join(lay.seq[key[0]][r][key[1][r][0]][0]+APPROACHES[lay.seq[key[0]][r][key[1][r][0]][1]]+'-'+key[1][r][1] for r in range(2)),
            through=''.join(T),arrow=''.join(A),permissive=''.join('F' if x else '-' for x in P),
            queues=(lay.M@queue).astype(int).tolist(),boundary=(lay.M@boundary).astype(int).tolist(),inventory=(lay.M@inventory).astype(int).tolist(),
            lane_inventory=inventory.tolist(),lane_queues=queue.tolist(),lane_boundary=boundary.tolist(),
            lane_queue_length_m=lengths.tolist(),lane_storage_capacity=plant.capacity,
            throughput=(lay.M@plant.served.sum(axis=1)).astype(int).tolist(),left_throughput=(lay.M@plant.served[:,1]).astype(int).tolist(),
            right_throughput=(lay.M@plant.served[:,2]).astype(int).tolist() if len(lay.movements)==3 else [0]*4,
            lane_throughput=plant.served.sum(axis=1).tolist(),delay_veh_s=plant.delay.sum(axis=1).tolist(),left_delay_veh_s=plant.delay[:,1].tolist(),model='idm'))
    for issue,h,forecast in issued:
        truth=lay.M@tape[issue:issue+h].sum(axis=(0,2))
        for i,name in enumerate(APPROACHES):errors.append(dict(issue_time_s=issue,horizon_s=h,approach=name,predicted=float(forecast[i]),actual=int(truth[i]),absolute_error_veh=float(abs(forecast[i]-truth[i]))))
    delay_error=plant.verify_delay(len(tape));assert delay_error<1e-5,delay_error
    approach_delay=plant.delay.sum(axis=1)
    offered=lay.M@plant.offered.sum(axis=1); served=lay.M@plant.served.sum(axis=1); avg=approach_delay/np.maximum(1,offered)
    left_offered=lay.M@plant.offered[:,1]; left_served=lay.M@plant.served[:,1]
    pet=plant.min_pet()
    lane_counts=[len(lay.roads[lay.road_of[a]]['lanes']) for a in range(4)]
    metrics=dict(scenario=scenario,seed=seed,controller=controller,model_version=VERSION,controller_version=VERSION,demand_id=f'{scenario}:{seed}:lanes{n}',
        lanes_per_approach=lane_counts[0] if len(set(lane_counts))==1 else None,total_delay_veh_s=float(approach_delay.sum()),throughput=int(served.sum()),max_queue_veh=int(maximum.max()),residual_veh=int(residual.sum()),
        max_queue_length_m=max_length,lane_storage_capacity=plant.capacity,max_queue_plus_boundary_veh=max_backlog,
        boundary_residual_veh=int(boundary.sum()),service_imbalance_s=float(avg.max()-avg.min()),conservation_error=max_error,fallback_decisions=fallback,
        delay_accounting_error=delay_error,collision_guard_corrections=plant.guards,red_crossings=plant.red_crossings,yellow_crossings=plant.yellow_crossings,
        min_gap_m=plant.min_gap if np.isfinite(plant.min_gap) else None,max_speed_mps=plant.max_speed,max_acceleration_mps2=plant.max_acc,
        min_acceleration_mps2=plant.min_acc,clearance_extensions_s=clearance_holds,
        left_delay_veh_s=float(plant.delay[:,1].sum()),through_delay_veh_s=float(plant.delay[:,0].sum()),
        left_offered_veh=int(left_offered.sum()),left_throughput=int(left_served.sum()),
        mean_left_delay_s=float(plant.delay[:,1].sum()/max(1,left_offered.sum())),
        mean_through_delay_s=float(plant.delay[:,0].sum()/max(1,plant.offered[:,0].sum())),
        protected_left_turns=plant.protected_lefts,permissive_left_turns=plant.permissive_lefts,
        min_permissive_left_pet_s=pet if np.isfinite(pet) else None,left_phase_skips=skipped if lefts_present else 0,
        arrow_green_s=int(arrow_s.sum()),arrow_with_through_ball_s=arrow_with_ball_s,dual_arrow_s=dual_arrow_s,fya_s=int(fya_s.sum()))
    for i,name in enumerate(APPROACHES):metrics.update({f'{name}_inbound_lanes':lane_counts[i],f'{name}_delay_veh_s':float(approach_delay[i]),f'{name}_throughput':int(served[i]),f'{name}_max_queue_veh':int(maximum[i]),
        f'{name}_residual_veh':int(residual[i]),f'{name}_offered_veh':int(offered[i]),f'{name}_left_delay_veh_s':float(plant.delay[i,1]),f'{name}_left_offered_veh':int(left_offered[i])})
    for m,movement in enumerate(MOVEMENTS):
        enabled=m<len(lay.movements); count=int(plant.offered[:,m].sum()) if enabled else 0
        delay=float(plant.delay[:,m].sum()) if enabled else 0.
        metrics.update({movement+'_offered_veh':count,movement+'_throughput':int(plant.served[:,m].sum()) if enabled else 0,
                        movement+'_delay_veh_s':delay,'mean_'+movement+'_delay_s':delay/max(1,count)})
    context=dict(intersection_id=lay.id,scenario=scenario,seed=seed,controller=controller,left_mode=lay.roads[0]['left_mode'],metrics_schema_version=1)
    context['run_id']=f'{lay.id}:{context["left_mode"]}:{scenario}:{seed}:{controller}'
    vehicles=list(plant.vehicles.values())
    for q in plant.pending:
        for uid,born,_ in q:plant.vehicles[uid]['delay_s']=len(tape)-born
    for cars in plant.cars:
        for v in cars:
            plant.vehicles[v.id].update(position_m=v.x,speed_mps=v.v)
            if v.x<0:plant.vehicles[v.id]['delay_s']=len(tape)-v.born-(v.x-plant.entry_x)/plant.p['desired_speed_mps']
    for row in vehicles:row.update(vehicle_uid=f'{context["run_id"]}:{row["vehicle_id"]}',observed_until_s=len(tape))
    movement_metrics=[]
    for ch,(a,lane,kind) in enumerate(lay.channels):
        for m,movement in enumerate(lay.movements):
            if not lay.allowed[ch,m]:continue
            records=[r for r in vehicles if r['approach']==APPROACHES[a] and r['lane_id']==lane+1 and r['movement']==movement]
            movement_metrics.append(dict(approach=APPROACHES[a],lane_id=lane+1,lane_kind=kind,movement=movement,
                outbound_approach=APPROACHES[EXITS[a][m]],offered_veh=int(plant.offered[ch,m]),throughput=int(plant.served[ch,m]),
                residual_veh=int(plant.offered[ch,m]-plant.served[ch,m]),boundary_residual_veh=int(plant.waiting[ch,m]),
                delay_veh_s=float(sum(r['delay_s'] for r in records)),outbound_entries=sum(r['outbound_entry_time_s'] is not None for r in records),
                exited_veh=sum(r['exit_time_s'] is not None for r in records),duration_s=len(tape)))
    intervals=[dict(vehicle_id=uid,approach=APPROACHES[a],movement=MOVEMENTS[m],permissive=accepted,enter_time_s=enter,clear_time_s=clear)
               for uid,(a,m,accepted,enter,clear) in plant.conflict_times.items()]
    for table in (vehicles,movement_metrics,intervals,plant.departures,observations,commands,forecasts,errors):
        for row in table:row.update(context)
    metrics.update(context)
    layout=dict(channels=[[APPROACHES[a],lane,kind] for a,lane,kind in lay.channels],modes=lay.mode,left_path_m=g['left_path_m'],right_path_m=g['right_path_m'])
    return metrics,dict(trace=trace,observations=observations,commands=commands,forecasts=forecasts,forecast_errors=errors,departures=plant.departures,
        vehicles=vehicles,movement_metrics=movement_metrics,conflict_intervals=intervals,
        motion=dict(dt_s=plant.dt,parameters=plant.p,layout=layout,tracks=list(plant.tracks.values())))

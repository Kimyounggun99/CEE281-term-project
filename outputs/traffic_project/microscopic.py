"""IDM intersection plant with physical lanes and closed-loop detector control."""
from collections import deque
from dataclasses import dataclass
import numpy as np
from forecast import predict
from simulation import Signal, step_signal, optimize, APPROACHES

VERSION='2.2.0'
# IDM city-traffic values from Treiber & Kesting, Traffic Flow Dynamics, Table 11.2.
DEFAULTS=dict(dt_s=.2,desired_speed_mps=15.,acceleration_mps2=1.,comfortable_braking_mps2=1.5,acceleration_exponent=4.,
              max_braking_mps2=6.,headway_s=1.,
              # Stop-or-go on yellow uses the ITE yellow-interval deceleration, not IDM's comfortable b,
              # so commitment distance v^2/(2*3) is covered within the 3 s yellow at 54 km/h.
              yellow_decision_braking_mps2=3.,minimum_gap_m=2.,vehicle_length_m=5.,
              approach_length_m=200.,intersection_length_m=24.,exit_distance_m=69.)


@dataclass
class Vehicle:
    id: int
    channel: int
    born: float
    x: float
    v: float
    committed: bool=False


class Plant:
    def __init__(self,c,lanes=2,detailed=False):
        self.p={**DEFAULTS,**c.get('idm',{})}; self.dt=self.p['dt_s']
        assert abs(round(1/self.dt)*self.dt-1)<1e-9
        self.lanes=lanes; self.c=c; self.detailed=detailed
        self.capacity=min(c['storage_veh'],int(self.p['approach_length_m']//(self.p['vehicle_length_m']+self.p['minimum_gap_m'])))
        if self.capacity<1:raise ValueError('Approach must store at least one vehicle with its standstill gap')
        self.entry_x=-self.p['approach_length_m']+self.p['vehicle_length_m']
        self.cars=[[] for _ in range(4*lanes)]; self.pending=[deque() for _ in self.cars]
        self.offered=np.zeros((4,lanes),int); self.served=self.offered.copy()
        self.delay=np.zeros(4); self.next_id=0; self.tracks={}; self.departures=[]
        self.guards=0; self.red_crossings=0; self.yellow_crossings=0
        self.last_label=None
        self.min_gap=float('inf'); self.max_acc=0.; self.min_acc=0.; self.max_speed=0.

    def add(self,counts,t):
        self.offered+=counts
        for ch,q in enumerate(self.pending):
            for _ in range(int(counts[ch//self.lanes,ch%self.lanes])):
                q.append((self.next_id,t)); self.next_id+=1

    def clear(self,phase):
        """Ideal virtual presence detector covering the full clearance zone."""
        return not any(0<=v.x<self.p['intersection_length_m']+self.p['vehicle_length_m']
                       for ch,cars in enumerate(self.cars) if (ch//self.lanes)//2==phase for v in cars)

    def counts(self):
        inventory=np.array([sum(v.x<0 for v in cars) for cars in self.cars]).reshape(4,self.lanes)
        queue=np.array([sum(v.x<0 and v.v<.5 for v in cars) for cars in self.cars]).reshape(4,self.lanes)
        boundary=np.array([len(q) for q in self.pending]).reshape(4,self.lanes)
        return inventory,queue,boundary

    def queue_lengths(self):
        return np.array([max((-v.x+self.p['vehicle_length_m'] for v in cars if v.x<0 and v.v<.5),default=0.)
                         for cars in self.cars]).reshape(4,self.lanes)

    def step(self,t,label):
        p=self.p; dt=self.dt; v0=p['desired_speed_mps']; length=p['vehicle_length_m']
        phase,stage=label.split(':'); phase=int(phase)
        yellow_started=stage=='yellow' and label!=self.last_label
        self.last_label=label
        for ch,cars in enumerate(self.cars):
            approach=ch//self.lanes; lane=ch%self.lanes
            active=approach//2==phase
            green=active and stage=='green'; yellow=active and stage=='yellow'
            if self.pending[ch] and sum(v.x<0 for v in cars)<self.capacity:
                gap=cars[-1].x-self.entry_x-length if cars else 1e6
                if gap>=p['minimum_gap_m']+.2:
                    uid,born=self.pending[ch].popleft()
                    # Largest entry speed whose IDM desired gap s*(v,v-lead) fits the gap: k v^2+(T-k lead)v-(gap-s0)=0.
                    k=1/(2*np.sqrt(p['acceleration_mps2']*p['comfortable_braking_mps2'])); h=p['headway_s']-k*(cars[-1].v if cars else v0)
                    speed=min(v0,(-h+np.sqrt(h*h+4*k*max(0,gap-p['minimum_gap_m'])))/(2*k))
                    v=Vehicle(uid,ch,born,self.entry_x,speed); cars.append(v)
                    if self.detailed:self.tracks[uid]=[uid,ch,round(t,5),[round(v.x,4)],[round(v.v,4)],born]
            self.delay[approach]+=len(self.pending[ch])*dt
            if not cars:continue
            x=np.array([v.x for v in cars]); speed=np.array([v.v for v in cars])
            gap=np.r_[1e6,x[:-1]-x[1:]-length]; lead_speed=np.r_[v0,speed[:-1]]
            blocked=np.zeros(len(cars),bool)
            for j,v in enumerate(cars):
                if green:v.committed=False
                leader_committed=j==0 or cars[j-1].x>=0 or cars[j-1].committed
                if yellow and yellow_started and v.x<0 and v.v>.5 and leader_committed and -v.x<=v.v*v.v/(2*p['yellow_decision_braking_mps2']):
                    v.committed=True
                blocked[j]=v.x<0 and not green and not(yellow and v.committed)
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
                    self.delay[approach]+=fraction*dt-min(distance,-x[j])/v0
                    if nx[j]>=0:
                        crossing=t+fraction*dt
                        self.served[approach,lane]+=1
                        self.red_crossings+=int(not(green or yellow)); self.yellow_crossings+=int(yellow)
                        self.departures.append(dict(vehicle_id=v.id,approach=APPROACHES[approach],lane_id=lane+1,
                            arrival_time_s=v.born,departure_time_s=crossing,delay_s=crossing-v.born+self.entry_x/v0,
                            speed_mps=float(nv[j]),signal_stage=stage))
                self.max_speed=max(self.max_speed,float(nv[j])); self.max_acc=max(self.max_acc,float(acc[j])); self.min_acc=min(self.min_acc,float(acc[j]))
                v.x=float(nx[j]);v.v=float(nv[j])
                if self.detailed:
                    self.tracks[v.id][3].append(round(v.x,4));self.tracks[v.id][4].append(round(v.v,4))
            self.cars[ch]=[v for v in cars if v.x<p['exit_distance_m']]

    def verify_delay(self,t):
        remaining=sum(t-born for q in self.pending for _,born in q)
        remaining+=sum(t-v.born-(v.x-self.entry_x)/self.p['desired_speed_mps'] for cars in self.cars for v in cars if v.x<0)
        return abs(sum(d['delay_s'] for d in self.departures)+remaining-self.delay.sum())


def run(arrivals,controller,scenario,seed,c,model,detailed=False):
    tape=arrivals[:,:,None] if arrivals.ndim==2 else arrivals
    lanes=tape.shape[2]; c=dict(c,lanes_per_approach=lanes); plant=Plant(c,lanes,detailed)
    signal=Signal(); history=[]; latest=-1; estimate=np.zeros(4); prior=1.8*sum(c.get('lane_demand_factors',[1.]*lanes))
    pred=np.full((6,4),prior); last_out=plant.served.copy(); pending=[]
    trace=[]; observations=[]; commands=[]; forecasts=[]; errors=[]; issued=[]
    maximum=np.zeros(4,int); max_error=0; fallback=0; clearance_holds=0
    max_length=0.; max_backlog=0
    for t in range(len(tape)):
        if t and t%10==0:
            missing=scenario=='detector_fault' and len(tape)*.4<=t<len(tape)*.65
            lag=30 if scenario=='delayed' else 0
            pending.append(dict(deliver=t+lag,end=t,missing=missing,inc=tape[t-10:t].sum(axis=0),
                out=plant.served-last_out,inventory=plant.offered-plant.served))
            last_out=plant.served.copy()
        for packet in list(pending):
            if packet['deliver']>t:continue
            pending.remove(packet); good=not packet['missing'] and t-packet['end']<=10
            for i,name in enumerate(APPROACHES):
                observations.append(dict(sensor_id=name,interval_start_s=packet['end']-10,interval_end_s=packet['end'],
                    delivery_time_s=t,count=None if packet['missing'] else int(packet['inc'][i].sum()),
                    departure_count=None if packet['missing'] else int(packet['out'][i].sum()),
                    mean_speed_mps=None,quality_flag='ok' if good else 'missing_or_stale'))
            if good:
                # Hardware cumulative entry/exit balance: total approach inventory, not simulator queues.
                estimate=packet['inventory'].sum(axis=1).astype(float); latest=t
                history.append(packet['inc'].sum(axis=1))
            else:history.append(np.mean(history[-3:],axis=0) if history else np.full(4,prior))
        if t%10==0 and controller=='mpc_transformer':
            # Only the MPC uses an arrival forecast (Transformer); fixed/responsive issue none.
            pred=predict(model,history,t,prior_count=prior)
            if t>=120 and t+60<=len(tape):
                for h in [30,60]:issued.append((t,h,pred[:h//10].sum(axis=0)))
            for i,name in enumerate(APPROACHES):forecasts.append(dict(issue_time_s=t,target_time_s=t+60,segment_id=name,
                estimated_state=float(estimate[i]),predicted_value=float(pred[:,i].sum()),variable_name='arrival_count',units='veh',quality='observed' if latest==t else 'imputed'))
        switch=False; reason='hold'; objective=None
        if t%c['decision_s']==0:
            stale=latest<0 or t-latest>10
            if controller=='fixed' or stale:
                switch=signal.elapsed>=c['fixed_green_s']; reason='fixed_plan' if controller=='fixed' else 'fallback_stale_observation'; fallback+=int(stale and controller!='fixed')
            elif controller=='responsive':
                sums=[estimate[:2].sum(),estimate[2:].sum()];switch=sums[1-signal.phase]>sums[signal.phase]+2;reason='opposing_inventory'
            else:switch,objective=optimize(estimate,signal,pred,c);reason='minimum_predicted_inventory_integral'
            commands.append(dict(issue_time_s=t,apply_time_s=t,actuator_id='intersection',action='request_switch' if switch else 'hold',value=int(switch),units='boolean',reason=reason,
                phase=signal.phase,stage=signal.stage,estimated_inventory=estimate.tolist(),objective_veh_s=objective))
        # Clearance interlock prevents releasing the conflicting direction before the rear clears.
        if signal.stage=='all_red' and signal.elapsed>=c['all_red_s']-1 and not plant.clear(signal.phase):
            signal.elapsed=c['all_red_s']-2; clearance_holds+=1
        _,label=step_signal(signal,switch,c)
        for sub in range(round(1/plant.dt)):plant.step(t+sub*plant.dt,label)
        plant.add(tape[t],t+1)
        inventory,queue,boundary=plant.counts(); residual=(inventory+boundary).sum(axis=1)
        maximum=np.maximum(maximum,queue.sum(axis=1))
        lengths=plant.queue_lengths();max_length=max(max_length,float(lengths.max()))
        max_backlog=max(max_backlog,int((queue+boundary).sum(axis=1).max()))
        assert np.max(inventory)<=plant.capacity
        assert lengths.max()<=plant.p['approach_length_m']+1e-8
        error=int(np.max(np.abs(plant.offered-plant.served-inventory-boundary)));max_error=max(max_error,error);assert error==0
        if detailed:trace.append(dict(time_s=t+1,phase=label,queues=queue.sum(axis=1).tolist(),boundary=boundary.sum(axis=1).tolist(),
            inventory=inventory.sum(axis=1).tolist(),lane_inventory=inventory.tolist(),lane_queues=queue.tolist(),lane_boundary=boundary.tolist(),
            lane_queue_length_m=lengths.tolist(),lane_storage_capacity=plant.capacity,
            throughput=plant.served.sum(axis=1).tolist(),lane_throughput=plant.served.tolist(),delay_veh_s=plant.delay.tolist(),model='idm'))
    for issue,h,forecast in issued:
        truth=tape[issue:issue+h].sum(axis=(0,2))
        for i,name in enumerate(APPROACHES):errors.append(dict(issue_time_s=issue,horizon_s=h,approach=name,predicted=float(forecast[i]),actual=int(truth[i]),absolute_error_veh=float(abs(forecast[i]-truth[i]))))
    delay_error=plant.verify_delay(len(tape));assert delay_error<1e-5,delay_error
    offered=plant.offered.sum(axis=1); served=plant.served.sum(axis=1); avg=plant.delay/np.maximum(1,offered)
    metrics=dict(scenario=scenario,seed=seed,controller=controller,model_version=VERSION,controller_version=VERSION,demand_id=f'{scenario}:{seed}:lanes{lanes}',
        lanes_per_approach=lanes,total_delay_veh_s=float(plant.delay.sum()),throughput=int(served.sum()),max_queue_veh=int(maximum.max()),residual_veh=int(residual.sum()),
        max_queue_length_m=max_length,lane_storage_capacity=plant.capacity,max_queue_plus_boundary_veh=max_backlog,
        boundary_residual_veh=int(boundary.sum()),service_imbalance_s=float(avg.max()-avg.min()),conservation_error=max_error,fallback_decisions=fallback,
        delay_accounting_error=delay_error,collision_guard_corrections=plant.guards,red_crossings=plant.red_crossings,yellow_crossings=plant.yellow_crossings,
        min_gap_m=plant.min_gap if np.isfinite(plant.min_gap) else None,max_speed_mps=plant.max_speed,max_acceleration_mps2=plant.max_acc,
        min_acceleration_mps2=plant.min_acc,clearance_extensions_s=clearance_holds)
    for i,name in enumerate(APPROACHES):metrics.update({f'{name}_delay_veh_s':float(plant.delay[i]),f'{name}_throughput':int(served[i]),f'{name}_max_queue_veh':int(maximum[i]),f'{name}_residual_veh':int(residual[i]),f'{name}_offered_veh':int(offered[i])})
    return metrics,dict(trace=trace,observations=observations,commands=commands,forecasts=forecasts,forecast_errors=errors,departures=plant.departures,
        motion=dict(dt_s=plant.dt,parameters=plant.p,tracks=list(plant.tracks.values())))

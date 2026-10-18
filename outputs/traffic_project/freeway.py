"""Common freeway foundation: synchronous IDM, arrivals, merge and metering."""
import numpy as np


def acceleration(v, gap, leader_v, v0=30., headway=1.5):
    desired = 2 + np.maximum(0, v*headway + v*(v-leader_v)/(2*np.sqrt(1.2*2.)))
    return 1.2 * (1-(v/v0)**4-(desired/np.maximum(gap,.01))**2)


def run_freeway(seed=101, dt=.25, controller='feedback', model='idm', duration=400, headway=1.5):
    rng = np.random.default_rng(seed)
    arrivals = rng.poisson([.30,.16], size=(duration,2))
    x, v, ids = np.array([]), np.array([]), np.array([],int)
    waiting = np.zeros(2,int)
    offered = exited = next_id = 0
    rate, tokens, occupancy = .25, 0., 0.
    trajectory, aggregates, observations, commands = [], [], [], []
    corrections, minimum_gap, waiting_delay, slow_delay = 0, float('inf'), 0., 0.
    crossing_count, crossing_speeds = 0, []
    for k in range(round(duration/dt)):
        t = k*dt
        if k % round(1/dt) == 0:
            a = arrivals[int(t)]
            waiting += a; offered += int(a.sum())
        if k and k % round(10/dt) == 0:
            measured = occupancy/10
            observations.append(dict(sensor_id='loop_400m', interval_start_s=t-10, interval_end_s=t,
                count=crossing_count, mean_speed_mps=float(np.mean(crossing_speeds)) if crossing_speeds else None,
                occupancy=measured, quality_flag='ok'))
            if controller == 'feedback':
                rate = float(np.clip(rate + .2*(.18-measured), .05, .4))
            else:
                rate = .25
            commands.append(dict(issue_time_s=t, apply_time_s=t, actuator_id='ramp_300m', action='release_rate',
                value=rate, units='veh/s', min_value=.05, max_value=.4, fallback=.25))
            occupancy, crossing_count, crossing_speeds = 0., 0, []
        tokens = min(1., tokens+rate*dt)
        # Merge only into a gap with enough room both upstream and downstream.
        for source, pos in [(0,0.), (1,300.)]:
            if not waiting[source] or (source == 1 and tokens < 1):
                continue
            ahead, behind = np.where(x>pos)[0], np.where(x<=pos)[0]
            lead = ahead[-1] if len(ahead) else None
            follow = behind[0] if len(behind) else None
            speed = min(15., v[lead]) if lead is not None else 15.
            forward_ok = lead is None or x[lead]-pos-5 > 2+speed*headway
            rear_ok = follow is None or pos-x[follow]-5 > 2+v[follow]*headway+max(0,v[follow]*(v[follow]-speed)/3)
            if forward_ok and rear_ok:
                x=np.append(x,pos); v=np.append(v,speed); ids=np.append(ids,next_id)
                next_id+=1; waiting[source]-=1
                order=np.argsort(-x); x,v,ids=x[order],v[order],ids[order]
                if source == 1:
                    tokens-=1
        gap=np.r_[1e6,x[:-1]-x[1:]-5] if len(x) else np.array([])
        lead_v=np.r_[30.,v[:-1]] if len(v) else np.array([])
        v0=np.where(x>=700,12.,30.)
        if model == 'idm':
            acc=acceleration(v,gap,lead_v,v0,headway)
        else:
            target=np.minimum(v0,np.maximum(0,(gap-2)/headway))
            acc=(target-v)/1.5
        acc=np.clip(acc,-8,1.2)
        new_v=np.maximum(0,v+acc*dt)
        dx=v*dt+.5*acc*dt*dt
        stopping=(v+acc*dt)<0
        dx[stopping]=-v[stopping]**2/(2*acc[stopping])
        new_x=x+dx
        for i in range(1,len(x)):
            if new_x[i] > new_x[i-1]-5-.1:
                new_x[i]=new_x[i-1]-5-.1; new_v[i]=min(new_v[i],new_v[i-1]); corrections+=1
        if len(x)>1:
            minimum_gap=min(minimum_gap,float(np.min(new_x[:-1]-new_x[1:]-5)))
        crossing=(x<400)&(new_x>=400)
        crossing_count+=int(crossing.sum()); crossing_speeds.extend(new_v[crossing].tolist())
        occupancy+=float(np.any((new_x>=400)&(new_x-5<=400)))*dt
        waiting_delay+=waiting.sum()*dt
        slow_delay+=float(np.sum(np.maximum(0,1-new_v/30)))*dt
        leave=new_x>=1000; exited+=int(leave.sum())
        x,v,ids=new_x[~leave],new_v[~leave],ids[~leave]
        assert offered==exited+len(x)+int(waiting.sum())
        if k % round(1/dt)==0:
            trajectory.extend(dict(time_s=t+dt,vehicle_id=int(i),lane_id='main',position_m=float(xx),speed_mps=float(vv)) for i,xx,vv in zip(ids,x,v))
            aggregates.append(dict(time_s=t+dt,main_boundary_veh=int(waiting[0]),ramp_boundary_veh=int(waiting[1]),
                vehicles=len(x),exited=exited,meter_rate_veh_s=rate))
    return (dict(seed=seed,dt_s=dt,controller=controller,model=model,headway_s=headway,offered=offered,
        throughput=exited,residual_veh=len(x)+int(waiting.sum()),boundary_residual_veh=int(waiting.sum()),
        delay_veh_s=float(waiting_delay+slow_delay),minimum_gap_m=minimum_gap,
        collision_guard_corrections=corrections,conservation_error=offered-exited-len(x)-int(waiting.sum())),
        dict(trajectory=trajectory,aggregates=aggregates,observations=observations,commands=commands))

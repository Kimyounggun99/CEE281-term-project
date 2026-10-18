"""Finite-storage FIFO queues with explicit upstream backlog and detector boundary."""
from collections import deque
from dataclasses import dataclass, replace
import numpy as np
import simpy
from forecast import predict

APPROACHES = ['N', 'S', 'E', 'W']
VERSION = '1.1.0'


@dataclass
class Signal:
    phase: int = 0
    stage: str = 'green'
    elapsed: int = 0


def step_signal(s, switch, c):
    """Return permission for [t,t+1), then advance the signal clock."""
    if s.stage == 'green' and ((switch and s.elapsed >= c['min_green_s']) or s.elapsed >= c['max_green_s']):
        s.stage, s.elapsed = 'yellow', 0
    permission = np.array([1, 1, 0, 0] if s.phase == 0 else [0, 0, 1, 1]) if s.stage == 'green' else np.zeros(4)
    label = f'{s.phase}:{s.stage}'
    s.elapsed += 1
    limit = c['yellow_s'] if s.stage == 'yellow' else c['all_red_s']
    if s.stage != 'green' and s.elapsed >= limit:
        s.elapsed = 0
        if s.stage == 'yellow':
            s.stage = 'all_red'
        else:
            s.stage = 'green'; s.phase = 1 - s.phase
    return permission, label


def optimize(q, signal, arrivals, c):
    """Beam search over feasible hold/switch sequences; fluid prediction model."""
    beam = [(0., q.copy(), replace(signal), False)]
    for k in range(0, c['forecast_horizon_s'], c['decision_s']):
        candidates = []
        for cost, queue, state, first in beam:
            actions = [False, True] if state.stage == 'green' and state.elapsed >= c['min_green_s'] else [False]
            for action in actions:
                s, qq, value = replace(state), queue.copy(), cost
                for j in range(c['decision_s']):
                    mask, _ = step_signal(s, action if j == 0 else False, c)
                    value += qq.sum()
                    qq = np.maximum(0, qq + arrivals[(k+j)//10]/10 - mask*c['saturation_veh_s']*c.get('lanes_per_approach',1))
                candidates.append((value, qq, s, action if k == 0 else first))
        beam = sorted(candidates, key=lambda x: x[0])[:c['beam_width']]
    return beam[0][3], float(beam[0][0])


def run(arrivals, controller, scenario, seed, c, model, detailed=False):
    lane_arrivals = arrivals[:,:,None] if arrivals.ndim==2 else arrivals
    lanes=lane_arrivals.shape[2]
    if lanes not in (1,2) or lane_arrivals.shape[1]!=4:
        raise ValueError('Expected arrival tape shape (seconds, 4, 1 or 2 lanes)')
    arrivals=lane_arrivals.sum(axis=2)
    c=dict(c,lanes_per_approach=lanes)
    factors=c.get('lane_demand_factors',[1.]*lanes)
    prior_count=1.8*(sum(factors) if len(factors)==lanes else lanes)
    queues, boundary = [deque() for _ in range(4)], [deque() for _ in range(4)]
    signal = Signal()
    estimate = np.zeros(4)
    history, observations, commands, forecasts, trace, departures = [], [], [], [], [], []
    pending = []
    count_in, count_out = np.zeros(4, int), np.zeros(4, int)
    detector_cumulative_in = np.zeros(4, int)
    delay, served, maximum = np.zeros(4), np.zeros(4, int), np.zeros(4, int)
    credit = np.zeros((4,lanes))
    lane_served = np.zeros((4,lanes),int)
    lane_count_out = np.zeros((4,lanes),int)
    latest, pred, objective = -1, np.full((6, 4), prior_count), None
    forecast_records = []
    uid, max_conservation_error, fallback_count = 0, 0, 0
    env = simpy.Environment()

    def loop():
        nonlocal estimate, count_in, count_out, latest, pred, uid, objective, max_conservation_error, fallback_count
        for t in range(len(arrivals)):
            # Publish completed detector intervals only. Controller never sees the demand tape.
            if t and t % 10 == 0:
                missing = scenario == 'detector_fault' and len(arrivals)*.4 <= t < len(arrivals)*.65
                lag = 30 if scenario == 'delayed' else 0
                packet = (t+lag, t, None if missing else count_in.copy(), None if missing else count_out.copy(), detector_cumulative_in.copy(), served.copy(),
                    lane_arrivals[t-10:t].sum(axis=0),lane_count_out.copy())
                lane_count_out[:]=0
                pending.append(packet)
                count_in, count_out = np.zeros(4, int), np.zeros(4, int)
            for packet in list(pending):
                delivery, end, inc, out, cumulative_in, cumulative_out, lane_in, lane_out = packet
                if delivery > t:
                    continue
                pending.remove(packet)
                good = inc is not None and t-end <= 10
                for i, name in enumerate(APPROACHES):
                    observations.append(dict(sensor_id=name, interval_start_s=end-10, interval_end_s=end,
                        delivery_time_s=t, count=None if inc is None else int(inc[i]),
                        departure_count=None if out is None else int(out[i]), mean_speed_mps=None,
                        lane_arrival_counts=None if inc is None else lane_in[i].tolist(),
                        lane_departure_counts=None if out is None else lane_out[i].tolist(),
                        quality_flag='ok' if good else ('missing' if inc is None else 'stale')))
                if good:
                    # Counter totals are hardware measurements; recover after a report dropout.
                    estimate = np.maximum(0, cumulative_in-cumulative_out).astype(float)
                    latest = t
                    history.append(inc)
                else:
                    # Missing intervals explicitly imputed, never backfilled using truth.
                    history.append(np.mean(history[-3:], axis=0) if history else np.full(4, prior_count))
            if t % 10 == 0 and controller == 'mpc_transformer':
                # Only the MPC uses an arrival forecast (Transformer); fixed/responsive issue none.
                pred = predict(model, history, t, prior_count=prior_count)
                if t >= 120 and t + 60 <= len(arrivals):
                    for h in [30, 60]:
                        forecast_records.append((t, h, pred[:h//10].sum(axis=0)))
                for i, name in enumerate(APPROACHES):
                    forecasts.append(dict(issue_time_s=t, target_time_s=t+60, segment_id=name,
                        estimated_state=float(estimate[i]), predicted_value=float(pred[:,i].sum()),
                        variable_name='arrival_count', units='veh', quality='observed' if latest == t else 'imputed'))
            stale = latest < 0 or t-latest > 10
            switch, reason = False, 'hold'
            if t % c['decision_s'] == 0:
                if controller == 'fixed' or stale:
                    switch = signal.elapsed >= c['fixed_green_s']
                    reason = 'fixed_plan' if controller == 'fixed' else 'fallback_stale_observation'
                    fallback_count += int(stale and controller != 'fixed')
                elif controller == 'responsive':
                    own = estimate[:2].sum() if signal.phase == 0 else estimate[2:].sum()
                    other = estimate[2:].sum() if signal.phase == 0 else estimate[:2].sum()
                    switch = other > own + 2
                    reason = 'opposing_queue_exceeds_current_by_2'
                else:
                    switch, objective = optimize(estimate, signal, pred, c)
                    reason = 'minimum_predicted_queue_integral'
                commands.append(dict(issue_time_s=t, apply_time_s=t, actuator_id='intersection', action='request_switch' if switch else 'hold',
                    value=int(switch), units='boolean', reason=reason, phase=signal.phase, stage=signal.stage,
                    green_elapsed_s=signal.elapsed, estimated_queue=estimate.tolist(), objective_veh_s=objective,
                    min_green_s=c['min_green_s'], max_green_s=c['max_green_s'], fallback='fixed_30s'))
            # Waiting during this interval is charged to everyone already waiting.
            delay[:] += [len(queues[i])+len(boundary[i]) for i in range(4)]
            mask, label = step_signal(signal, switch, c)
            credit[:] = np.where(mask[:,None], credit+c['saturation_veh_s'], 0)
            for i in range(4):
                for lane in range(lanes):
                    while credit[i,lane]>=1:
                        vehicle=next((v for v in queues[i] if v[2]==lane),None)
                        if vehicle is None: break
                        queues[i].remove(vehicle); credit[i,lane]-=1
                        vehicle_id,born,_=vehicle
                        served[i]+=1; lane_served[i,lane]+=1; count_out[i]+=1; lane_count_out[i,lane]+=1
                        if detailed:
                            departures.append(dict(vehicle_id=vehicle_id, approach=APPROACHES[i], lane_id=lane+1,
                                arrival_time_s=born, departure_time_s=t+1, delay_s=t+1-born))
                    if not any(v[2]==lane for v in queues[i]): credit[i,lane]=0
                    # Independent offered demand and finite storage in each lane.
                    for _ in range(int(lane_arrivals[t,i,lane])):
                        boundary[i].append((uid,t+1,lane)); uid+=1
                    occupied=sum(v[2]==lane for v in queues[i])
                    while occupied<c['storage_veh']:
                        vehicle=next((v for v in boundary[i] if v[2]==lane),None)
                        if vehicle is None: break
                        boundary[i].remove(vehicle); queues[i].append(vehicle); occupied+=1
                count_in[i] += arrivals[t,i]
                detector_cumulative_in[i] += arrivals[t,i]
            residual = np.array([len(queues[i])+len(boundary[i]) for i in range(4)])
            maximum[:] = np.maximum(maximum, residual)
            error = abs(uid-int(served.sum())-int(residual.sum()))
            max_conservation_error = max(max_conservation_error, error)
            assert error == 0
            if detailed:
                trace.append(dict(time_s=t+1, phase=label, queues=[len(q) for q in queues], boundary=[len(q) for q in boundary],
                    throughput=served.tolist(), delay_veh_s=delay.tolist(),
                    lane_queues=[[sum(v[2]==lane for v in q) for lane in range(lanes)] for q in queues],
                    lane_boundary=[[sum(v[2]==lane for v in q) for lane in range(lanes)] for q in boundary],
                    lane_throughput=lane_served.tolist()))
            yield env.timeout(1)
    env.process(loop()); env.run()
    residual = np.array([len(queues[i])+len(boundary[i]) for i in range(4)])
    # Reconstruct the exact finite-horizon delay independently from cohort timestamps.
    remaining_delay = sum(len(arrivals)-born for q in queues+boundary for _, born, _ in q)
    if detailed:
        assert abs(sum(x['delay_s'] for x in departures)+remaining_delay-delay.sum()) < 1e-8
    forecast_errors = []
    for issue, horizon, forecast in forecast_records:
        truth = arrivals[issue:issue+horizon].sum(axis=0)
        for i, name in enumerate(APPROACHES):
            forecast_errors.append(dict(issue_time_s=issue, horizon_s=horizon, approach=name, predicted=float(forecast[i]),
                actual=int(truth[i]), absolute_error_veh=float(abs(forecast[i]-truth[i]))))
    offered = arrivals.sum(axis=0)
    avg = delay / np.maximum(1, offered)
    metrics = dict(scenario=scenario, seed=seed, controller=controller, model_version=VERSION, controller_version=VERSION,
        demand_id=f'{scenario}:{seed}:lanes{lanes}', lanes_per_approach=lanes,total_delay_veh_s=float(delay.sum()), throughput=int(served.sum()),
        max_queue_veh=int(maximum.max()), residual_veh=int(residual.sum()), boundary_residual_veh=sum(map(len,boundary)),
        service_imbalance_s=float(avg.max()-avg.min()), conservation_error=max_conservation_error, fallback_decisions=fallback_count)
    for i, name in enumerate(APPROACHES):
        metrics.update({f'{name}_delay_veh_s':float(delay[i]), f'{name}_throughput':int(served[i]),
                        f'{name}_max_queue_veh':int(maximum[i]), f'{name}_residual_veh':int(residual[i]),
                        f'{name}_offered_veh':int(offered[i])})
    return metrics, dict(trace=trace, observations=observations, commands=commands, forecasts=forecasts,
                         forecast_errors=forecast_errors, departures=departures)

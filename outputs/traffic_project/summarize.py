"""Build a transparent result summary from saved experiment records."""
import csv
import json
from pathlib import Path
import numpy as np


def summarize(out):
    config=json.loads((out/'config_used.json').read_text(encoding='utf-8'))
    def read(name):
        with (out/name).open(encoding='utf-8') as f: return list(csv.DictReader(f))
    metrics=read('metrics.csv'); paired=read('paired_comparisons.csv'); forecasts=read('forecast_scores.csv'); freeway=read('freeway_metrics.csv')
    scenarios=list(dict.fromkeys(r['scenario'] for r in metrics))
    controllers=list(dict.fromkeys(r['controller'] for r in metrics))
    lines=['# Synthetic experiment results','',
        f'{len(metrics)} intersection runs. All results use synthetic data and are not field performance validation.', '',
        f"Entry lanes per approach: {config.get('lanes_per_approach',1)}. Per-lane demand factors: {config.get('lane_demand_factors',[1.0])}. Discharge rate and storage are per-lane values, and each lane's FIFO queue is computed independently.", '',
        '## Mean total delay [veh h]','',
        '| Scenario | '+' | '.join(controllers)+' |', '|---|'+'---:|'*len(controllers)]
    for scenario in scenarios:
        values=[np.mean([float(r['total_delay_veh_s'])/3600 for r in metrics if r['scenario']==scenario and r['controller']==c]) for c in controllers]
        lines.append('| '+scenario+' | '+' | '.join(f'{v:.3f}' for v in values)+' |')
    lines+=['','## Transformer MPC vs fixed: paired differences','',
            'Negative values mean less delay; positive values mean more delay. Intervals are 95% Student-t intervals, not corrected for multiple comparisons across scenarios.','',
            '| Scenario | Mean difference [veh h] | 95% CI [veh h] |','|---|---:|---|']
    for r in paired:
        if r['controller']=='mpc_transformer':
            ci=f"[{float(r['ci95_low'])/3600:.3f}, {float(r['ci95_high'])/3600:.3f}]" if r['ci95_low'] else 'Unavailable: one seed'
            lines.append(f"| {r['scenario']} | {float(r['mean_delay_difference_veh_s'])/3600:.3f} | {ci} |")
    lines+=['','## 60 s forecast count MAE [veh/approach/horizon]','',
            '| Scenario | Transformer |','|---|---:|']
    for scenario in scenarios:
        values=[np.mean([float(r['mae_veh']) for r in forecasts if r['scenario']==scenario and r['controller']==c and r['horizon_s']=='60']) for c in ['mpc_transformer']]
        lines.append('| '+scenario+' | '+' | '.join(f'{v:.3f}' for v in values)+' |')
    lines+=['','## Freeway foundation','',
            '| Controller/model | dt [s] | T [s] | Throughput | Residual | Delay [veh s] | Guard interventions |',
            '|---|---:|---:|---:|---:|---:|---:|']
    for r in freeway:
        lines.append(f"| {r['controller']}/{r['model']} | {r['dt_s']} | {r['headway_s']} | {r['throughput']} | {r['residual_veh']} | {float(r['delay_veh_s']):.1f} | {r['collision_guard_corrections']} |")
    base=next(r for r in freeway if r['controller']=='feedback' and r['model']=='idm' and r['dt_s']=='0.25' and r['headway_s']=='1.5')
    small=next(r for r in freeway if r['dt_s']=='0.125')
    relative=(float(small['delay_veh_s'])/float(base['delay_veh_s'])-1)*100
    lines+=['',f'Change in total delay for IDM dt 0.25 -> 0.125 s: {relative:+.2f}%. The discretization of occupancy measurement and merge acceptance timing also changes, so this is not a measure of pure ODE error alone.',
        '',f"Maximum conservation error across all intersection runs: {max(float(r['conservation_error']) for r in metrics):.0f} veh.",
        '', '## Scope of interpretation','',
        'Controllers are compared on matched demand realizations. The difference between MA and Transformer MPC can be read as a forecaster ablation, but the effects of the approximate search and the observation update interval remain. Check forecast error and delay together, and also report scenarios that did not improve.',
        '', 'Under oversaturation, always report boundary waiting and residual vehicles together. Delay is accumulated up to the end time and excludes post-end clearance delay. Verifying the signal rules is not a verification of real-road safety.',
        '', 'Connecting the supplied scaffold, manual video verification, per-member contribution and module-exchange records, and field-data validation are separate tasks.']
    if 'red_crossings' in metrics[0]:
        lines+=['','## IDM dynamics verification','',
            f"Maximum speed: {max(float(r['max_speed_mps']) for r in metrics)*3.6:.2f} km/h. Red entries: {sum(int(r['red_crossings']) for r in metrics)}.",
            f"Position guard interventions: {sum(int(r['collision_guard_corrections']) for r in metrics)}. Minimum net gap: {min(float(r['min_gap_m']) for r in metrics if r['min_gap_m']):.3f} m.",
            'Delay is free-flow-relative time loss, including boundary waiting. Committed yellow entries are permitted. All controllers, including fixed timing, share an occupancy-based all-red clearance interlock. Parameters and geometry remain educational assumptions, not field calibration.']
    if 'max_queue_length_m' in metrics[0]:
        lines+=['','## Physical queue storage','',
            f"Detector spacing: {config['idm']['approach_length_m']} m. Capacity: {metrics[0]['lane_storage_capacity']} vehicles per lane.",
            f"Largest observed stop-line-to-queue-tail distance: {max(float(r['max_queue_length_m']) for r in metrics):.3f} m.",
            'max_queue_veh excludes the outside reservoir. max_queue_plus_boundary_veh includes it. Excess demand is retained outside, never clipped or discarded. This admission constraint is not a guarantee that signal control can serve oversaturated demand.']
    (out/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__': summarize(Path(__file__).parent/'results')

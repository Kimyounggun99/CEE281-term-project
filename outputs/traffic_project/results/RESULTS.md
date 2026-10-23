# Synthetic experiment results

75 intersection runs. All results use synthetic data and are not field performance validation.

Entry lanes per approach: 2. Per-lane demand factors: [1.0, 1.0]. Discharge rate and storage are per-lane values, and each lane's FIFO queue is computed independently.

## Mean total delay [veh h]

| Scenario | fixed | responsive | mpc_transformer |
|---|---:|---:|---:|
| balanced | 35.892 | 39.559 | 21.111 |
| directional_shift | 48.846 | 49.472 | 34.339 |
| detector_fault | 35.892 | 37.613 | 24.728 |
| delayed | 35.892 | 35.892 | 35.892 |
| heavy | 212.337 | 205.819 | 190.560 |

## Transformer MPC vs fixed: paired differences

Negative values mean less delay; positive values mean more delay. Intervals are 95% Student-t intervals, not corrected for multiple comparisons across scenarios.

| Scenario | Mean difference [veh h] | 95% CI [veh h] |
|---|---:|---|
| balanced | -14.781 | [-19.326, -10.236] |
| directional_shift | -14.507 | [-18.119, -10.895] |
| detector_fault | -11.164 | [-14.924, -7.404] |
| delayed | 0.000 | [0.000, 0.000] |
| heavy | -21.778 | [-23.606, -19.949] |

## 60 s forecast count MAE [veh/approach/horizon]

| Scenario | Transformer |
|---|---:|
| balanced | 4.316 |
| directional_shift | 9.740 |
| detector_fault | 5.967 |
| delayed | 8.796 |
| heavy | 25.828 |

## Freeway foundation

| Controller/model | dt [s] | T [s] | Throughput | Residual | Delay [veh s] | Guard interventions |
|---|---:|---:|---:|---:|---:|---:|
| fixed/idm | 0.25 | 1.5 | 114 | 68 | 13068.9 | 0 |
| feedback/idm | 0.25 | 1.5 | 117 | 65 | 12403.4 | 0 |
| feedback/idm | 0.125 | 1.5 | 120 | 62 | 11771.3 | 0 |
| feedback/ovm | 0.25 | 1.5 | 128 | 54 | 9245.0 | 0 |
| feedback/idm | 0.25 | 2.0 | 105 | 77 | 14750.9 | 0 |

Change in total delay for IDM dt 0.25 -> 0.125 s: -5.10%. The discretization of occupancy measurement and merge acceptance timing also changes, so this is not a measure of pure ODE error alone.

Maximum conservation error across all intersection runs: 0 veh.

## Scope of interpretation

Controllers are compared on matched demand realizations. The difference between MA and Transformer MPC can be read as a forecaster ablation, but the effects of the approximate search and the observation update interval remain. Check forecast error and delay together, and also report scenarios that did not improve.

Under oversaturation, always report boundary waiting and residual vehicles together. Delay is accumulated up to the end time and excludes post-end clearance delay. Verifying the signal rules is not a verification of real-road safety.

Connecting the supplied scaffold, manual video verification, per-member contribution and module-exchange records, and field-data validation are separate tasks.

## IDM dynamics verification

Maximum speed: 54.00 km/h. Red entries: 0.
Position guard interventions: 0. Minimum net gap: 1.785 m.
Delay is free-flow-relative time loss, including boundary waiting. Committed yellow entries are permitted. All controllers, including fixed timing, share an occupancy-based all-red clearance interlock. Parameters and geometry remain educational assumptions, not field calibration.

## Physical queue storage

Detector spacing: 200.0 m. Capacity: 28 vehicles per lane.
Largest observed stop-line-to-queue-tail distance: 199.901 m.
max_queue_veh excludes the outside reservoir. max_queue_plus_boundary_veh includes it. Excess demand is retained outside, never clipped or discarded. This admission constraint is not a guarantee that signal control can serve oversaturated demand.

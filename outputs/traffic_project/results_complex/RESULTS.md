# Primary/secondary intersection case studies

180 intersection runs, 5 seeds, 900 s each. Synthetic demand only; not field validation.

## Layout

| Road | Approaches | Lanes (median to curb) | Left mode | Through factor/lane | Left factor | Right factor | Fixed through green [s] |
|---|---|---|---|---:|---:|---:|---:|
| primary | N/S | L T TR | protected_permissive | 0.8 | 0.3 | 0.15 | 30 |
| secondary | E/W | LT TR | permissive | 0.5 | 0.1 | 0.1 | 20 |

Signal: NEMA dual-ring, lead-lead lefts, barrier between the primary and secondary roads. Left arrows run concurrently with the opposing left or with the same-approach through. The flashing yellow arrow is tied to the opposing through green, so the yellow trap cannot occur. Lefts on the secondary road use a shared lane and yield to the opposing through.

## Main study (primary left mode: protected_permissive)

### Mean total delay [veh h]

| Scenario | fixed | responsive | mpc_transformer |
|---|---:|---:|---:|
| balanced | 48.04 | 44.25 | 39.70 |
| directional_shift | 61.52 | 53.28 | 48.89 |
| left_surge | 50.19 | 46.01 | 41.70 |
| detector_fault | 48.04 | 44.56 | 39.86 |
| delayed | 48.04 | 48.04 | 48.04 |
| heavy | 198.84 | 185.65 | 178.26 |

### Mean time loss per offered vehicle [s/veh]: left / through / right

Time loss includes outside waiting and stops at the analysis horizon. Unserved vehicles contribute partial time loss; these are not mean delays of completed trips. Read delay together with throughput and residual demand.

| Scenario | fixed | responsive | mpc_transformer |
|---|---|---|---|
| balanced | 141 / 157 / 149 | 92 / 152 / 131 | 229 / 114 / 111 |
| directional_shift | 153 / 171 / 162 | 94 / 154 / 151 | 243 / 118 / 120 |
| left_surge | 159 / 158 / 148 | 107 / 153 / 134 | 227 / 114 / 106 |
| detector_fault | 141 / 157 / 149 | 107 / 151 / 130 | 217 / 116 / 111 |
| delayed | 141 / 157 / 149 | 141 / 157 / 149 | 141 / 157 / 149 |
| heavy | 302 / 309 / 294 | 220 / 296 / 292 | 380 / 261 / 263 |

### Mean stop-line throughput / unserved at horizon [veh]

| Scenario | fixed | responsive | mpc_transformer |
|---|---|---|---|
| balanced | 768 / 347 | 766 / 349 | 808 / 307 |
| directional_shift | 759 / 555 | 830 / 484 | 860 / 454 |
| left_surge | 764 / 381 | 774 / 371 | 808 / 337 |
| detector_fault | 768 / 347 | 760 / 355 | 817 / 298 |
| delayed | 768 / 347 | 768 / 347 | 768 / 347 |
| heavy | 778 / 1550 | 868 / 1461 | 936 / 1392 |

### Paired total-delay difference vs fixed [veh h], 95% Student-t CI

| Scenario | Controller | Mean | 95% CI |
|---|---|---:|---|
| balanced | responsive | -3.78 | [-8.11, 0.54] |
| balanced | mpc_transformer | -8.34 | [-12.97, -3.71] |
| directional_shift | responsive | -8.24 | [-13.49, -2.99] |
| directional_shift | mpc_transformer | -12.62 | [-17.22, -8.03] |
| left_surge | responsive | -4.18 | [-9.63, 1.26] |
| left_surge | mpc_transformer | -8.49 | [-13.12, -3.86] |
| detector_fault | responsive | -3.48 | [-7.84, 0.88] |
| detector_fault | mpc_transformer | -8.18 | [-11.96, -4.39] |
| delayed | responsive | 0.00 | [0.00, 0.00] |
| delayed | mpc_transformer | 0.00 | [0.00, 0.00] |
| heavy | responsive | -13.18 | [-19.00, -7.36] |
| heavy | mpc_transformer | -20.57 | [-23.87, -17.27] |

### Left-turn signal usage (mean per run)

| Scenario | Controller | Arrow green [s] | Arrow with same-approach through [s] | Dual arrows [s] | Protected / permissive lefts | Left phases skipped | Min permissive PET [s] |
|---|---|---:|---:|---:|---|---:|---:|
| balanced | fixed | 223 | 0 | 112 | 68 / 30 | 0.0 | 2.25 |
| balanced | responsive | 294 | 36 | 119 | 89 / 25 | 1.0 | 1.04 |
| balanced | mpc_transformer | 153 | 14 | 64 | 46 / 26 | 0.0 | 1.34 |
| directional_shift | fixed | 223 | 0 | 112 | 69 / 30 | 0.0 | 2.25 |
| directional_shift | responsive | 326 | 32 | 138 | 106 / 23 | 0.8 | 1.03 |
| directional_shift | mpc_transformer | 138 | 3 | 66 | 40 / 25 | 0.0 | 1.34 |
| left_surge | fixed | 224 | 0 | 112 | 69 / 30 | 0.0 | 2.25 |
| left_surge | responsive | 319 | 47 | 123 | 101 / 24 | 0.8 | 1.04 |
| left_surge | mpc_transformer | 163 | 15 | 68 | 50 / 25 | 0.0 | 1.34 |
| detector_fault | fixed | 223 | 0 | 112 | 68 / 30 | 0.0 | 2.25 |
| detector_fault | responsive | 281 | 34 | 114 | 87 / 25 | 0.8 | 1.02 |
| detector_fault | mpc_transformer | 156 | 4 | 74 | 47 / 26 | 0.0 | 1.34 |
| delayed | fixed | 223 | 0 | 112 | 68 / 30 | 0.0 | 2.25 |
| delayed | responsive | 223 | 0 | 112 | 68 / 30 | 0.0 | 2.25 |
| delayed | mpc_transformer | 223 | 0 | 112 | 68 / 30 | 0.0 | 2.25 |
| heavy | fixed | 232 | 0 | 116 | 77 / 32 | 0.0 | 3.58 |
| heavy | responsive | 382 | 0 | 190 | 136 / 24 | 0.0 | 3.70 |
| heavy | mpc_transformer | 124 | 0 | 62 | 34 / 27 | 0.0 | 3.17 |

## Left-turn mode comparison (primary road)

Same demand tapes for every mode. Total delay [veh h] / mean left delay [s/veh] / left vehicles still unserved at the end.

| Scenario | Mode | fixed | responsive | mpc_transformer |
|---|---|---|---|---|
| balanced | permissive | 38.78 / 333 / 102 | 36.91 / 354 / 107 | 34.91 / 353 / 109 |
| balanced | protected | 44.45 / 158 / 47 | 41.80 / 93 / 26 | 35.79 / 267 / 81 |
| balanced | protected_permissive | 48.04 / 141 / 42 | 44.25 / 92 / 26 | 39.70 / 229 / 67 |
| left_surge | permissive | 41.23 / 309 / 141 | 39.00 / 330 / 150 | 37.16 / 326 / 148 |
| left_surge | protected | 46.65 / 173 / 86 | 43.77 / 109 / 55 | 37.70 / 254 / 119 |
| left_surge | protected_permissive | 50.19 / 159 / 80 | 46.01 / 107 / 53 | 41.70 / 227 / 103 |
| heavy | permissive | 187.48 / 412 / 236 | 170.67 / 425 / 243 | 166.63 / 430 / 246 |
| heavy | protected | 193.68 / 315 / 175 | 180.79 / 232 / 121 | 170.02 / 408 / 233 |
| heavy | protected_permissive | 198.84 / 302 / 167 | 185.65 / 220 / 115 | 178.26 / 380 / 214 |

## 60 s forecast count MAE [veh/approach/horizon]

| Scenario | Transformer |
|---|---:|
| balanced | 3.764 |
| directional_shift | 9.362 |
| left_surge | 4.336 |
| detector_fault | 5.076 |
| delayed | 6.719 |
| heavy | 20.567 |

## Verification over all runs

Conservation error: 0 veh. Red-light entries: 0. Collision-guard corrections: 0. Minimum net gap: 1.785 m. Max delay-accounting error: 6.89e-07 veh s.
Smallest post-encroachment time between a permissive left and opposing through/right traffic: 1.02 s.

## Saved interfaces

`movement_metrics.csv` contains one row per run, approach, lane and permitted movement. `*_seedN_vehicles.csv` preserves every offered vehicle, including boundary and upstream residuals, with a run-scoped vehicle UID, local link ports, exit direction, event times and partial time loss. `*_seedN_conflict_intervals.csv` records conflict-point occupancy. `schema.json` defines units, keys and censoring. `audit.json` independently reconciles these exports with every saved demand tape; rerun with `python audit_complex.py --results results_complex`.


## Scope of interpretation

Right turns share the through ball and FIFO curb lane; right turn on red is disabled. Permissive lefts conservatively yield to opposing rights as well as through vehicles, without assuming separate receiving lanes remove that conflict. Demand factors, 30 m left paths and 12 m right paths are illustrative assumptions. Turners retain the IDM desired speed. Left turners wait at the stop line rather than in the box. No pedestrians, lane changes, downstream receiving queues, or left-bay spillback into through lanes are modeled. Exports identify outbound flows but a future corridor simulator must implement downstream storage, travel time, spillback and vehicle handoff before intersections can interact. The MPC uses a lane-level fluid model with HCM-style permissive saturation flow and does not anticipate IDM start-up loss. Five seeds is pilot scale and no multiple-comparison correction is applied.

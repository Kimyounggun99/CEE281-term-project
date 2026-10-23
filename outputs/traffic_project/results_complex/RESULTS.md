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
| balanced | 49.61 | 50.87 | 45.13 |
| directional_shift | 62.65 | 60.95 | 56.09 |
| left_surge | 51.68 | 52.95 | 47.17 |
| detector_fault | 49.61 | 50.19 | 45.23 |
| delayed | 49.61 | 49.61 | 49.61 |
| heavy | 201.51 | 195.65 | 192.46 |

### Mean time loss per offered vehicle [s/veh]: left / through / right

Time loss includes outside waiting and stops at the analysis horizon. Unserved vehicles contribute partial time loss; these are not mean delays of completed trips. Read delay together with throughput and residual demand.

| Scenario | fixed | responsive | mpc_transformer |
|---|---|---|---|
| balanced | 152 / 162 / 152 | 98 / 175 / 157 | 210 / 136 / 138 |
| directional_shift | 162 / 174 / 163 | 101 / 177 / 172 | 217 / 144 / 148 |
| left_surge | 168 / 162 / 152 | 112 / 178 / 158 | 218 / 136 / 130 |
| detector_fault | 152 / 162 / 152 | 111 / 171 / 154 | 196 / 139 / 138 |
| delayed | 152 / 162 / 152 | 152 / 162 / 152 | 152 / 162 / 152 |
| heavy | 313 / 313 / 298 | 237 / 312 / 308 | 355 / 290 / 284 |

### Mean stop-line throughput / unserved at horizon [veh]

| Scenario | fixed | responsive | mpc_transformer |
|---|---|---|---|
| balanced | 748 / 367 | 720 / 395 | 761 / 354 |
| directional_shift | 744 / 571 | 760 / 554 | 795 / 519 |
| left_surge | 744 / 401 | 716 / 429 | 762 / 383 |
| detector_fault | 748 / 367 | 721 / 394 | 771 / 345 |
| delayed | 748 / 367 | 748 / 367 | 748 / 367 |
| heavy | 761 / 1568 | 790 / 1539 | 822 / 1507 |

### Paired total-delay difference vs fixed [veh h], 95% Student-t CI

| Scenario | Controller | Mean | 95% CI |
|---|---|---:|---|
| balanced | responsive | 1.25 | [-1.79, 4.30] |
| balanced | mpc_transformer | -4.48 | [-8.04, -0.93] |
| directional_shift | responsive | -1.69 | [-4.88, 1.50] |
| directional_shift | mpc_transformer | -6.56 | [-9.74, -3.38] |
| left_surge | responsive | 1.27 | [-1.70, 4.23] |
| left_surge | mpc_transformer | -4.51 | [-7.74, -1.28] |
| detector_fault | responsive | 0.57 | [-1.67, 2.82] |
| detector_fault | mpc_transformer | -4.39 | [-7.79, -0.98] |
| delayed | responsive | 0.00 | [0.00, 0.00] |
| delayed | mpc_transformer | 0.00 | [0.00, 0.00] |
| heavy | responsive | -5.86 | [-7.47, -4.25] |
| heavy | mpc_transformer | -9.05 | [-10.18, -7.93] |

### Left-turn signal usage (mean per run)

| Scenario | Controller | Arrow green [s] | Arrow with same-approach through [s] | Dual arrows [s] | Protected / permissive lefts | Left phases skipped | Min permissive PET [s] |
|---|---|---:|---:|---:|---|---:|---:|
| balanced | fixed | 246 | 0 | 123 | 79 / 13 | 0.0 | 2.54 |
| balanced | responsive | 306 | 35 | 124 | 92 / 18 | 0.6 | 2.01 |
| balanced | mpc_transformer | 157 | 4 | 72 | 56 / 21 | 0.0 | 1.71 |
| directional_shift | fixed | 243 | 0 | 121 | 79 / 14 | 0.0 | 2.54 |
| directional_shift | responsive | 329 | 28 | 143 | 104 / 20 | 0.6 | 2.67 |
| directional_shift | mpc_transformer | 146 | 0 | 72 | 53 / 20 | 0.0 | 2.68 |
| left_surge | fixed | 247 | 0 | 124 | 80 / 13 | 0.0 | 2.54 |
| left_surge | responsive | 331 | 45 | 130 | 104 / 18 | 0.6 | 2.67 |
| left_surge | mpc_transformer | 149 | 5 | 68 | 53 / 21 | 0.0 | 1.71 |
| detector_fault | fixed | 246 | 0 | 123 | 79 / 13 | 0.0 | 2.54 |
| detector_fault | responsive | 297 | 38 | 122 | 92 / 19 | 1.0 | 2.68 |
| detector_fault | mpc_transformer | 176 | 0 | 87 | 60 / 20 | 0.0 | 2.74 |
| delayed | fixed | 246 | 0 | 123 | 79 / 13 | 0.0 | 2.54 |
| delayed | responsive | 246 | 0 | 123 | 79 / 13 | 0.0 | 2.54 |
| delayed | mpc_transformer | 246 | 0 | 123 | 79 / 13 | 0.0 | 2.54 |
| heavy | fixed | 245 | 0 | 122 | 84 / 15 | 0.0 | 2.28 |
| heavy | responsive | 380 | 0 | 190 | 131 / 21 | 0.0 | 1.92 |
| heavy | mpc_transformer | 145 | 0 | 73 | 54 / 20 | 0.0 | 1.71 |

## Left-turn mode comparison (primary road)

Same demand tapes for every mode. Total delay [veh h] / mean left delay [s/veh] / left vehicles still unserved at the end.

| Scenario | Mode | fixed | responsive | mpc_transformer |
|---|---|---|---|---|
| balanced | permissive | 41.41 / 357 / 110 | 40.51 / 378 / 116 | 39.68 / 375 / 115 |
| balanced | protected | 48.60 / 162 / 47 | 47.97 / 103 / 30 | 41.43 / 234 / 71 |
| balanced | protected_permissive | 49.61 / 152 / 47 | 50.87 / 98 / 30 | 45.13 / 210 / 62 |
| left_surge | permissive | 43.83 / 327 / 149 | 42.73 / 343 / 155 | 41.64 / 341 / 154 |
| left_surge | protected | 50.72 / 177 / 86 | 50.14 / 119 / 61 | 43.46 / 237 / 113 |
| left_surge | protected_permissive | 51.68 / 168 / 85 | 52.95 / 112 / 57 | 47.17 / 218 / 105 |
| heavy | permissive | 191.47 / 428 / 245 | 182.95 / 436 / 250 | 181.65 / 431 / 246 |
| heavy | protected | 200.80 / 314 / 176 | 191.74 / 242 / 134 | 186.89 / 376 / 216 |
| heavy | protected_permissive | 201.51 / 313 / 176 | 195.65 / 237 / 123 | 192.46 / 355 / 201 |

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

Conservation error: 0 veh. Red-light entries: 0. Collision-guard corrections: 0. Minimum net gap: 1.993 m. Max delay-accounting error: 5.50e-07 veh s.
Smallest post-encroachment time between a permissive left and opposing through/right traffic: 1.27 s.

## Saved interfaces

`movement_metrics.csv` contains one row per run, approach, lane and permitted movement. `*_seedN_vehicles.csv` preserves every offered vehicle, including boundary and upstream residuals, with a run-scoped vehicle UID, local link ports, exit direction, event times and partial time loss. `*_seedN_conflict_intervals.csv` records conflict-point occupancy. `schema.json` defines units, keys and censoring. `audit.json` independently reconciles these exports with every saved demand tape; rerun with `python audit_complex.py --results results_complex`.


## Scope of interpretation

Right turns share the through ball and FIFO curb lane; right turn on red is disabled. Permissive lefts conservatively yield to opposing rights as well as through vehicles, without assuming separate receiving lanes remove that conflict. Demand factors, 30 m left paths and 12 m right paths are illustrative assumptions. Turners retain the IDM desired speed. Left turners wait at the stop line rather than in the box. No pedestrians, lane changes, downstream receiving queues, or left-bay spillback into through lanes are modeled. Exports identify outbound flows but a future corridor simulator must implement downstream storage, travel time, spillback and vehicle handoff before intersections can interact. The MPC uses a lane-level fluid model with HCM-style permissive saturation flow and does not anticipate IDM start-up loss. Five seeds is pilot scale and no multiple-comparison correction is applied.

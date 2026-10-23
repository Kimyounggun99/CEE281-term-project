# Complex intersection cross-examination

Checked 2026-10-21. The regenerated study uses primary L/T/TR and secondary LT/TR roads, synthetic demand, five paired seeds and a 900 s analysis horizon. Results below refer to the corrected model in `results_complex/`.

## Logic review and correction

The dual-ring phase sequence, protected/permissive left modes, detector fallback and through-only legacy behavior are retained. Right turns use the through ball and existing yellow commitment rule, with no right turn on red. Shared lanes retain FIFO order. Permissive lefts yield to opposing through and right traffic. Right turns take the correct exit road and participate in clearance holds.

The audit found a real pre-existing clearance defect. A left could accept a gap during yellow while still upstream, cross during all-red, and remain in the box when a conflicting protected movement started. The original interlock only considered vehicles already beyond the stop line. It now also waits for accepted upstream lefts. A failing regression reproduced this directly and in a primary/primary closed loop; both pass after the correction. Zero red-entry and collision-guard counters alone had missed this case.

The tests cover primary/primary, primary/secondary, secondary/primary and secondary/secondary layouts with all three controllers. The original through-only fixed/responsive model still matches exactly. Mixed-layout lane metadata now reports 3/3/2/2 explicitly instead of incorrectly reporting two lanes for every approach.

## Evidence

- `./run_project.sh --test`: **39 tests passed**.
- `./run_project.sh --cases --workers 8`: **180 experiments regenerated**, including all left-mode comparisons.
- `python audit_complex.py --results results_complex`: **259,659 vehicle records**, **36 detailed traces**, **24 trajectory sets** reconciled against saved demand tapes.
- Independent checks cover lane/movement counts, routing, event order, censoring, time loss, paired inputs, storage, signals, same-lane separation, motion bounds, conflict occupancy/PET and protected-movement clearance.
- All **72 paired comparison rows**, including their Student-t confidence intervals, were recomputed from `metrics.csv`. The delayed-detector scenario reproduces fixed-plan metrics for every seed, as expected from stale-observation fallback.
- Across the full study: conservation error **0**, recorded red entries **0**, collision-guard corrections **0**, maximum delay reconciliation error **5.50e-7 vehicle seconds**, minimum net lane gap **1.993 m**, minimum permissive-left PET against opposing through/right traffic **1.27 s**.
- Both regenerated comparison plots were visually inspected. The Node replay check passed all **24 selections** and **1,355 completed right-turn paths**, plus counts and playback; browser canvas rasterization was not checked.
- Independent source review found and resolved two additional edges: the replay CLI now selects its template from the saved model layout, and invalid movement paths/conflict points outside the observed domain are rejected before simulation. Focused regressions cover both; the supplied study geometry and replay template are unchanged.

## What the results support

Main study, primary left mode protected/permissive; means over the same five demand seeds. Time loss includes partial waiting by vehicles unserved at the horizon.

| Scenario | Fixed total loss [veh h] | MPC total loss [veh h] | MPC change | Fixed left loss [s/offered veh] | MPC left loss [s/offered veh] |
|---|---:|---:|---:|---:|---:|
| Balanced | 49.61 | 45.13 | -9.04% | 152 | 210 |
| Directional shift | 62.65 | 56.09 | -10.47% | 162 | 217 |
| Left surge | 51.68 | 47.17 | -8.73% | 168 | 218 |
| Detector fault | 49.61 | 45.23 | -8.84% | 152 | 196 |
| Delayed | 49.61 | 49.61 | 0.00% | 152 | 152 |
| Heavy | 201.51 | 192.46 | -4.49% | 313 | 355 |

MPC improves aggregate loss in the five non-delayed scenarios while worsening left-turn service. For balanced demand, mean unserved left vehicles increase from **46.8 to 61.8**. In heavy traffic, MPC still leaves about **1,507 unserved vehicles**, versus **1,568** under fixed timing. A lower aggregate objective is therefore not evidence of uniformly better service or resolution of oversaturation. Permissive-only lefts also have substantially higher left-turn loss than protected modes despite sometimes lower aggregate loss. Five seeds and unadjusted confidence intervals remain pilot-scale evidence.

The new demand includes additional right turns and corrected clearance. Controller comparisons within this regenerated study use matched tapes; numerical changes from the earlier model are not a controlled comparison of model versions.

## Saved interfaces and limits

`movement_metrics.csv` and per-seed vehicle journals preserve every offered vehicle, lane/movement counts, residual and external demand, partial loss, local inbound/outbound ports and exit directions. Timestamps distinguish admission, stop-line crossing, receiving-link entry, rear clearance and local-domain exit. `schema.json` defines keys, units and censoring; stop-line throughput does not remove a vehicle from downstream accounting.

These are inputs to future network work. A coupled simulator must still preserve vehicle identity across handoffs and implement shared link storage, receiving capacity, travel time and spillback. Downstream vehicles currently retain simplified inbound-lane leader following. Turning speeds, conflict points and demand factors are illustrative assumptions; pedestrians, lane changes, field calibration and a real-browser rendering check remain outside this verification.

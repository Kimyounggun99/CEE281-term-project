# Verification record

## v2.2 moving-average removal

- 18 unit tests passed. The future-arrival isolation test now runs `mpc_transformer`; the detector-recovery test checks observation quality because `responsive` issues no forecasts.
- Quick runs before and after the change gave identical metrics for `fixed`, `responsive` and `mpc_transformer` and identical Transformer forecast scores.
- Saved results were reduced to 75 metric records and 15 detailed traces; the saved-output audit passed. `replay.html` was rebuilt with three controllers (rebuild checked byte-identical to `build_replay.py` output on a quick run) and the storage and IDM replay checks passed.

## v2.1 storage verification

- 18 unit tests passed, including sustained red with 80 offered vehicles per lane on a 200 m approach: approximately 30 can queue internally, overflow is retained, and every admitted rear bumper remains inside the boundary.
- All 100 intersection experiments and 5 freeway runs regenerated. Saved-output audit passed for 100 metric records and 20 detailed traces, including capacity, queue extent, vehicle-body boundary, conservation, dynamics and clearance checks.
- Largest recorded queue extent: 199.971121 m, below the 200 m detector spacing. Maximum internal stopped count was 60 per approach; lane inventory never exceeded 30. No positional guard interventions occurred.
- Browser checks confirmed 200 m spacing, nonblank canvas, overview and zoom rendering, and no JavaScript errors or mobile horizontal overflow. Queue counts exclude the outside reservoir; delay still includes it. This is admission control, not a guarantee against external spillback under oversaturation.

## v2.0 IDM verification

- 17 unit tests passed, including free-flow green passage without detector braking, red stopping and bounded restart, closed-loop accounting, time-step sensitivity, and the late-yellow reacceleration regression.
- Recomputed all 100 intersection experiments and 5 freeway comparisons. The independent audit passed for all 100 metric records and 20 detailed traces. Across the intersection study: zero positional guard interventions, zero red entries, minimum same-lane bumper gap 1.9929 m, maximum speed 10 m/s, and maximum independent delay-accounting error 1.75e-7 vehicle-seconds.
- The saved-output audit now checks position increments against recorded speeds, in addition to speed and acceleration bounds, independent cohort delay accounting, conservation and conflicting-phase clearance. Any positional guard intervention fails the audit.
- The renderer uses stored physical positions and speeds at 0.2 s intervals, not prescribed approach/discharge animations. Default playback is 1x; desired speed is 15 m/s (54 km/h) from v3.2 (10 m/s before).
- Final Playwright/Edge checks inspected 20,716 tracks, including 275 steady-speed and 19,492 accelerating stop-line crossings. Playback advanced, departing vehicles were present, and there were no JavaScript errors or mobile horizontal overflow. Desktop 1280x1050 and mobile 390x844 screenshots were inspected.
- This is an educational synthetic-demand model, not field validation. There are no turns, pedestrians, lane changes or downstream blockage. MPC remains a fluid approximation to the IDM plant.

The verification and illustrative-animation limitations below concern legacy versions, not the current physical-trajectory renderer.

## v1.1 two-lane verification

- 12 unit tests passed, including independent two-lane saturation service and no capacity transfer from an empty lane.
- Retrained the Transformer and completed all 100 intersection experiments with independent two-lane demand; regenerated comparisons, traces and replay.
- Saved-output audit passed for 100 metric records and 20 detailed traces, including lane-specific conservation and storage limits.
- Browser checks found all eight inbound lanes visible, 27,905 discharge events beginning in compatible green, and 1,071 unqueued green crossings without a detector stop. No JavaScript errors or mobile horizontal overflow were found. Desktop and mobile screenshots were visually inspected.

Earlier verification notes below describe the previous single-lane implementation.

Green-flow animation regression: 796 unqueued green-arrival examples across all 20 replays retained continuous positions of -20, -10, 0 and +10 drawing units around the detector crossing. All 14,257 discharge animations still begin in compatible green intervals. Rolling queue followers now interpolate over their actual discharge headway instead of reaching the detector early and waiting there.

Executed on 2026-10-12. Runtime versions are in `results/versions.json`.

- 10 unittest checks passed, including future-demand isolation and exact saturated discharge.
- Full study completed: 100 intersection runs and 5 freeway comparisons.
- Independent saved-output audit passed for all 100 metrics records and 20 full first-seed traces: per-step conservation, delay integration, storage bounds and phase durations.
- All intersection conservation errors were zero. All five freeway runs had zero collision-guard interventions and zero conservation error.
- Playwright/Edge desktop 1280x1000 and mobile 390x844 checks passed: no JavaScript errors, no horizontal overflow, nonblank canvas, time advanced from 241 to 246 seconds while playing, scenario/controller selection updated the replay.
- Desktop/mobile screenshots and representative intersection/freeway plots were visually inspected.

Numerical limitation: reducing the freeway integration step from 0.25 to 0.125 seconds changed measured delay by -5.10%. This is sensitivity evidence, not a convergence certificate. Merge acceptance and sampled loop occupancy contribute to that difference.

The animation represents recorded queue states, not a microscopic intersection trajectory model. No field validation, manual video audit, peer exchange or student contribution certification has been performed.

Visualization update: approaching and departing vehicles now move continuously, with gray departing vehicles and labeled arrival/stop-line loops. All 14,257 recorded discharge events across 20 detailed replays were checked to begin animation in a compatible green interval. Playwright confirmed fractional-time vehicle movement, visible outbound vehicles, desktop/mobile rendering, no horizontal overflow and no JavaScript errors. These are illustrative trajectories derived from FIFO events, not new simulated driving dynamics.

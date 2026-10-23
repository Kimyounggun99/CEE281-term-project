# CEE 281: Adaptive Traffic Signal Control

## v3.1: left, through and right movements

The current `--cases` layout has primary N/S roads with **L T TR** lanes and secondary E/W roads with **LT TR** lanes, from median to curb. L is left only, T is straight only, LT is left/straight, and TR is straight/right. A vehicle retains its movement and lane; shared lanes use FIFO service, so vehicles cannot pass a waiting turner.

The v3.0 dual-ring sequence is retained. Right turns use the through ball, including the existing yellow commitment rule; right turn on red is disabled. A permissive left yields to opposing through **and right** vehicles. Opposing right/left merges are treated conservatively as conflicts even when separate outbound lanes could accommodate both. All-red holds include right-turn occupants and already-accepted lefts still approaching the stop line; the latter fixes a late-entry clearance bug found during cross-examination. The replay draws right turns to the curb lane of the correct exit road.

`right_factor` is total right demand per approach, distributed over permitted right-turn lanes. Defaults `.15` on primary and `.1` on secondary roads are illustrative synthetic assumptions, as are the 12 m right-turn path and 6 m conflict-point distance. Through demand remains `.8` per primary through-capable lane and `.5` per secondary through-capable lane; right demand is additional. Turners keep the existing IDM speed model; turning-speed reduction, pedestrians, lane changes and downstream receiving queues are not modeled.

From this directory:

```bash
./run_project.sh --test
./run_project.sh --cases --quick          # 360 s, one seed -> results_complex_quick/
./run_project.sh --cases --workers 4      # 900 s, five seeds -> results_complex/
xdg-open results_complex/replay.html     # macOS: open instead of xdg-open
.venv/bin/python audit_complex.py --results results_complex
node ../../work/verify_complex_replay.cjs # embedded replay behavior; no browser needed
```

Both study commands train the forecaster, simulate all three controllers and build the HTML animation automatically. For a replay-only rebuild of saved complex trajectories:

```bash
.venv/bin/python build_replay.py --results results_complex
```

### Metrics and future road networks

`metrics.csv` retains aggregate and per-approach results and adds separate through/left/right demand, throughput and time loss. `N_inbound_lanes` through `W_inbound_lanes` describe the mixed layout; `lanes_per_approach` is blank when approaches have different lane counts. `movement_metrics.csv` contains each run's lane/movement counts, stop-line throughput, residual and outside demand, time loss, receiving-link entries and exits.

Every seed and controller also saves `*_seedN_vehicles.csv`, `*_seedN_movement_metrics.csv` and `*_seedN_conflict_intervals.csv`. Vehicle records include `intersection_id`, `run_id`, a run-scoped `vehicle_uid`, inbound/outbound link ports, origin/exit compass legs, lane, movement, offered/admitted/stop-line/outbound-entry/junction-clear/domain-exit times, final observed position/speed and status. Blank event times mean the event was not observed before `observed_until_s`. Vehicles still outside or upstream remain in the journal and contribute partial time loss. Delay is per offered vehicle at the finite horizon, not mean delay of completed trips.

`schema.json` defines keys, units and event boundaries. Local ports such as `intersection_1:W:out` can later map to another intersection's inbound port; `outbound_entry_time_s` records when the front reaches that receiving link. Movement paths and rear clearance must fit inside the configured exit boundary; invalid geometry is rejected before simulation. A network simulator must still implement shared link storage, downstream capacity, travel time, spillback and vehicle handoff. Independent runs do not yet interact through these exports.

`audit_complex.py` reads saved input tapes and exports independently, checks every offered vehicle and movement count, reconstructs time loss and censoring, checks exit routing and event order, verifies paired inputs, and checks conflict occupancy/PET against opposing through/right traffic. First-seed traces and available trajectories also check conservation, storage, signal conflicts, speed/acceleration bounds and clearance before protected movements. The Node check exercises replay selection, counts, playback and right-turn exit geometry; it does not rasterize a browser canvas.

The following v3.0 section records the earlier through/left-only configuration.

## v3.0: primary/secondary roads with left-turn lanes

`intersection.py` generalizes the IDM plant and the signal. Each road in the `intersection` block of `config_complex.json` lists its lanes from the median outward (`L` exclusive left, `T` through, `LT` shared) and a primary-road `left_mode`:

- `permissive`: no arrow. Lefts turn on the green ball or the flashing yellow arrow (FYA), yielding to oncoming traffic.
- `protected`: lefts turn on the green arrow only.
- `protected_permissive`: green arrow, then FYA. This mode needs an exclusive `L` lane, as does `protected`.

The default case has the primary N/S road with `L T T` and the secondary E/W road with `LT T`.

**Signal.** A NEMA dual-ring, lead-lead controller with a barrier between the two roads. Ring 1 runs SB-left then NB-through (φ1→φ2), and ring 2 runs NB-left then SB-through (φ5→φ6). The allowed concurrent pairs are 1+5, 1+6, 2+5 and 2+6, so a left arrow can show alongside the opposing left or alongside its own approach's through ball. Both rings cross the barrier together.

**Left-turn rules.**
- The FYA is tied to the *opposing* through green, which prevents the yellow trap.
- A permissive turner accepts a gap only if every oncoming through vehicle needs longer than both the HCM critical headway (4.5 s) and the turner's own time to clear the conflict point plus 1 s.
- During the opposing yellow, oncoming vehicles that will stop are ignored (sneakers).
- Left phases are called, skipped and gapped out by 12-m stop-bar presence loops. The pretimed `fixed` plan always serves lefts.
- The all-red interlock holds until no vehicle conflicting with the next movements is in the box.

**MPC.** It optimizes per-ring "end left arrow" and "cross barrier" decisions with a lane-level fluid model. Permissive service uses the HCM gap-acceptance flow `v e^{-v tc}/(1-e^{-v tf})` with the plant's effective gap.

**Running.** `./run_project.sh --cases` runs 6 scenarios (adding `left_surge`, which triples the N-approach left demand from 450 s) plus a left-mode comparison on the same demand tapes, and writes to `results_complex/`. `--quick` writes to `results_complex_quick/`. `results_complex/replay.html` animates turning paths, arrows and the FYA.

**Legacy equivalence.** With the legacy through-only layout, `intersection.run` reproduces `microscopic.run` metric for metric (`test_intersection.py`), so the v2.x study in `results/` is unchanged. `test_intersection.py` also checks:
- the signal never shows conflicting greens;
- the FYA appears only while the opposing through is green;
- interval lengths are correct;
- uncalled lefts are skipped;
- protected-only lefts never turn on the ball;
- permissive turners wait for gaps;
- conservation, red entries and PET hold in closed loop.

**Not modeled:** right turns, pedestrians, lane changes, left-bay spillback, turning-speed reduction, and turners waiting inside the box.

## v2.2: moving-average forecasting removed

The moving-average (MA) forecast and the `mpc_ma` controller were removed. The study now compares three controllers: `fixed`, `responsive` and `mpc_transformer`. Only `mpc_transformer` issues arrival forecasts; `fixed` and `responsive` do not, so they no longer write `_forecasts.csv` / `_forecast_errors.csv`, and `forecast_scores.csv` contains Transformer scores only. Results for the remaining controllers are unchanged, so the saved `results/` were updated by dropping the `mpc_ma` records rather than rerunning. Two non-MA-controller uses of averaging remain by design: before 12 intervals of history exist (first 120 s) the Transformer forecaster returns the mean of the observed history, and a missing detector interval is imputed with the mean of the last three intervals.

## v2.1: 200m detector spacing and physical storage

The arrival loop is 200 m upstream of the stop-line loop. Each approach has two lanes, with at most 30 admitted upstream vehicles per lane (60 per approach). Effective capacity is `min(storage_veh, floor(approach_length_m / (vehicle_length_m + minimum_gap_m)))`. At the default 4.5 m vehicle length and 2 m standstill gap, 30 stopped vehicles require approximately 195 m. The 200 m geometry is an educational choice, not a site-specific design recommendation.

Admission places the full vehicle body inside the detector boundary and checks available leader gap. Queue length is measured from the stop line to the rear bumper of the furthest stopped vehicle (speed below 0.5 m/s), independently per lane, and must remain within 200 m. All upstream inventory, including moving vehicles, is limited by the storage cap. Excess demand waits in the external reservoir and is included in delay and conservation. This is a physical admission constraint, not proof that the signal optimizer can prevent external spillback under oversaturation.

`max_queue_veh` now means maximum internal stopped count per approach, excluding the reservoir. `max_queue_plus_boundary_veh` preserves the combined backlog measure. `max_queue_length_m` is the maximum single-lane physical queue extent. Traces include `lane_queue_length_m` and `lane_storage_capacity`. The replay shows internal queues and meter extents separately from Outside counts; Zoom changes only the camera, not vehicle speed. Change `idm.approach_length_m` and `storage_veh` in `config.json`, then rerun to test other storage lengths. The shorter 45 m geometry described below belongs to v2.0.

## IDM intersection model (v2.0)

The default run now uses the IDM car-following model in `microscopic.py`. The earlier integer-queue model `simulation.py` is kept for previous versions and for the shared signal/MPC functions. Detectors do not change vehicle speed. Acceleration and deceleration are determined by the distance and relative speed to the leader and by the red stop line. In the `idm` block of `config.json` you can adjust the desired speed of 10 m/s (36 km/h), acceleration 1.2 m/s², comfortable deceleration 2 m/s², maximum deceleration 6 m/s², time headway 1.5 s, minimum gap 2 m, and vehicle length 4.5 m. The integration step is 0.2 s; the display only interpolates linearly between trajectory samples. Playback defaults to 1x, and vehicles keep the same dynamics after they exit.

Each direction has two lanes, a 45 m approach, and 24 m between stop lines. 30 vehicles per lane is an upper limit; actual storage is further limited by vehicle length, gap and road length. When there is no room to enter, vehicles are retained in an external queue. A vehicle that cannot stop comfortably on yellow may continue into the intersection, and all-red is extended until a virtual intersection-occupancy detector confirms that the box is clear. Actual clearance can therefore be longer than the nominal per-signal clearance.

Evaluated delay is **time loss: the actual elapsed time to the stop line minus the time needed to cover that distance at free-flow speed**, and it includes external waiting time. The on-screen Queue counts stopped vehicles (speed below 0.5 m/s); conservation accounting uses `inventory`, which also includes moving vehicles. A stop-line crossing is counted as the event where the actual position passes 0 m, not as a fixed service credit. The forecaster is retrained on separate synthetic data, and signal control is rerun against the new IDM vehicle observations. The MPC's internal prediction is still a simple fluid inventory model, so it cannot fully anticipate IDM start-up loss, lane imbalance or travel time.

The track format in `*_motion.json` / `replay_motion.json` is `[vehicle_id, channel, entry_time_s, positions_m[], speeds_mps[], offered_time_s]`. Position is the front bumper, with the stop line at 0 m and downstream positive. `replay.html` embeds the compressed actual trajectories and metrics, so it opens without a server. `python3 -m unittest test_microscopic -v` checks free-flow green passage without stopping, red stop/restart, vehicle conservation and delay accounting, and time-step sensitivity.

The IDM equations and integration scheme follow [the model author's description](https://traffic-simulation.de/info/info_IDM.html). Parameters and intersection dimensions are educational assumptions and have not been calibrated against field measurements. The v1.x descriptions below of fixed discharge, point-queue delay and schematic motion apply only to the earlier model.

## Two-lane demand per direction (v1.1)

Each direction has two independent through entry lanes. In `config.json`, `lanes_per_approach: 2` and `lane_demand_factors: [1.0, 1.0]` apply the former single-lane demand to each lane, doubling the mean total demand per direction. The two lanes of the same direction also generate independent Poisson arrivals. To keep the former per-direction total demand and split it between the two lanes, change the factors to `[0.5, 0.5]` and rerun. Different per-lane demand can also be specified, e.g. `[1.0, 0.7]`.

`storage_veh: 30` and `saturation_veh_s: 0.5` are **per-lane** values. Storage per direction is 60 vehicles, and the total discharge capacity when both lanes are saturated is 1 veh/s. There is no lane changing or capacity transfer between lanes. The controllers and forecaster use per-direction aggregate observations, so the MPC cannot accurately predict capacity loss caused by lane imbalance.

`lane_demand_*.npy` is indexed `[time, approach, lane]`; the existing `demand_*.npy` holds per-direction totals. Detailed traces add `lane_queues`, `lane_boundary` and `lane_throughput`, and departure records use `lane_id` 1 or 2. Queue numbers in the replay are shown as `lane 1 / lane 2`. A/D detectors are shown for each lane, and the signal phase is shared per direction. The per-lane definitions in this section take precedence over the demand and capacity figures in the initial single-lane design description below.

This is a runnable research simulation built from the guidelines and the proposal. It uses **synthetic data and a self-built intersection scaffold**. The instructor-provided scaffold, field traffic counts and video were not attached, so integration with those materials, calibration against them and manual video verification have not yet been done.

## Running (macOS)

Requires Python 3.9 or later (tested with 3.9 and 3.13; the Xcode Command Line Tools Python 3.9 works). On a fresh Mac, `/usr/bin/python3` is only a stub that asks to install the Xcode Command Line Tools, so install a real Python first: `xcode-select --install`, the python.org macOS installer, or `brew install python@3.12`. `run_project.sh` prefers Homebrew/python.org Python and skips the stub. Open Terminal in this folder (`outputs/traffic_project`) and run:

```bash
chmod +x run_project.sh      # once, if the script is not executable
./run_project.sh --setup     # once: create .venv and install requirements.txt
./run_project.sh             # full study -> results/
./run_project.sh --quick     # quick check -> results_quick/
./run_project.sh --test      # unit tests
```

`run_project.sh` uses `.venv/bin/python` when it exists and otherwise `python3` on the PATH. Extra arguments are passed through to `run.py` (for example `./run_project.sh --workers 4`). The equivalent manual commands are:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 run.py
python3 -m unittest tests test_microscopic -v
```

The default run trains a small Transformer on 30 independent synthetic training days and performs 5 evaluation scenarios × 5 random seeds × 3 controllers = 75 intersection experiments, plus 5 freeway experiments. Use `python3 run.py --quick` for a quick check. Default results are saved in `results/` and quick results in `results_quick/`. `results/replay.html` opens in a browser without a server (`open results/replay.html`). Rerunning updates the same results directory.

PyTorch runs on the CPU (Intel or Apple Silicon); CUDA/MPS is not required. Experiments run in parallel worker processes (`--workers`, default 2), which macOS starts with the same `spawn` method as Windows. Because PyTorch/BLAS builds differ between platforms, retrained results may differ from the saved Windows results in the last digits.

## Implementation and interpretation

- `simulation.py`: SimPy time advance, integer-vehicle FIFO queues, queues outside storage, signal state machine, detector reports, state estimation, beam-search MPC.
- `forecast.py`: PyTorch Transformer encoder, temporal positional embedding, 12-interval arrival history, ToD/DoW inputs, and 10-second forecasts extended recursively to 60 seconds. Forecast error is scored at 30/60-second horizons.
- `freeway.py`: IDM, a simple optimal-velocity relaxation model for comparison, entry/exit, ramp merge, downstream speed bottleneck, loop detector, and occupancy-feedback ramp metering.
- `config.json`: time, storage, signal limits, saturation discharge rate, and training and experiment settings.
- `tests.py`: signal conflicts/minimum and maximum green/clearance, vehicle conservation, delay accounting, storage, detector dropouts, discharge cap, IDM equilibrium, and freeway boundary checks.

The intersection uses only two phases: N/S through and E/W through. Turns, pedestrians and movement inside the intersection are excluded. This is not a microscopic model that represents approach length but a **vertical queue at the stop line**, so delay is stop-line waiting time. While the signal is green, at most one vehicle is discharged every 2 seconds. Remaining service credit is removed at the end of green. Vehicle arrivals occur at the end of each 1-second interval and accumulate delay from the next interval. Vehicles waiting outside accumulate delay in the same way and enter when storage becomes available. Controllers have no access to future arrivals.

The fixed signal uses a symmetric 30-second green matched to a representative symmetric mean demand of 648 veh/h/approach. Because the decision interval is 5 seconds, the applied green can be 30–34 seconds. This plan is a baseline with symmetric allocation and sufficient capacity, but it is not claimed to be the globally optimal fixed-time plan. A minimum green of 10 s, maximum green of 50 s, yellow of 3 s and all-red of 1 s apply to all controllers. Automatic max-green switching is applied every second. These values are educational assumptions, not actual field signal-design values.

The responsive controller requests a switch when the estimated queue of the opposing phase exceeds the current one by 2 or more vehicles. MPC enumerates hold/switch every 5 seconds over 60 seconds and keeps the best 24 paths. The objective is the time integral of the sum of predicted queues, and only the first decision is executed. **It is an approximate beam search with no guarantee of global optimality.** The mismatch between the continuous queues used for prediction and the actual integer discharge also remains. `mpc_transformer` uses the Transformer forecast as the MPC's arrival prediction (the earlier moving-average MPC variant was removed in v2.2).

Detectors observe the arrival boundary upstream of the approach storage and the departure count at the stop line. Internal + external waiting vehicles are estimated from the count difference. This is a strong assumption that the external boundary can be observed. Both interval counts and cumulative counters are transmitted so that the estimate recovers after dropouts; speed observations are `None`. If the last valid observation is older than 10 seconds, the fixed-plan fallback is applied. The 30-second-delay scenario evaluates the conservative behavior of not using stale observations. Ground-truth state is used only for evaluation and plots.

Training uses only synthetic training days generated with the separate seed 7; evaluation seeds 101–105 are not used. The first 120 seconds of evaluation are excluded from forecast evaluation but included in control delay. The balanced scenario shares the same generation rules in training and evaluation, so this is not evidence of external generalization. The ToD/DoW structure from the proposal is implemented, but a short morning session alone cannot demonstrate actual daily/weekly seasonality. Model size and training epochs are defaults chosen for computational cost and were not tuned on evaluation results.

## Result files

`metrics.csv`: total and per-approach delay, throughput, maximum/residual queue, boundary residual, service imbalance, and fallback count. Maximum queue is **the largest, over approaches, of each approach's internal + external maximum**. Delay is accumulated up to the end of the analysis period and does not include clearance delay after the end. Residual vehicles are not discarded. Service imbalance is the max − min over approaches of `(cumulative delay / offered arrivals)`.

`RESULTS.md` contains the run summary. `audit.json` is the independent verification record for the 15 saved detailed traces and all 75 results. `python3 audit_results.py` re-audits the saved results; the audit also runs automatically in the default run.

In the replay, A is the upstream arrival loop detector and D is the stop-line departure loop detector. Vehicles enter from outside the approach, wait, and depart during the recorded green discharge intervals; after departure they turn gray and cross the intersection. The movement paths and detector positions are schematic, not microscopic trajectories calibrated to actual distance and speed. The approach motion during the 6 seconds before arrival is visualized, and the queue and delay figures keep the original results. After editing the template, run `python3 build_replay.py` to refresh only the HTML without recomputing the experiments.

`paired_comparisons.csv`: delay difference relative to fixed for the same seed, with a paired Student-t 95% confidence interval. Negative means improvement and positive means worse. Five seeds is pilot-study scale, and no multiple-comparison correction was applied. `forecast_scores.csv`: count MAE per horizon [veh/approach/horizon].

For the first seed of each scenario, `_observations.csv`, `_forecasts.csv`, `_commands.csv`, `_departures.csv` and `_trace.json` trace observation → estimation → forecast → decision → response. Inputs for all seeds are saved as `demand_*.npy`. `freeway_metrics.csv` and the trajectory/observation/command CSVs are evidence for the common foundation module. `comparison.png`, the per-scenario PNGs, `freeway_trajectories.png` and `replay.html` show actual run results.

## Remaining work before submission

1. Connect the supplied intersection scaffold and observation interface; validate against actual arrival counts and calibrate where needed.
2. Manual sample count audit on short traffic video / provided tracks. Do not claim that the current virtual-detector audit replaces it.
3. Module-exchange runs with teammates and individual explanations/contribution records. Record the work actually performed in the design record (`DESIGN_RECORD.md`).
4. Review the course control materials, write the 6-page final report and presentation, and incorporate instructor feedback. Do not conclude performance or safety improvements in advance.

AI use: the initial code, documentation and synthetic experiments were written by Codex. Automated verification covers `tests.py` and the run results. Contributions, cross-reviews or video analyses not actually performed by the student have not been recorded. The macOS port (shell launcher, portable browser-check scripts, English translation of the Korean text) was made with Claude.

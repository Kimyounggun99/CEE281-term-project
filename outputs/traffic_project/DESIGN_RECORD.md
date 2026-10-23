# Evolving design record / v1.0.0

## v3.1: shared through/right lanes and saved movement interfaces

Primary roads now use L/T/TR and secondary roads LT/TR, as requested. Existing ring sequences, left indications, yellow commitment and IDM dynamics are retained. Right turns use the through ball and shared-lane FIFO, with no right turn on red. Permissive lefts yield to opposing rights as well as through vehicles; the MPC's opposing-flow weights include both. Right-turn occupants participate in the existing all-red interlock. The replay uses a separate right-turn curve and the correct outbound compass leg.

This follows the movement/phase distinction in [FHWA Signal Timing Manual chapter 4](https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter4.htm): one phase can serve through and right movements. The 12 m right path, 6 m right conflict-point location and `.15`/`.1` demand factors are modeling assumptions, not field calibration or signal-design recommendations. Opposing left/right merges are conservatively conflicting; no benefit is assumed from distinct receiving lanes. Turning speed and downstream leader following retain the simplified scalar-path IDM model.

Each run exports every offered vehicle, including censored boundary/upstream vehicles, plus lane/movement metrics and conflict occupancy. IDs distinguish intersections, modes, scenarios, seeds and controllers. Local inbound/outbound ports and front-entry, rear-clearance and local-domain-exit timestamps distinguish stop-line service from delivery to a future receiving link. A versioned schema defines units and blank timestamps. These records support future network coupling; they do not implement receiving capacity, shared link storage, travel time or spillback.

Cross-examination found an existing all-red bug: a left that accepted a gap during yellow could still be upstream when the occupancy detector released the next barrier, then enter during all-red. Clearance now also waits for already-accepted upstream lefts. The signal sequence is unchanged; regression tests exercise the late entry and primary/primary, primary/secondary, secondary/primary and secondary/secondary layouts. The old zero red-entry and guard counters alone did not establish clearance correctness.

The independent complex audit reconciles saved tapes, journals, movement tables and aggregates, reconstructs time loss, checks paired demands, and checks conflict occupancy/PET including opposing rights. Available detailed traces and trajectories check signal safety, storage, motion bounds and clearance. Tests cover FIFO, lane permissions, right-turn signals, gap acceptance, routing, censoring, corrupted exports and closed-loop operation across all controllers/modes. A Node runtime check exercises the embedded replay without installing browser dependencies.

## v3.0: Primary/secondary roads, left-turn lanes, dual-ring phasing

`intersection.py` is a separate generalized module, and `microscopic.py` is untouched. Lanes are channels with a kind (L/T/LT), and each vehicle carries a movement (through/left). The signal state is `(barrier, ((pos, stage, elapsed) per ring))`, using the NEMA lead-lead sequence from FHWA Signal Timing Manual ch. 4, https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter4.htm.

**Concurrency and conflicts.** Concurrency follows the barrier groups {1,2,5,6} and {3,4,7,8}. Conflicts: perpendicular movements always conflict, a left conflicts with the opposing through, and opposing lefts are compatible.

**Permissive indication.** Permissive = FYA (MUTCD IA-10, NCHRP 493), shown only while the opposing through is green. This rules out the yellow trap by construction, and the signal test checks it on every reachable state.

**Gap acceptance.** It uses the HCM signalized values tc=4.5 s and tf=2.5 s. The turner's own clearing time from a stop (about 5.9 s + 1 s margin) binds, so the effective critical gap is 6.9 s. The MPC uses that same value in the permissive-capacity formula, so the controller model and the plant agree. Sneaker clearance on the opposing yellow is permitted.

**Left calls.** Calls come from stop-bar presence, not from the 10-s inventory. The inventory includes vehicles still 200 m upstream, so it never let a left phase gap out or skip; presence matches field actuation.

**Demand.** Demand factors were chosen so that the primary cross product (about 2.0e5) exceeds the 1e5 two-lane screening guideline (WisDOT TSDM 3-4-1), while the secondary road (about 4e4) stays permissive. The fixed plan (10 / 30 / 20 s) rounds up Webster's split. The Transformer is retrained on the new approach totals via `approach_demand_factors`.

**Verification.** Exact reduction to v2.1 for the fixed and responsive controllers (identical metrics, ≤1e-8 delay-check noise). The MPC differs by design because it models individual lanes.

## v2.1: Upstream storage boundary

Move A loops to 200 m upstream; retain two inbound lanes and nominal 30 vehicles/lane. Physical capacity is the smaller of configured storage and floor(length / (vehicle length + standstill gap)). Admission requires space and places the rear bumper at or beyond the upstream boundary. The front-bumper entry location is therefore -195.5 m; free-flow-relative delay uses this exact travel distance.

Queue extent is the stop-line-to-tail rear-bumper distance for stopped vehicles, checked every second against detector spacing. Inventory is capped independently on each lane. Excess offered demand remains in the external reservoir; it is not removed to satisfy the constraint. Internal maximum queue counts exclude this reservoir, which is reported separately. This does not introduce a hard MPC prediction constraint or guarantee spillback-free operation in sustained oversaturation. The replay preserves uniform physical scale and adds camera zoom for the longer road.

## v2.0: Physical IDM intersection dynamics

`microscopic.py` replaces the point-queue plant in `run.py`. Vehicles have front-bumper positions, speeds and lane identities, follow the IDM acceleration law and integrate ballistically at 0.2 s. The same dynamics apply before, inside and after the junction. Red is a stationary virtual leader; passive loops never affect acceleration. Urban desired speed is 10 m/s, a=1.2 m/s², b=2 m/s², T=1.5 s, s0=2 m, length=4.5 m. Hard braking is bounded at 6 m/s²; positional corrections are counted. The map uses 6 drawing units/m in both directions, 3.5m lanes and 1.8m-wide vehicles. Default playback is 1x.

Arrivals occur at the 45m upstream boundary. Geometry and gaps constrain admission, retaining external arrivals in the reservoir. Stop-line throughput is an actual crossing. Delay is elapsed time minus progress/free speed up to the stop line, including reservoir time. Inventory includes moving vehicles; queue counts only speeds below 0.5 m/s. The full controller loop is rerun using IDM entry/exit detector counts. Aggregate count balance estimates inventory, not calibrated stopped queues. MPC retains its approximate fluid inventory prediction and nominal saturation capacity, with startup, lane imbalance and travel-time mismatch left to evaluation.

At yellow onset only, moving vehicles inside their comfortable stopping distance commit to passing when their leader is also clearing. Vehicles already braking do not change this decision partway through yellow. An ideal virtual junction-presence detector holds all-red until the last rear bumper clears the 24m intersection. This is an explicit permitted input to the clearance interlock, not to the forecaster. Fixed timing therefore means nominal fixed greens with the same clearance interlock used by all controllers. No turns, lane changes, pedestrians, downstream blockage or field calibration are modeled. Legacy v1.x descriptions below apply to the earlier queue model.

## v1.1: Two inbound lanes per approach

The intersection now uses two independent straight-through queues on each approach. Each lane receives an independent Poisson realization with the original per-lane demand profile. Default factors [1,1] double the expected approach demand. Factors [.5,.5] retain the previous expected approach total. Each lane has 30 spaces and 0.5 veh/s saturation flow; unused capacity cannot move to its neighbor. No lane changing is modeled. Stop-line departure records include lane ID, and detailed traces retain all eight lane queues, boundary backlogs and throughputs. Aggregate metrics retain the four-approach interface.

The Transformer is retrained on aggregate two-lane arrivals. MPC uses aggregate approach queues and twice the per-lane saturation capacity. This is an approximation when demand is imbalanced between lanes: the prediction may assume service unavailable in the actual nonempty lane. The simulator enforces lane-specific service and exposes this mismatch in evaluation. Signals remain shared by both lanes in the same compatible phase. The visualization reconstructs FIFO events separately for each lane, including arrivals and gray departures.

## Requirement mapping

| Requirement | Implementation / evidence | Status |
|---|---|---|
| Common bounded freeway, arrivals, exits, bottleneck | `freeway.py`, trajectories | Implemented, simplified safe-gap merge |
| Justified original model | IDM equation and sources below | Implemented, not field calibrated |
| CEE281 second-model comparison | OVM relaxation vs IDM; fixed arrivals | Implemented exploratory comparison |
| Conservation, gaps, equilibrium, step sensitivity | tests, dt .25 vs .125 runs, guard counter | Automated and numerical checks |
| Detector observations and missing quantities | interval count, optional mean speed, quality | Implemented |
| Video/manual audit | No video or tracks supplied | Outstanding |
| State estimation + forecast + baseline | cumulative detector balance, Transformer forecast (MA baseline removed in v2.2) | Implemented synthetic evaluation |
| Common closed-loop TMC | fixed vs occupancy-integral ramp feedback | Implemented simplified foundation |
| Final signal phases and stop-line service | explicit green/yellow/all-red | Implemented |
| Baseline, shift, faults, congestion | 5 scenarios, paired seeds | Implemented |
| CEE281 controller ablation | MA-forecast MPC variant removed in v2.2; Transformer MPC vs fixed/responsive | Changed |
| Peer module exchange and roles | interfaces below | Requires team execution |
| Supplied intersection scaffold | Was not included with PDFs | Requires integration |

## Equations and sources

| Source | Design connection | Parameters and limits |
|---|---|---|
| Treiber, Hennecke & Helbing (2000), Congested traffic states in empirical observations and microscopic simulations, https://doi.org/10.1103/PhysRevE.62.1805 | `a[1-(v/v0)^4-(s*/s)^2]`; `s*=s0+max(0,vT+v(v-vlead)/(2 sqrt(ab)))` | a=1.2 m/s², b=2, T=1.5 s, s0=2 m, v0=30 m/s; chosen educational settings |
| Author's IDM implementation notes, https://traffic-simulation.de/info/info_IDM.html | Ballistic integration; exact stopping within a step | dt=.25 and .125 s; hard braking clipped at -8 m/s²; guard interventions counted |
| Bando et al. (1995), Dynamical model of traffic congestion and numerical simulation, https://doi.org/10.1103/PhysRevE.51.1035 | Motivates alternative optimal-velocity relaxation family | Here piecewise-linear V(s), relaxation 1.5 s; NOT reproduction of original tanh calibration |
| Papageorgiou et al. (1991), ALINEA, https://onlinepubs.trb.org/Onlinepubs/trr/1991/1320/1320-008.pdf | Occupancy-integral feedback structure `r <- clip(r+K(o*-o))` | K=.2 veh/s per occupancy fraction per update, target .18, period 10 s; ALINEA-inspired, not calibrated ALINEA |
| FHWA Traffic Signal Timing Manual, Ch. 5, https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter5.htm | Green constraints and clearance structure | 10/50 s green, 3 s yellow, 1 s all-red are assumptions, not prescribed by source |
| Vaswani et al. (2017), https://arxiv.org/abs/1706.03762 | Self-attention encoder forecasting | 1 layer, d_model=24, 4 heads; implementation uses PyTorch |
| Hyndman & Athanasopoulos, Forecasting: Principles and Practice, https://otexts.com/fpp3/tscv.html | Time-ordered evaluation, horizon-specific forecast errors | Independent synthetic training days; untouched evaluation seeds |
| Li & Savla (2025), https://arxiv.org/abs/2503.10934 | Related traffic MPC literature | Our finite-horizon queue-delay beam search does NOT reproduce their adaptive parameter-identification controller |
| User proposal, Adaptive Traffic Signal Control Using Demand Forecasting and Rolling-Horizon Optimization, pp. 2-4 | Two phases, Transformer recursion, queue-delay optimization, paired experiments | Scope maintained; supplied scaffold/data pending |

No third-party simulation code was copied. NumPy, SimPy, PyTorch, SciPy and Matplotlib provide numerics, scheduling, neural network layers, statistical intervals and plotting.

## Interfaces

Seconds, meters, m/s internally. Freeway x=0 upstream, x=1000 downstream, increasing downstream; front-bumper position; length 5 m. Trajectory sample period 1 s, numerical integration .25 s. Vehicle IDs are unique per run. Mainline and ramp external queues are unbounded backlogs: no demand disappears. Ramp merge at 300 m, downstream speed reduction at 700 m. No lane changes or realistic acceleration lane.

Intersection detector records event timestamps in `(start,end]`; counts are published at `end`. Forecast at t describes the next `(t,t+h]` count. Commands apply at decision time; step permission is held during `[t,t+1)`. Queue traces sample interval end. Exact event convention is defined in code and departure records.

`simulation.run` accepts a fixed realized arrival tape for the plant. Only the detector adapter reads realized arrivals as time advances; controllers receive estimated queues, signal state and predictions. The evaluator reads future tape slices only after the simulation finishes to score forecasts. The cumulative counter estimator assumes known empty initial conditions and working arrival/departure counting hardware; a report outage differs from permanent detector counter failure.

Finite horizon accounting: served delay + sum(T-arrival_time) for all waiting vehicles = total integral waiting. Throughput + internal residual + boundary residual = all offered arrivals. No average of completed vehicles is used to hide residual demand.

## Predictions before execution

1. Balanced average demand should give the fixed plan a credible reference performance. Adaptive benefit is uncertain because short-term Poisson variation can dominate predictability.
2. Directional shift may favor feedback control; a Transformer trained only on recurring balanced sessions may lag or mispredict it.
3. Missing/stale reports should trigger fixed fallback, removing any forecast advantage during the outage.
4. Heavy demand should produce external and residual queues and nonzero unmet-at-horizon demand.
5. MA versus Transformer MPC isolates the forecast choice; a better count forecast need not give lower delay with the approximate controller. (Not tested after v2.2: the MA-forecast MPC was removed.)

After execution, consult metrics, paired intervals, forecast scores and `RESULTS.md`. Do not selectively report only successful seeds.

## Individual ownership and exchange record

Proposed, not certified: Younggun Kim - forecasting and optimization; Manuel A. Martinez Garcia - plant, sensing and evaluation. Confirm actual allocation with both students. For each actual contribution record name, file/function, test command, outcome, explanation and date. Run another student's module on a small shared input and record any interface mismatch. This work has not yet been performed by the students.

## Limits

Synthetic data only; 15-minute horizon; no pedestrian/turning movement, spillback network, startup lost-time calibration or physical junction conflicts beyond phase compatibility. Boundary detector coverage is idealized. Missing reports recover through retained counters. Forecast objective uses fluid service, while plant is discrete. Beam truncation may prune best sequences. No confidence calibration for neural forecasts; paired controller intervals describe seed variation only. Freeway merge rules and speed bottleneck are artificial. Hard braking and collision guards alter IDM and must be examined. No crash-reduction claim.

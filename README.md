# CEE 281: Adaptive Traffic Signal Control

Simulation code: `outputs/traffic_project/` (model details: `outputs/traffic_project/README.md`).

## Environment

- macOS (Apple Silicon or Intel) or Linux
- Python 3.9 or newer (`python3 --version`)
  - macOS without Python: `xcode-select --install`
- Python packages (installed by `--setup`): numpy, scipy, matplotlib, simpy, torch — see `outputs/traffic_project/requirements.txt`
- Optional, for browser checks of the replay: Node.js 18+

## Setup

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>/outputs/traffic_project
chmod +x run_project.sh
./run_project.sh --setup        # creates .venv and installs requirements.txt
```

## Commands

Run from `outputs/traffic_project/`:

```bash
./run_project.sh --test         # unit tests
./run_project.sh --quick        # quick run      -> results_quick/
./run_project.sh                # full study     -> results/
./run_project.sh --workers 4    # full study, 4 worker processes

open results/RESULTS.md         # summary (Linux: xdg-open)
open results/replay.html        # replay (created by the full run)
```

After a full run:

```bash
source .venv/bin/activate
python audit_results.py         # re-audit saved results
python build_replay.py          # rebuild results/replay.html only
```

Optional replay checks (from the repository root):

```bash
cd work
npm install
npx playwright install chromium
node verify_storage_replay.cjs
node verify_idm_replay.cjs
```

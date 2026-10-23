# Replay browser checks

`node verify_complex_replay.cjs` checks the current complex replay's embedded JavaScript, controller/scenario selection, counts, playback and right-turn exit geometry using Node's standard library. It reads `../outputs/traffic_project/results_complex/replay.html`; pass another HTML path as its first argument for quick results. It does not check browser canvas rasterization.

These Node scripts open `../outputs/traffic_project/results/replay.html` in headless Chromium (Playwright) and check rendering, motion and storage limits. Screenshots are written to this folder.

On the original Windows machine they used a Codex-bundled Playwright and Microsoft Edge. On macOS they use a local Playwright install and its bundled Chromium:

```bash
cd work
npm install                       # installs playwright from package.json
npx playwright install chromium   # once
node verify_storage_replay.cjs    # current v2.1 check
node verify_idm_replay.cjs        # v2.0 IDM check
```

`check_motion.cjs`, `check_no_stop.cjs`, `verify_replay.cjs` and `verify_two_lanes.cjs` target earlier replay versions (v1.x globals such as `scenarios`/`events()`) and are kept as a historical record; they are not expected to pass against the current replay.

`inspect_guards.py` is a debugging helper: `python3 inspect_guards.py` (needs the project's Python environment).

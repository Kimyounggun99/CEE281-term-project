#!/usr/bin/env bash
# macOS/Linux launcher (replaces the Windows run_project.ps1).
# Usage:
#   ./run_project.sh --setup   create .venv and install requirements.txt
#   ./run_project.sh           full study  -> results/
#   ./run_project.sh --quick   quick check -> results_quick/
#   ./run_project.sh --test    unit tests
# Any other arguments (e.g. --workers 4) are passed to run.py.
set -eo pipefail
cd "$(dirname "$0")"

# Equivalent of "python -X utf8" in the Windows script.
export PYTHONUTF8=1
# Avoid Matplotlib GUI backends and oversubscribing threads in worker processes.
export MPLBACKEND=Agg
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

# On macOS, /usr/bin/python3 is only a stub until the Xcode Command Line Tools
# are installed (running it pops up the "install developer tools" dialog).
# Prefer a real Python from Homebrew or python.org, and only use the system
# stub when the Command Line Tools are actually present.
find_python() {
    local cand
    for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                /Library/Frameworks/Python.framework/Versions/3.1[0-9]/bin/python3; do
        if [ -x "$cand" ]; then echo "$cand"; return 0; fi
    done
    cand="$(command -v python3 2>/dev/null || true)"
    if [ -n "$cand" ]; then
        if [ "$cand" = "/usr/bin/python3" ] && [ "$(uname)" = "Darwin" ] \
           && ! xcode-select -p >/dev/null 2>&1; then
            return 1
        fi
        echo "$cand"; return 0
    fi
    return 1
}

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif ! PY="$(find_python)"; then
    cat >&2 <<'MSG'
No usable Python 3 was found.
Install Python 3.9 or newer with ONE of these, then rerun ./run_project.sh --setup:
  1) python.org installer: https://www.python.org/downloads/macos/
  2) Homebrew:  brew install python@3.12
  3) Apple Command Line Tools:  xcode-select --install
MSG
    exit 1
fi
echo "Using Python: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])'))"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' || {
    echo "Python 3.9 or newer is required." >&2
    exit 1
}

MODE=run
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --setup) MODE=setup ;;
        --test)  MODE=test ;;
        *)       ARGS+=("$arg") ;;
    esac
done

case "$MODE" in
    setup)
        "$PY" -m venv .venv
        .venv/bin/python -m pip install --upgrade pip
        .venv/bin/python -m pip install -r requirements.txt
        echo "Environment ready: $(pwd)/.venv"
        ;;
    test)
        exec "$PY" -m unittest tests test_microscopic -v
        ;;
    run)
        exec "$PY" run.py ${ARGS[@]+"${ARGS[@]}"}
        ;;
esac

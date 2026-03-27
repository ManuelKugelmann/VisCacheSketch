# Plan: Ladder Batch Session — No Mogwai Restart Between Steps

## Context

Each `mogwai-headless.sh` call starts a fresh Mogwai process: DX12 device creation, CUDA init,
Python interpreter init, and first-run shader compilation all pay their cost every time.
Within a single step (e.g. Ladder01) all variants already run inside ONE Mogwai session —
`run_variants()` loops over variants using `m.addGraph()` / `m.removeGraph()` / `m.loadScene()`
without restarting. The same pattern can eliminate the restart between ladder steps.

**Goal:** run Step 00 + Step 01 + Step 02 (and any future steps) in a single Mogwai process.

**What exists already:**
- `RunGraphHeadless.py` — current harness: exec one `GRAPH_SCRIPT`, then `exit()`
- `VisCache_Ladder01.py` (and 00, 02) — each script sets `_HEADLESS_SCRIPT_DONE = True`
  and does its own rendering via `run_variants()` / `run_baseline()`; they rely on
  `globals()` containing `m` and `fc` (injected by Mogwai's scripting context)
- No IPC/socket/server mode in Mogwai — verified by code search

## Approach

Add a **batch harness** `RunLadderBatch.py` that exec's multiple step scripts sequentially
inside one Mogwai session. No changes to the individual ladder step scripts.

### How it works

```
Mogwai --headless --script RunLadderBatch.py
```

`LADDER_STEPS` env var lists which step scripts to run (comma-separated glob patterns or names):

```
LADDER_STEPS="VisCache_Ladder00.py,VisCache_Ladder01.py,VisCache_Ladder02.py"
```

The harness:
1. For each script path in `LADDER_STEPS`:
   a. Reset `_HEADLESS_SCRIPT_DONE = False` in the current namespace
   b. `exec(open(script_path).read())` — same as RunGraphHeadless.py does today
   c. The script runs, calls `run_variants(mogwai_globals=globals())` which uses the
      persistent `m` / `fc` from Mogwai's scripting context
   d. Script sets `_HEADLESS_SCRIPT_DONE = True` and returns
2. After all steps: `exit()`

Key: `_HEADLESS_SCRIPT_DONE` is a local flag; `m` and `fc` are provided by Mogwai's
Python context and persist across all `exec` calls without any extra wiring.

### New files

**`scripts/RunLadderBatch.py`**
```python
"""
RunLadderBatch.py — Run multiple ladder step scripts in one Mogwai session.

Env vars:
    LADDER_STEPS   — comma-separated script names or paths (relative to scripts/ dir)
                     default: all VisCache_Ladder??.py in scripts/
    PROJECT_ROOT   — project root (set by mogwai-headless.sh)
"""
import os, sys, glob

project_root = os.environ.get("PROJECT_ROOT", "")
scripts_dir = os.path.join(project_root, "scripts") if project_root else \
              os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

steps_env = os.environ.get("LADDER_STEPS", "")
if steps_env:
    names = [s.strip() for s in steps_env.split(",") if s.strip()]
else:
    names = sorted(glob.glob(os.path.join(scripts_dir, "VisCache_Ladder??.py")))

def _resolve(name):
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    candidate = os.path.join(scripts_dir, name)
    if os.path.isfile(candidate):
        return candidate
    return name  # let it fail with a clear error

scripts = [_resolve(n) for n in names]

print(f"[batch] Running {len(scripts)} ladder steps in one session:")
for p in scripts:
    print(f"[batch]   {os.path.basename(p)}")

for script_path in scripts:
    print(f"\n[batch] ===== {os.path.basename(script_path)} =====")
    _HEADLESS_SCRIPT_DONE = False
    with open(script_path) as _f:
        exec(_f.read(), globals())
    print(f"[batch] ===== {os.path.basename(script_path)} done =====")

exit()
```

**`.scripts/mogwai-ladder.sh`** — thin wrapper around `mogwai-headless.sh` that sets
`GRAPH_SCRIPT` to `RunLadderBatch.py` and passes `LADDER_STEPS` through:

```bash
#!/usr/bin/env bash
# mogwai-ladder.sh — Run a batch of ladder steps in one Mogwai session.
# Usage: .scripts/mogwai-ladder.sh [--source|--synced] [step1.py,step2.py,...]
#   Default: all VisCache_Ladder??.py in scripts/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Pull optional --source/--synced flag
MODE_ARG=""
if [ "${1:-}" = "--source" ] || [ "${1:-}" = "--synced" ]; then
    MODE_ARG="$1"; shift
fi

STEPS_ARG="${1:-}"  # optional comma-separated list; empty = all ladder scripts

export LADDER_STEPS="$STEPS_ARG"

exec "$SCRIPT_DIR/mogwai-headless.sh" $MODE_ARG 'RunLadderBatch.py'
```

### Changes to `mogwai-headless.sh`

None required. `RunLadderBatch.py` is just another `GRAPH_SCRIPT` from its perspective;
`_HEADLESS_SCRIPT_DONE = True` at the end skips the harness's simple scene-load fallback.

### Changes to individual ladder scripts

None. They already use `_HEADLESS_SCRIPT_DONE = True` and `run_variants(mogwai_globals=globals())`.

## Critical files

| File | Action |
|------|--------|
| `scripts/RunLadderBatch.py` | **new** |
| `.scripts/mogwai-ladder.sh` | **new** |
| `scripts/RunGraphHeadless.py` | read-only reference |
| `scripts/VisCache_LadderCommon.py` | read-only; `run_variants()` already session-safe |
| `scripts/VisCache_Ladder00.py` | no change |
| `scripts/VisCache_Ladder01.py` | no change |
| `scripts/VisCache_Ladder02.py` | no change |

## Edge cases / risks

- **`sys.path.insert` duplication**: each ladder script does `sys.path.insert(0, ...)` —
  harmless, Python deduplicates module cache.
- **Global state leaks between steps**: `VISCACHE_DEFAULTS` in LadderCommon is module-level.
  Each step restores overrides after each variant (already done in `run_variants`). Safe.
- **CSV append collision**: `append_stats_csv` opens for append; running 00→01→02 in one
  session is fine since each step writes to its own `captures/ladder/{step}/stats.csv`.
- **`plot_rays_overview` CWD dependency**: plots use relative `captures/` paths.
  `RunGraphHeadless.py` already does `cd "$RUNTIME"` before launching Mogwai. Safe.
- **`exit()` in ladder scripts**: each script currently ends with `_HEADLESS_SCRIPT_DONE = True`
  (not `exit()`). The batch harness itself calls `exit()` at the very end. Confirm none of
  the individual scripts call bare `exit()` before the flag.

## Verification

```bash
# Batch run steps 00+01 in one session
.scripts/mogwai-ladder.sh 'VisCache_Ladder00.py,VisCache_Ladder01.py'

# All steps
.scripts/mogwai-ladder.sh

# Single step (same as before, but via batch harness)
LADDER_STEPS='VisCache_Ladder01.py' .scripts/mogwai-ladder.sh
```

Expected: no regression in output vs individual `mogwai-headless.sh` runs; startup overhead
paid once instead of N times.

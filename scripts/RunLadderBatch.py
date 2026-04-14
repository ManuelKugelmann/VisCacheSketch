"""
RunLadderBatch.py — Run multiple ladder step scripts in one Mogwai session.

Eliminates per-step DX12/CUDA/Python startup overhead by exec'ing each ladder
script sequentially inside the same Mogwai process. m and fc persist across steps.

Env vars:
    LADDER_STEPS   — comma-separated script names or paths (relative to scripts/ dir)
                     default: all VisCache_Ladder??.py in scripts/
    PROJECT_ROOT   — project root (set by mogwai-headless.sh in source mode)

Usage:
    .scripts/mogwai-ladder.sh [--source|--synced] [step1.py,step2.py,...]
    # or directly:
    LADDER_STEPS="VisCache_Ladder01.py,VisCache_Ladder02.py" \\
        Mogwai.exe --headless --script RunLadderBatch.py
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
    return name  # let it fail with a clear error below

scripts = [_resolve(n) for n in names]

if not scripts:
    print("[batch] No ladder steps found — set LADDER_STEPS or add VisCache_Ladder??.py to scripts/")
    exit(1)

print(f"[batch] Running {len(scripts)} ladder step(s) in one session:")
for p in scripts:
    print(f"[batch]   {os.path.basename(p)}")

for script_path in scripts:
    if not os.path.isfile(script_path):
        print(f"[batch] ERROR: script not found: {script_path}")
        exit(1)
    print(f"\n[batch] ===== {os.path.basename(script_path)} =====")
    _HEADLESS_SCRIPT_DONE = False
    with open(script_path) as _f:
        exec(_f.read(), globals())
    print(f"[batch] ===== {os.path.basename(script_path)} done =====")

print("\n[batch] All steps complete.")
_HEADLESS_SCRIPT_DONE = True

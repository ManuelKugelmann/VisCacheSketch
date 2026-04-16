"""
RunLadderBatch.py — Run ladder steps for one or more scenes in a single Mogwai
session.

Scene-outer loop: for each scene, exec every requested step script with
SCENE_FILE set so each step's `get_scenes()` returns just that scene. Keeps
per-scene results grouped (useful when adding a scene and rerunning only the
additive part — captures/CSV are upsert-keyed, so existing data survives).

Eliminates DX12/CUDA/Python startup between steps. NOT safe for very large
sweeps in one process (Slang's internal compiler fatigues after ~60
permutations in a single Mogwai session) — use `.scripts/mogwai-ladder.sh`
for per-scene Mogwai isolation instead.

Env vars:
    LADDER_STEPS   comma-separated script names (e.g. "VisCache_Ladder05.py,...").
                   Default: all VisCache_Ladder??.py in scripts/
    LADDER_SCENES  comma-separated scene files (e.g. "CornellBox_1AreaLight.pyscene,...").
                   Default: ALL_SCENES from VisCache_LadderCommon (the
                   authoritative list — extend there when adding scenes).
    PROJECT_ROOT   project root (set by mogwai-headless.sh in source mode).

Usage:
    .scripts/mogwai-ladder.sh [--source|--synced] <steps> [scenes]
    # or directly:
    LADDER_STEPS="VisCache_Ladder06.py" LADDER_SCENES="CornellBox_1AreaLight.pyscene" \\
        Mogwai.exe --headless --script RunLadderBatch.py
"""
import os, sys, glob

project_root = os.environ.get("PROJECT_ROOT", "")
scripts_dir = os.path.join(project_root, "scripts") if project_root else \
              os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

from VisCache_LadderCommon import ALL_SCENES

steps_env = os.environ.get("LADDER_STEPS", "")
if steps_env:
    step_names = [s.strip() for s in steps_env.split(",") if s.strip()]
else:
    step_names = sorted(glob.glob(os.path.join(scripts_dir, "VisCache_Ladder??.py")))

scenes_env = os.environ.get("LADDER_SCENES", "")
if scenes_env:
    scenes = [s.strip() for s in scenes_env.split(",") if s.strip()]
else:
    scenes = list(ALL_SCENES)

def _resolve(name):
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    candidate = os.path.join(scripts_dir, name)
    if os.path.isfile(candidate):
        return candidate
    return name  # let it fail with a clear error below

scripts = [_resolve(n) for n in step_names]

if not scripts:
    print("[batch] No ladder steps found — set LADDER_STEPS or add VisCache_Ladder??.py to scripts/")
    exit(1)
if not scenes:
    print("[batch] No scenes to run — set LADDER_SCENES or populate ALL_SCENES")
    exit(1)

print(f"[batch] Running {len(scripts)} step(s) × {len(scenes)} scene(s) in one session:")
for s in scenes:
    print(f"[batch]   scene: {s}")
for p in scripts:
    print(f"[batch]   step:  {os.path.basename(p)}")

# Scene-outer, step-inner: one scene runs its full step list before moving on.
# Each step sees SCENE_FILE set so its get_scenes() resolves to a singleton.
for scene_file in scenes:
    os.environ["SCENE_FILE"] = scene_file
    # SCENES would take precedence over SCENE_FILE in get_scenes(); clear it
    # so the single-scene override actually applies.
    os.environ.pop("SCENES", None)
    print(f"\n[batch] ========= scene: {scene_file} =========")
    for script_path in scripts:
        if not os.path.isfile(script_path):
            print(f"[batch] ERROR: script not found: {script_path}")
            exit(1)
        print(f"\n[batch] ----- {os.path.basename(script_path)} @ {scene_file} -----")
        _HEADLESS_SCRIPT_DONE = False
        with open(script_path) as _f:
            exec(_f.read(), globals())
        print(f"[batch] ----- {os.path.basename(script_path)} @ {scene_file} done -----")

print("\n[batch] All scene × step combinations complete.")
_HEADLESS_SCRIPT_DONE = True

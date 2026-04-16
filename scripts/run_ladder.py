"""
run_ladder.py — Python ladder runner. Per-(step, scene) Mogwai isolation.

One Mogwai process per (step, scene) combo. Avoids both Slang's internal
compiler fatigue (~60 shader permutations/process) AND GPU/host memory
accumulation when batching many steps in one session. Captures & CSV are
upsert-keyed, so subsetting and additive runs are safe.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py [-s STEPS] [-c SCENES]

Args:
    -s / --steps    Comma- or space-separated step numbers ("06" or
                    "VisCache_Ladder06.py"). Default: all VisCache_Ladder??.py
                    in scripts/.
    -c / --scenes   Comma- or space-separated scene names ("CornellBox_1AreaLight"
                    or full ".pyscene"). Default: ALL_SCENES from
                    VisCache_LadderCommon.

Examples:
    python scripts/run_ladder.py -s 06
    python scripts/run_ladder.py -s "03 05 06 07 08" -c CornellBox_1AreaLight
    python scripts/run_ladder.py -s 06,12 -c CornellBox_1AreaLight,CornellBox_3AreaLights
    python scripts/run_ladder.py -c NewScene                 # all steps, additive
"""
import argparse
import os
import re
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR  = os.path.join(PROJECT_ROOT, "scripts")
RUNTIME_DIR  = os.path.join(PROJECT_ROOT, "runtime")
MOGWAI_EXE   = os.path.join(RUNTIME_DIR, "Mogwai.exe")
HARNESS_PY   = os.path.join(SCRIPTS_DIR, "RunGraphHeadless.py")
BATCH_PY     = os.path.join(SCRIPTS_DIR, "RunLadderBatch.py")

sys.path.insert(0, SCRIPTS_DIR)
from VisCache_LadderCommon import ALL_SCENES


def _split(arg, default):
    """Comma OR whitespace separated → list. Empty / None → default."""
    if not arg:
        return list(default)
    return [t for t in re.split(r'[,\s]+', arg.strip()) if t]


def _normalize_step(s):
    if s.endswith(".py"):
        return s
    return f"VisCache_Ladder{s}.py"


def _normalize_scene(s):
    if s.endswith(".pyscene"):
        return s
    return f"{s}.pyscene"


def _run_one(scene, step):
    """One Mogwai process for one (scene, step) combo. Maximum isolation:
    avoids both Slang compiler fatigue (accumulated shader permutations) and
    memory accumulation across step scripts.
    """
    env = os.environ.copy()
    env["PROJECT_ROOT"]  = PROJECT_ROOT
    env["GRAPH_SCRIPT"]  = BATCH_PY
    env["LADDER_STEPS"]  = step
    env["LADDER_SCENES"] = scene
    cmd = [MOGWAI_EXE, "--headless", "--script", HARNESS_PY]
    print(f"\n### [{time.strftime('%H:%M:%S')}] scene={scene} step={step} ###",
          flush=True)
    t0 = time.time()
    rc = subprocess.call(cmd, env=env, cwd=RUNTIME_DIR)
    dt = time.time() - t0
    status = "OK" if rc == 0 else f"FAIL (rc={rc})"
    print(f"### [{time.strftime('%H:%M:%S')}] scene={scene} step={step} {status} ({dt:.0f}s) ###",
          flush=True)
    return rc == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--steps",  default="", help="Steps to run (default: all)")
    ap.add_argument("-c", "--scenes", default="", help="Scenes to run (default: ALL_SCENES)")
    args = ap.parse_args()

    import glob
    raw_steps  = _split(args.steps,  default=[])
    raw_scenes = _split(args.scenes, default=ALL_SCENES)
    if raw_steps:
        steps = [_normalize_step(s) for s in raw_steps]
    else:
        steps = sorted(os.path.basename(p)
                       for p in glob.glob(os.path.join(SCRIPTS_DIR, "VisCache_Ladder??.py")))
    scenes = [_normalize_scene(s) for s in raw_scenes]

    if not os.path.isfile(MOGWAI_EXE):
        sys.exit(f"Mogwai.exe not found at {MOGWAI_EXE}")
    if not os.path.isfile(BATCH_PY):
        sys.exit(f"RunLadderBatch.py not found at {BATCH_PY}")

    print(f"[run_ladder] {len(steps)} step(s) × {len(scenes)} scene(s) = {len(steps)*len(scenes)} Mogwai runs")
    for s in scenes:
        print(f"[run_ladder]   scene: {s}")
    for s in steps:
        print(f"[run_ladder]   step:  {s}")

    passed, failed = 0, []
    for scene in scenes:
        for step in steps:
            if _run_one(scene, step):
                passed += 1
            else:
                failed.append((scene, step))

    print(f"\n=== run_ladder summary: {passed} passed, {len(failed)} failed ===")
    if failed:
        for scene, step in failed:
            print(f"  FAIL scene={scene} step={step}")
        sys.exit(1)


if __name__ == "__main__":
    main()

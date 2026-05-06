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


# Per-step chunk count: steps with large variant sets are dispatched as
# CHUNK_COUNT Mogwai processes via CHUNK_IDX env, so one step's workload can
# stay under the per-process OOM ceiling while keeping one logical step name
# (one CSV, one capture dir, one plot). Steps not listed here run as a single
# Mogwai process.
CHUNKS_PER_STEP = {
    # Empirical safe ceiling: ~24 runs per Mogwai process (step 04 at 3
    # chunks = 9 variants × 3 SPP = 27 runs/chunk has been stable; the
    # 4-chunk step 03 version at 48 runs/chunk crashed every chunk).
    # Sized so a default run completes without triggering retry.
    "VisCache_Ladder03.py": 8,  # 96 variants × 2 SPP = 192 runs/scene → 8 × 24
    "VisCache_Ladder04.py": 3,  # 9 variants × 3 SPP = 27 runs/scene  → 3 × 9
    # New multi-frame ladder (post-archive) — step 11+ scripts hold few
    # variants (≤6), no chunking needed.
}


def _run_one(scene, step, chunk_idx=0, chunk_count=1, attempt_tag=""):
    """One Mogwai process for one (scene, step, chunk) combo."""
    env = os.environ.copy()
    env["PROJECT_ROOT"]  = PROJECT_ROOT
    env["GRAPH_SCRIPT"]  = BATCH_PY
    env["LADDER_STEPS"]  = step
    env["LADDER_SCENES"] = scene
    env["CHUNK_IDX"]     = str(chunk_idx)
    env["CHUNK_COUNT"]   = str(chunk_count)
    cmd = [MOGWAI_EXE, "--headless", "--script", HARNESS_PY]
    chunk_tag = f" chunk={chunk_idx+1}/{chunk_count}" if chunk_count > 1 else ""
    print(f"\n### [{time.strftime('%H:%M:%S')}] scene={scene} step={step}{chunk_tag}{attempt_tag} ###",
          flush=True)
    t0 = time.time()
    rc = subprocess.call(cmd, env=env, cwd=RUNTIME_DIR)
    dt = time.time() - t0
    status = "OK" if rc == 0 else f"FAIL (rc={rc})"
    print(f"### [{time.strftime('%H:%M:%S')}] scene={scene} step={step}{chunk_tag}{attempt_tag} {status} ({dt:.0f}s) ###",
          flush=True)
    return rc == 0


def _run_one_with_retry(scene, step, chunk_idx=0, chunk_count=1, max_retries=5):
    """Run (scene, step, chunk), retrying on non-zero exit (likely OOM). Each
    retry is a fresh Mogwai process; resume in run_variants skips variants that
    already have CSV rows, so retries only work on what's left. Stops if a
    retry makes no progress (same failure without advancing)."""
    step_num = step.replace("VisCache_Ladder", "").replace(".py", "")
    csv_path = os.path.join(RUNTIME_DIR, "captures", "ladder", step_num, "stats.csv")

    def _csv_size():
        try: return os.path.getsize(csv_path)
        except OSError: return 0

    for attempt in range(1, max_retries + 1):
        tag = f" (try {attempt}/{max_retries})" if attempt > 1 else ""
        before = _csv_size()
        if _run_one(scene, step, chunk_idx, chunk_count, attempt_tag=tag):
            return True
        after = _csv_size()
        if after <= before:
            print(f"### scene={scene} step={step} — no progress on retry {attempt}, giving up", flush=True)
            return False
    return False


def _run_scene_step(scene, step):
    """Dispatch all chunks for (scene, step). Returns True if every chunk OK."""
    n_chunks = CHUNKS_PER_STEP.get(step, 1)
    for chunk_idx in range(n_chunks):
        if not _run_one_with_retry(scene, step, chunk_idx, n_chunks):
            return False
    return True


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
        # Numeric ladder steps (00..99); RDI_NN steps must be requested
        # explicitly via -s RDI_01 etc to keep the default run focused.
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
    for step in steps:
        for scene in scenes:
            if _run_scene_step(scene, step):
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

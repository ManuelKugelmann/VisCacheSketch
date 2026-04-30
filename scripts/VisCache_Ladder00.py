"""
VisCache_Ladder00.py — Step 00: Vanilla baselines (no VisCache).

Reference renders for L2 error and noise comparison. Renders x1 SPP
(error baseline) + x4096 SPP ground truth (noise baseline) per scene.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder00.py
"""
import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_baseline, run_baseline_wsrestir, run_baseline_rtxdi,
    get_scenes, finalize_baseline,
)

res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    # Wipe baseline directory for clean output
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    baseline_dir = f"captures/ladder/00/{scene_name}"
    if os.path.exists(baseline_dir):
        shutil.rmtree(baseline_dir, ignore_errors=True)

    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        gt_spp=4096,
        # x2 / x4 / x8 / x16 added for step 04's sample-count sweep; step 05+ uses x4.
        extra_spp=[2, 4, 8, 16],
        mogwai_globals=globals(),
    )

    # §9.4 WS-ReSTIR DI self-baseline (direct-lighting only).
    # Captures at virtual SPP 1 and 4 — same low-SPP regime where ReSTIR
    # variance reduction is meaningful. Compared against vanilla x1/x4
    # for variance benefit, against vanilla x4096 GT for bias check.
    run_baseline_wsrestir(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # RTXDI external reference (ReSTIR DI ground truth for proper-implementation
    # variance reduction). RTXDI's SPP is fixed at 1 per frame internally; we
    # capture once per scene as the reference quality bar.
    run_baseline_rtxdi(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1,),
        mogwai_globals=globals(),
    )

finalize_baseline("00")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder00.py — Step 00: Vanilla baselines (no VisCache).

Reference renders for L2 error and noise comparison. Renders x1 SPP
(error baseline) + x4096 SPP ground truth (noise baseline) per scene.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder00.py
"""
import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_baseline, get_scenes

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
        # x4 / x8 added for step 04's sample-count sweep; step 05+ only use x4.
        extra_spp=[4, 8, 16],
        mogwai_globals=globals(),
    )

_HEADLESS_SCRIPT_DONE = True

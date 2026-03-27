"""
VisCache_Ladder00.py — Step 00: Vanilla baseline (no VisCache).

Reference render for L2 error comparison. Same scene, same sample count,
same PathTracer settings — just no VisCache pass. All other ladder steps
compare against this baseline.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder00.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_baseline

import shutil
scene_file = os.environ.get("SCENE_FILE", "media/scenes/CornellBox_1AreaLight.pyscene")
res = int(os.environ.get("RES", "512"))

# Wipe baseline directory for clean output
scene_name = os.path.splitext(os.path.basename(scene_file))[0]
baseline_dir = f"captures/ladder/00/{scene_name}"
if os.path.exists(baseline_dir):
    shutil.rmtree(baseline_dir, ignore_errors=True)

run_baseline(
    step_name="00",
    frame_configs=[(1, 1)],   # same warmup+averaging as step 01
    scene_file=scene_file,
    resX=res, resY=res,
    gt_spp=4096,              # ground truth: 4096 total samples (256 frames × 16 SPP, no jitter)
    mogwai_globals=globals(),
)
_HEADLESS_SCRIPT_DONE = True

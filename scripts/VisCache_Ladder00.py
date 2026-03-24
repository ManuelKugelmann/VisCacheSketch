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

scene_file = os.environ.get("SCENE_FILE", "media/scenes/CornellBox.pyscene")
res = int(os.environ.get("RES", "512"))

run_baseline(
    step_name="00",
    frame_configs=[(1, 1)],
    scene_file=scene_file,
    resX=res, resY=res,
    mogwai_globals=globals(),
)
exit()

"""
VisCache_Ladder01.py — Step 01: Single frame, all addressing variants.

1 warmup frame + 1 render frame. Tests hash table insert/lookup,
diagnostic pipeline, and all addressing modes.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants

scene_file = os.environ.get("SCENE_FILE", "media/scenes/CornellBox.pyscene")
res = int(os.environ.get("RES", "512"))

run_variants(
    step_name="01",
    frame_configs=[(1, 1)],
    scene_file=scene_file,
    resX=res, resY=res,
    mogwai_globals=globals(),
)
exit()

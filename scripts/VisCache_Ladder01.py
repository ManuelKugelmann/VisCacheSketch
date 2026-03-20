"""
VisCache_Ladder01.py — Step 01: Multi-frame accumulation, all addressing variants.

Tests convergence: cold start (8 frames) and warm start (8+8 frames).
Compares accumulated diagnostics vs snapshots.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants

scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")

run_variants(
    step_name="01",
    frame_configs=[
        (0, 8),      # cold start, 8 frames
        (8, 8),      # warm start, 8 frames averaging
    ],
    scene_file=scene_file,
    mogwai_globals=globals(),
)
exit()

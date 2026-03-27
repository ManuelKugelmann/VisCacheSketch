"""
VisCache_Ladder02.py — Step 02: Coarser posA cell sizes.

Tests effect of larger posA cells on cache quality.
x3 for most variants, x1.5 for pos_dir_dist1, unchanged for pos_pos1/pos_dir1_dist1.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder02.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, BASE, get_scenes, plot_rays_overview, \
    _make_variants

res = int(os.environ.get("RES", "512"))

QUANT_02 = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 8.0, "distB": 0.48}
VARIANTS_02 = _make_variants(normal_active=False, quant=QUANT_02)

for scene_file in get_scenes():
    # Ensure x32 baseline exists in step 00
    run_baseline(
        step_name="00",
        frame_configs=[(1, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="02",
        frame_configs=[(1, 1, 1), (1, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_02,
        resX=res, resY=res,
        mogwai_globals=globals(),
    )

plot_rays_overview("02")
_HEADLESS_SCRIPT_DONE = True

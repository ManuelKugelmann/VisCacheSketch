"""
VisCache_Ladder02.py — Step 02: Coarser posA cell sizes.

Tests effect of larger posA cells on cache quality.
x3 for most variants, x1.5 for pos_dir_dist1, unchanged for pos_pos1/pos_dir1_dist1.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder02.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, BASE, get_scenes, plot_rays_overview

res = int(os.environ.get("RES", "512"))

CELL_A = BASE["cellACoarse"]  # 0.06

VARIANTS_02 = [
    ("pos_norm1__pos", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "enableVisCacheNormalAddr": False,
        "cellACoarse": 0.12,
        "cellBCoarse": 0.12,
    }),
    ("pos_norm1__pos1", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "enableVisCacheNormalAddr": False,
        "cellBCoarse": 10000.0,
    }),
    ("pos_norm1__dir1_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "enableVisCacheNormalAddr": False,
        "angularBCoarse": 360.0,
        "distBCoarse": 1000.0,
    }),
    ("pos_norm1__dir_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "enableVisCacheNormalAddr": False,
        "cellACoarse": 0.12,
        "angularBCoarse": 8.0,
        "distBCoarse": 1000.0,
    }),
    ("pos_norm1__dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "enableVisCacheNormalAddr": False,
        "cellACoarse": 0.12,
        "angularBCoarse": 8.0,
        "distBCoarse": 0.24,
    }),
]

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

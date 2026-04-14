"""
VisCache_Ladder06.py — Step 06: Multi-level cascade + auto-tune.

PRESET_MINIMAL + RR_ADAPTIVE + LEVELS_MULTI: adds multi-level LOD cascade
and automatic cell size derivation from scene bounds.
Builds on step 05 (single-level + footprint) by adding the LOD cascade.
Norm-active only, non-collapsed B-side.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, \
    FOOTPRINT_ON

res = int(os.environ.get("RES", "512"))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **FOOTPRINT_ON, "tableCapacity": 1 << 25}  # 32M entries (8x default)

VARIANTS_06 = make_norm_variants(base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(1, 0, 2)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="06",
        frame_configs=[(1, 0, 2, 1), (1, 0, 17, 1)],
        scene_file=scene_file,
        variants=VARIANTS_06,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

plot_rays_overview("06")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder04.py — Step 04: Multi-level cascade + auto-tune.

PRESET_MINIMAL + RR_ADAPTIVE + LEVELS_MULTI: adds multi-level LOD cascade
and automatic cell size derivation from scene bounds.
Norm-active only (norm1 dropped after steps 01-02), non-collapsed B-side.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder04.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI

res = int(os.environ.get("RES", "512"))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI}

VARIANTS_04 = make_norm_variants(base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(1, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="04",
        frame_configs=[(1, 1, 1), (1, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_04,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

plot_rays_overview("04")
_HEADLESS_SCRIPT_DONE = True

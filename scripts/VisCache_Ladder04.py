"""
VisCache_Ladder04.py — Step 04: Expanded SPP, norm-active variants.

Same preset as step 03 (PRESET_MINIMAL + RR_ADAPTIVE + QUANT_MID),
norm-active only (norm1 comparison done in steps 02-03), x1 and x16 SPP.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder04.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID, \
    FOOTPRINT_OFF

res = int(os.environ.get("RES", "512"))

VARIANTS_04 = make_norm_variants(quant=QUANT_MID, base=PRESET_MINIMAL)

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
        step_name="04",
        frame_configs=[(1, 0, 2, 1), (1, 0, 2, 16)],
        scene_file=scene_file,
        variants=VARIANTS_04,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **FOOTPRINT_OFF},
    )

plot_rays_overview("04")
_HEADLESS_SCRIPT_DONE = True

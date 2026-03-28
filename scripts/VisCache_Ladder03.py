"""
VisCache_Ladder03.py — Step 03: Expanded SPP, norm-active variants.

Same preset as step 02 (PRESET_MINIMAL + RR_ADAPTIVE + QUANT_MID),
norm-active only (norm1 comparison done in steps 01-02), x1 and x16 SPP.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder03.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID

res = int(os.environ.get("RES", "512"))

VARIANTS_03 = make_norm_variants(quant=QUANT_MID, base=PRESET_MINIMAL)

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
        step_name="03",
        frame_configs=[(1, 1, 1), (1, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_03,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=RR_ADAPTIVE,
    )

plot_rays_overview("03")
_HEADLESS_SCRIPT_DONE = True

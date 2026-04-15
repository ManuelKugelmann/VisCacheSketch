"""
VisCache_Ladder04.py — Step 04: Sample-count sweep, norm-active variants.

Same preset as step 03 (PRESET_MINIMAL + RR_ADAPTIVE + QUANT_MID), 3
norm-active B-side variants, swept across x1 / x4 / x8 / x16 SPP. Step 05 and
later narrow back to x1 / x4 only — this step is the full convergence arc.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder04.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_overviews, copy_summary_to_root, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID, \
    FOOTPRINT_OFF, SUBFRAME_2x2

res = int(os.environ.get("RES", "512"))

VARIANTS_04 = make_norm_variants(quant=QUANT_MID, base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4, 8, 16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="04",
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4), (1, 0, 1, 8), (1, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_04,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **FOOTPRINT_OFF, **SUBFRAME_2x2},
    )

plot_overviews("04")
copy_summary_to_root("04")
_HEADLESS_SCRIPT_DONE = True

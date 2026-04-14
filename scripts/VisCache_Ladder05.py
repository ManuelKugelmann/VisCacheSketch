"""
VisCache_Ladder05.py — Step 05: Footprint scale isolation (no LOD cascade).

Identical setup to step 04 (PRESET_MINIMAL + RR_ADAPTIVE + QUANT_MID,
single level, norm-active non-collapsed B-side, x1 and x16 SPP) but with
FOOTPRINT_ON — isolates the effect of the footprint-aware trust gate before
the LOD cascade is introduced at step 06.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder05.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID, \
    FOOTPRINT_ON

res = int(os.environ.get("RES", "512"))

VARIANTS_05 = make_norm_variants(quant=QUANT_MID, base=PRESET_MINIMAL)

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
        step_name="05",
        frame_configs=[(1, 0, 2, 1), (1, 0, 2, 16)],
        scene_file=scene_file,
        variants=VARIANTS_05,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **FOOTPRINT_ON},
    )

plot_rays_overview("05")
_HEADLESS_SCRIPT_DONE = True

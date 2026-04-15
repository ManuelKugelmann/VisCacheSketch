"""
VisCache_Ladder03.py — Step 03: Adaptive RR + quantization sweep (norm-active).

PRESET_MINIMAL + RR_ADAPTIVE, 4 quantization settings (qA→qD, fine→coarse)
× 3 non-collapsed norm-active B-side variants (pos, dir_dist1, dir_dist).
12 runs per scene. Footprint scale stays OFF (introduced at step 05).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder03.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, make_norm_variants, get_scenes, \
    plot_overviews, copy_summary_to_root, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, \
    FOOTPRINT_OFF, SUBFRAME_2x2

res = int(os.environ.get("RES", "512"))

VARIANTS_03 = []
for tag, quant in QUANT_SWEEP.items():
    VARIANTS_03.extend(make_norm_variants(quant=quant, base=PRESET_MINIMAL, quant_tag=tag))

STEP_OVERRIDES = {**RR_ADAPTIVE, **FOOTPRINT_OFF, **SUBFRAME_2x2}

for scene_file in get_scenes():
    run_variants(
        step_name="03",
        frame_configs=[(1, 0, 1, 1)],
        scene_file=scene_file,
        variants=VARIANTS_03,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

plot_overviews("03")
copy_summary_to_root("03")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder03.py — Step 03: Adaptive RR + quantization sweep (norm-active).

PRESET_MINIMAL + RR_ADAPTIVE, 3 quantization settings (qfine, qmid, qcoarse)
× 3 non-collapsed norm-active B-side variants (pos, dir_dist1, dir_dist) ×
x1 / x4 SPP = 18 runs per scene. Footprint scale stays OFF (introduced at
step 05).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder03.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, make_norm_variants, \
    get_scenes, finalize_step, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, \
    FOOTPRINT_OFF, SUBFRAME_2x2

STEP = "03"
res = int(os.environ.get("RES", "512"))

VARIANTS_03 = []
for tag, quant in QUANT_SWEEP.items():
    VARIANTS_03.extend(make_norm_variants(quant=quant, base=PRESET_MINIMAL, quant_tag=tag))

STEP_OVERRIDES = {**RR_ADAPTIVE, **FOOTPRINT_OFF, **SUBFRAME_2x2}

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_03,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
_HEADLESS_SCRIPT_DONE = True

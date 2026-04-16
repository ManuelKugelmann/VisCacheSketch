"""
VisCache_Ladder11.py — Step 11: threshold × footprintScale grid, MULTI-LEVEL.

Multi-level mirror of step 06. 3 thresholds × 3 scales = 9 variants. The
cascade changes how cellPixels varies with depth, so the threshold×scale
landscape may shift relative to single level.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder11.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "11"
res = int(os.environ.get("RES", "512"))

# Mirror step 06: boot is the primary knob, sweep boot and fix mature; fp
# scale axis uses the fp0/fp05/fp1 convention with alpha-ramp encoding.
# Aligned with step 05/06 THRESH_SCALE for cross-step comparability.
THRESH_SCALE = {
    "th_low":  {"bootThreshold":  2, "matureThreshold": 128},
    "th_mid":  {"bootThreshold":  4, "matureThreshold": 128},
    "th_high": {"bootThreshold": 16, "matureThreshold": 128},
}

FOOTPRINT_SCALES = {
    "fp0":  {"footprintScale": 0.0},
    "fp05": {"footprintScale": 0.5},
    "fp1":  {"footprintScale": 1.0},
}

QUANT_WINNER_TAG, QUANT_WINNER = "qmid", QUANT_SWEEP["qmid"]
WINNER_07 = f"pos_norm__pos__{QUANT_WINNER_TAG}"
BASE_11 = [v for v in make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_WINNER_TAG)
           if v[0] == WINNER_07]

VARIANTS_11 = []
for q_tag, q_params in THRESH_SCALE.items():
    for s_tag, s_params in FOOTPRINT_SCALES.items():
        for (name, overrides) in BASE_11:
            VARIANTS_11.append((f"{name}__{q_tag}_{s_tag}",
                                {**overrides, **q_params, **s_params}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        variants=VARIANTS_11,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, prev_winner=WINNER_07)
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder05.py — Step 05: Footprint-OFF threshold sweep.

Tight default threshold range (boot 8/16/32). Isolates the effect of boot/
mature thresholds WITHOUT the footprint gate modulating them — the fpOn
wider sweep happens in step 06; step 07 directly compares fpOn vs fpOff at
each's best-performing thresholds.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder05.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, FOOTPRINT_OFF, SUBFRAME_2x2

STEP = "05"
res = int(os.environ.get("RES", "512"))

# Semantic tags shared with step 06 so the "th_mid valley" can be read across
# both plots. Actual boot/mature values differ between steps — the footprint
# gate shifts the effective threshold scale, so the fpOn sweep lives in a
# different absolute range. low/mid/high describe the threshold values.
# Boot threshold is the primary knob (gates trust & RR); mature threshold
# only affects write-side stop. Sweep boot, keep mature fixed.
#
# Asymmetric bracketing centred on the empirical winner (boot=4 in the
# earlier {4,8,16} sweep). th_low=2 is the hard floor (cache with <2 samples
# is pure noise). th_high=16 overtrusts (few cells mature → weak RR).
# th_mid=4 is the candidate optimum; th_high gets the wider 4× gap so
# overtrust-degradation is clearly visible in the plot.
THRESH_SCALE = {
    "th_low":  {"bootThreshold":  2, "matureThreshold": 128},
    "th_mid":  {"bootThreshold":  4, "matureThreshold": 128},
    "th_high": {"bootThreshold": 16, "matureThreshold": 128},
}

# Step 03 quant-winner (qmid) + step 04 variant winner — carried forward.
QUANT_WINNER_TAG, QUANT_WINNER = "qmid", QUANT_SWEEP["qmid"]
WINNER_04 = f"pos_norm__pos__{QUANT_WINNER_TAG}"
BASE_05 = [v for v in make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_WINNER_TAG)
           if v[0] == WINNER_04]

VARIANTS_05 = []
for q_tag, q_params in THRESH_SCALE.items():
    for (name, overrides) in BASE_05:
        VARIANTS_05.append((f"{name}__{q_tag}_fpOff",
                            {**overrides, **q_params, **FOOTPRINT_OFF}))

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
        variants=VARIANTS_05,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP, prev_winner=WINNER_04)
_HEADLESS_SCRIPT_DONE = True

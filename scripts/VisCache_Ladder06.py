"""
VisCache_Ladder06.py — Step 06: Footprint-ON threshold × scale sweep.

3 threshold presets × 3 footprintScale values (0.5, 1.0, 2.0) = 9 variants.
Widens the step-05 sweep in two axes simultaneously: thresholds span 8×
stepping (th_low / th_mid / th_high) and scale brackets the default 1.0 with
±2× to expose sensitivity. Step 07 then sweeps only scale at the winner.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, SUBFRAME_2x2

STEP = "06"
res = int(os.environ.get("RES", "512"))

# Boot threshold is the primary knob; sweep boot, keep mature fixed.
# Aligned with step 05's THRESH_SCALE so the fp0 column of step 06 is
# directly comparable to step 05's fpOff sweep — same boot/mature values,
# only the footprint axis differs across steps.
THRESH_SCALE = {
    "th_low":  {"bootThreshold":  2, "matureThreshold": 128},
    "th_mid":  {"bootThreshold":  4, "matureThreshold": 128},
    "th_high": {"bootThreshold": 16, "matureThreshold": 128},
}

# footprintScale axis: 0 (off) / 0.5 / 1.0. Hue in the plot is shared by
# threshold (th_low/mid/high each a single color); fill alpha ramps with
# the scale value (fp0 hollow → fp1 solid).
FOOTPRINT_SCALES = {
    "fp0":  {"footprintScale": 0.0},
    "fp05": {"footprintScale": 0.5},
    "fp1":  {"footprintScale": 1.0},
}

QUANT_WINNER_TAG, QUANT_WINNER = "qmid", QUANT_SWEEP["qmid"]
WINNER_05 = f"pos_norm__pos__{QUANT_WINNER_TAG}"
BASE_06 = [v for v in make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_WINNER_TAG)
           if v[0] == WINNER_05]

VARIANTS_06 = []
for q_tag, q_params in THRESH_SCALE.items():
    for s_tag, s_params in FOOTPRINT_SCALES.items():
        for (name, overrides) in BASE_06:
            VARIANTS_06.append((f"{name}__{q_tag}_{s_tag}",
                                {**overrides, **q_params, **s_params}))

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
        variants=VARIANTS_06,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP, prev_winner=WINNER_05)
_HEADLESS_SCRIPT_DONE = True

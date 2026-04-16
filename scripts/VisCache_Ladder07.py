"""
VisCache_Ladder07.py — Step 07: footprintScale sweep.

Sweeps the unified footprint trust scale at step-06's th_mid winner with the
qmid B-side winner. footprintScale=0 is the old fpOff (pure bootThreshold);
1.0 is the old log2(cellPixels) fpOn; values >1 put more pressure on big
cells. Picks the scale carried into step 08's 2×2×2 head-to-head.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder07.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, SUBFRAME_2x2

STEP = "07"
res = int(os.environ.get("RES", "512"))

# Tag encodes the scale value: fp0 = 0.0, fp05 = 0.5, fp1 = 1.0, ...
# Pure-fp tags → _hue_key returns None → all markers share the B-core hue
# and fp scale is encoded by fill transparency only (monotonic single-hue
# ramp in the legend). See `_fp_alpha` / `_hue_key` in VisCache_LadderCommon.
FOOTPRINT_SWEEP = {
    "fp0":    {"footprintScale": 0.0},
    "fp025":  {"footprintScale": 0.25},
    "fp05":   {"footprintScale": 0.5},
    "fp1":    {"footprintScale": 1.0},
}

# Central threshold aligned with step 05/06 th_mid (boot=4, mature=128).
TH_MID = {"bootThreshold": 4, "matureThreshold": 128}

QUANT_WINNER_TAG, QUANT_WINNER = "qmid", QUANT_SWEEP["qmid"]
WINNER_06 = f"pos_norm__pos__{QUANT_WINNER_TAG}"
BASE_07 = [v for v in make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_WINNER_TAG)
           if v[0] == WINNER_06]

VARIANTS_07 = []
for s_tag, s_params in FOOTPRINT_SWEEP.items():
    for (name, overrides) in BASE_07:
        VARIANTS_07.append((f"{name}__th_mid_{s_tag}",
                            {**overrides, **TH_MID, **s_params}))

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
        variants=VARIANTS_07,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP, prev_winner=WINNER_06)
_HEADLESS_SCRIPT_DONE = True

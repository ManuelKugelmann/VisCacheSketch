"""
VisCache_Ladder08.py — Step 08: single-level head-to-head.

Cross-product of 2 quants (qmid winner, qcoarse alternate) × 2 thresholds
(th_mid winner, th_high alternate) × 3 footprints (fp0 off, fp025/fp05
sub-1 sweet-spot bracket from step 07) — 12 variants × 2 SPPs = 24 runs
per scene. Validates whether the sweep winners (step 05 threshold, step 07
footprint, step 03 quant) hold together when combined. Head-to-head
"ladder stress test" before going multi-level.

Update THRESHOLDS / SCALES / QUANTS below once step 05/06/07 data picks
firm winners — placeholders match current best-guess settings.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder08.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, SUBFRAME_2x2

STEP = "08"
res = int(os.environ.get("RES", "512"))

THRESHOLDS = {
    "th_mid":  {"bootThreshold":  4, "matureThreshold": 128},
    "th_high": {"bootThreshold": 16, "matureThreshold": 128},
}

FOOTPRINTS = {
    "fp0":   {"footprintScale": 0.0},
    "fp025": {"footprintScale": 0.25},
    "fp05":  {"footprintScale": 0.5},
}

QUANTS = ["qmid", "qcoarse"]

WINNER_07 = "pos_norm__pos__qmid"

VARIANTS_08 = []
for q_tag in QUANTS:
    base = [v for v in make_norm_variants(quant=QUANT_SWEEP[q_tag],
                                           base=PRESET_MINIMAL,
                                           quant_tag=q_tag)
            if v[0] == f"pos_norm__pos__{q_tag}"]
    for (name, overrides) in base:
        for th_tag, th_params in THRESHOLDS.items():
            for s_tag, s_params in FOOTPRINTS.items():
                VARIANTS_08.append((f"{name}__{th_tag}_{s_tag}",
                                    {**overrides, **th_params, **s_params}))

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
        variants=VARIANTS_08,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP, prev_winner=WINNER_07)
_HEADLESS_SCRIPT_DONE = True

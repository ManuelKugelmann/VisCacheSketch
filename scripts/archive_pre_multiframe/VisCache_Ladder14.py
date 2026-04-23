"""
VisCache_Ladder14.py — Step 14: multi-level head-to-head.

Multi-level mirror of step 08. Same 2 quants × 2 thresholds × 2 scales
cross-product with LEVELS_MULTI enabled. Validates whether the multi-level
sweep winners (steps 11/12/13) hold when combined — analogous to step 08's
role as the single-level "stress test".

Update THRESHOLDS / FOOTPRINTS / QUANTS below once step 10/11 data picks
firm winners.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder14.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "14"
res = int(os.environ.get("RES", "512"))

THRESHOLDS = {
    "ct4":  {"bootThreshold":  4, "matureThreshold": 128},
    "ct16": {"bootThreshold": 16, "matureThreshold": 128},
}

FOOTPRINTS = {
    "fp0":   {"bootThresholdFactorFootprintPx": 0.0},
    "fp025": {"bootThresholdFactorFootprintPx": 0.25},
    "fp05":  {"bootThresholdFactorFootprintPx": 0.5},
}

QUANTS = ["qa012", "qa036"]

WINNER_11 = "pos_norm__pos__qa012"

VARIANTS_14 = []
for q_tag in QUANTS:
    base = [v for v in make_norm_variants(quant=QUANT_SWEEP[q_tag],
                                           base=PRESET_MINIMAL,
                                           quant_tag=q_tag)
            if v[0] == f"pos_norm__pos__{q_tag}"]
    for (name, overrides) in base:
        for th_tag, th_params in THRESHOLDS.items():
            for s_tag, s_params in FOOTPRINTS.items():
                VARIANTS_14.append((f"{name}__{th_tag}_{s_tag}",
                                    {**overrides, **th_params, **s_params}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

for scene_file in get_scenes(default=MULTI_LEVEL_SCENES):
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
        variants=VARIANTS_14,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, prev_winner=WINNER_11,
              ref_step="12",
              ref_variant="pos_norm__pos__qa012__ct16_vt005_fp0_fd0",
              ref_label="step-12 carry")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder10.py — Step 10: Level-count sweep (cascade depth).

Entry point into the multi-level ladder. Holds everything from step 07's
single-level winner fixed (qmid, pos B-side, th_mid boot=16/mature=256,
footprint ON) and sweeps `numLevels` at {4, 6, 8, 16}. Picks the cascade
depth carried forward into the threshold × footprint sweep (step 11) and
2×2×3 head-to-head (step 14).

Auto-tuned cell sizes (autoTuneCells=True) adapt per level, so the sweep
exposes "how deep does the cascade need to be before diminishing returns".

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder10.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, FOOTPRINT_ON, SUBFRAME_2x2

STEP = "10"
res = int(os.environ.get("RES", "512"))

# Level-count sweep (tag = Ln). autoTuneCells=True lets the cascade adapt
# finest/coarsest cell sizes to scene bounds regardless of depth.
LEVEL_COUNTS = {
    "L4":  {"numLevels":  4, "autoTuneCells": True},
    "L6":  {"numLevels":  6, "autoTuneCells": True},
    "L8":  {"numLevels":  8, "autoTuneCells": True},
    "L16": {"numLevels": 16, "autoTuneCells": True},
}

# Fixed central threshold aligned with step 05/06 th_mid (boot=4, mature=128).
TH_MID = {"bootThreshold": 4, "matureThreshold": 128}

QUANT_WINNER_TAG, QUANT_WINNER = "qmid", QUANT_SWEEP["qmid"]
WINNER_07 = f"pos_norm__pos__{QUANT_WINNER_TAG}"
BASE_10 = [v for v in make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_WINNER_TAG)
           if v[0] == WINNER_07]

VARIANTS_10 = []
for l_tag, l_params in LEVEL_COUNTS.items():
    for (name, overrides) in BASE_10:
        VARIANTS_10.append((f"{name}__{l_tag}",
                            {**overrides, **l_params, **TH_MID, **FOOTPRINT_ON}))

# Cascade needs more slots at deep counts — 32M entries (8× default).
STEP_OVERRIDES = {**RR_ADAPTIVE, **SUBFRAME_2x2,
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
        variants=VARIANTS_10,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, prev_winner=WINNER_07)
_HEADLESS_SCRIPT_DONE = True

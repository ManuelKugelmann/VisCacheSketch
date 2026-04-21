"""
VisCache_Ladder06.py — Step 06: jitter-before-quantize head-to-head.

Takes the step-05 winner (pos_norm__pos + picked quantAB + boot threshold)
and overlays the two jitter flavors:

  jitterFilter  — per-position-seed jitter (asuint(pos) seed). Soft cell
                  boundaries. Each sample gets independent jitter → stochastic
                  grid → acts as a 3D reconstruction kernel.

  jitterCell    — per-cell-index-seed jitter (baseIdx seed, Binder 2018).
                  Each cell redirects by a fixed offset → grid shifts per
                  cell → boundaries stay hard but land at new positions.

3×3 = 9 variants × {x1, x4 SPP}: jitterFilter ∈ {0.0, 0.5, 1.0} × jitterCell ∈
{0.0, 0.5, 1.0}. Tag convention is jf<val×10 pad-2> so jf00=0.0, jf05=0.5,
jf10=1.0 (same for jc).

  jf00_jc00  no jitter                   (reference / step-05 reprint)
  jf10_jc00  filter-only, full scale      (3D reconstruction kernel)
  jf00_jc10  cell-only, full scale        (Binder-style grid shift)
  jf10_jc10  both, offsets summed (±1)   (stacked)
  …plus the 5 mid-scale combinations with 0.5 offsets.

Scales are in "cells": 1.0 = standard ±0.5-cell offset at the current level's
cellSize. Jitter defaults to 0 in every earlier step — this is the first
ladder step where it is non-zero.

Step-05 winner baked in: pos_norm__pos + qA024_qB036 + th2 (see WINNER_*
constants below for the selection criterion — best ray savings subject to
err ≤ median+25% AND blob ≤ median+25%, noise informational only).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, write_picks_meta, pick_top_variants_per_bvariant, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "09"
res = int(os.environ.get("RES", "512"))

# Step-05 winner: qA024_qB036 + th2. Selection criterion:
#   best ray savings (lowest rays_traced_pct in the weighted "All" column,
#   with 32PointLights × 3) subject to err and blob both being non-positive
#   OR <= median+25%. qA024_qB036__th2 wins with rays=40.1, err=-1.43, blob=8.4
#   — lowest rays among qualifying. Noise is informational, not gated.
WINNER_QUANT_TAG = "qA024_qB036"
WINNER_QUANT = {"posACoarse": 0.24, "posBCoarse": 0.36}
WINNER_THRESH_TAG = "th2"
WINNER_THRESH = {"bootThreshold": 2, "matureThreshold": 128}
NORMAL_A = 60.0

WINNER_NAME = f"pos_norm__pos__{WINNER_QUANT_TAG}__{WINNER_THRESH_TAG}"
WINNER_BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    **WINNER_QUANT,
    **WINNER_THRESH,
}

# Companion quant one step finer on both axes — jitter blurs across cell
# boundaries, effectively coarsening the accumulation window. Running a
# variant where qA and qB are each one step smaller (0.12 / 0.18 vs the
# step-05 0.24 / 0.36 winner) tests whether halving the cell size
# compensates for the jitter-induced blur.
FINE_QUANT_TAG = "qA012_qB018"
FINE_QUANT = {"posACoarse": 0.12, "posBCoarse": 0.18}
FINE_NAME = f"pos_norm__pos__{FINE_QUANT_TAG}__{WINNER_THRESH_TAG}"
FINE_BASE = {**WINNER_BASE, **FINE_QUANT}

QUANT_FLAVORS = [
    (WINNER_NAME, WINNER_BASE),
    (FINE_NAME,   FINE_BASE),
]

JITTER_VALUES = [0.0, 0.5, 1.0]

def _jt(v): return f"{int(round(v * 10)):02d}"

VARIANTS_06 = []
for (qbase_name, qbase_ovr) in QUANT_FLAVORS:
    for jf in JITTER_VALUES:
        for jc in JITTER_VALUES:
            tag = f"jf{_jt(jf)}_jc{_jt(jc)}"
            VARIANTS_06.append((f"{qbase_name}__{tag}",
                                {**qbase_ovr,
                                 "jitterFilter": jf,
                                 "jitterCell":   jc}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **SUBFRAME_2x2}

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
        step_overrides=STEP_OVERRIDES,
    )

# Step 06's picker output feeds the upcoming multi-level step 10.
# Manual carry: jf05_jc00 on the step-05 winner quant — filter jitter at mid
# strength softens cell boundaries without the grid-shift cost of jc; stacking
# jc on top adds rays and firefly noise without visible artifact benefit.
# Overrides the auto-picker's ranking because jitter is a visual/artifact call,
# not purely a rays+err metric.
CARRY_06 = f"{WINNER_NAME}__jf05_jc00"
finalize_step(STEP, inherited_winners=[WINNER_NAME, FINE_NAME],
              carried_winners=[CARRY_06])
write_picks_meta(STEP, inherited_from="05", inherited=[WINNER_NAME, FINE_NAME],
                  carried={"pos": [CARRY_06]}, rule=_DEFAULT_PICKER_RULE,
                  notes="Manual carry: jf05_jc00 on step-05 winner quant — "
                        "filter jitter at mid strength softens boundaries "
                        "without the extra rays/firefly cost of stacking jc.")
_HEADLESS_SCRIPT_DONE = True

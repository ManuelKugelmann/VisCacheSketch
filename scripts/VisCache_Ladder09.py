"""
VisCache_Ladder09.py — Step 09: jitter sweep (single level).

Inherits the step-05 carry via read_carried_winner("05") + parse_variant_tags,
plus a companion quant with posA/posB halved relative to that carry.
Sweeps both jitter flavors on each:

  jitterFilter  — per-position-seed jitter (asuint(pos) seed). Soft cell
                  boundaries. Each sample gets independent jitter → stochastic
                  grid → acts as a 3D reconstruction kernel.

  jitterCell    — per-cell-index-seed jitter (baseIdx seed, Binder 2018).
                  Each cell redirects by a fixed offset → grid shifts per
                  cell → boundaries stay hard but land at new positions.

2 quant × 3×3 jitter = 18 variants × {x1, x4 SPP}: jitterFilter ∈ {0.0, 0.5,
1.0} × jitterCell ∈ {0.0, 0.5, 1.0}. Tag convention is jf<val×10 pad-2> so
jf00=0.0, jf05=0.5, jf10=1.0 (same for jc).

  jf00_jc00  no jitter                   (reference / step-05 reprint)
  jf10_jc00  filter-only, full scale      (3D reconstruction kernel)
  jf00_jc10  cell-only, full scale        (Binder-style grid shift)
  jf10_jc10  both, offsets summed (±1)    (stacked)
  …plus the 5 mid-scale combinations with 0.5 offsets.

Scales are in "cells": 1.0 = standard ±0.5-cell offset at the current level's
cellSize. Jitter defaults to 0 in every earlier step — this is the first
ladder step where it is non-zero.

Companion fine quant tests whether halving cell size compensates the
jitter-induced blur across cell boundaries.

Usage:
    Mogwai.exe --headless -s scripts/VisCache_Ladder09.py
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, write_picks_meta, pick_top_variants_per_bvariant, \
    read_carried_winner, parse_variant_tags, \
    _DEFAULT_PICKER_RULE, PRESET_MINIMAL, RR_ADAPTIVE, BAYER_2x2

STEP = "09"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("05")
if INHERITED_NAME is None:
    raise RuntimeError("[09] step 05 picks.json missing — run step 05 first.")
INHERITED_OVERRIDES = parse_variant_tags(INHERITED_NAME)
NORMAL_A = 60.0

INHERITED_BASE = {
    **PRESET_MINIMAL,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheNormalAddr": True,
    "normalACoarse": NORMAL_A,
    "matureThreshold": 128,
    **INHERITED_OVERRIDES,
}

# Companion: halve posA / posB off the inherited carry. The step-03 quant
# grid is power-of-2 spaced, so /2 is "one step finer" on both axes.
FINE_OVERRIDES = dict(INHERITED_OVERRIDES)
FINE_OVERRIDES["posACoarse"] = INHERITED_OVERRIDES["posACoarse"] / 2.0
FINE_OVERRIDES["posBCoarse"] = INHERITED_OVERRIDES["posBCoarse"] / 2.0
FINE_NAME = re.sub(
    r"qA\d+_qB\d+",
    f"qA{int(round(FINE_OVERRIDES['posACoarse'] * 100)):03d}"
    f"_qB{int(round(FINE_OVERRIDES['posBCoarse'] * 100)):03d}",
    INHERITED_NAME,
)
FINE_BASE = {**INHERITED_BASE, **FINE_OVERRIDES}

QUANT_FLAVORS = [
    (INHERITED_NAME, INHERITED_BASE),
    (FINE_NAME,      FINE_BASE),
]

JITTER_VALUES = [0.0, 0.5, 1.0]

def _jt(v): return f"{int(round(v * 10)):02d}"

VARIANTS_09 = []
for (qbase_name, qbase_ovr) in QUANT_FLAVORS:
    for jf in JITTER_VALUES:
        for jc in JITTER_VALUES:
            tag = f"jf{_jt(jf)}_jc{_jt(jc)}"
            VARIANTS_09.append((f"{qbase_name}__{tag}",
                                {**qbase_ovr,
                                 "jitterFilter": jf,
                                 "jitterCell":   jc}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **BAYER_2x2}

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
        frame_configs=[(1, 0, 1, 1), (1, 0, 4, 1)],
        scene_file=scene_file,
        variants=VARIANTS_09,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

# No carry yet — jitter is a visual/artifact call that still wants eyes on
# the plates before picking. Likely choice is jf05_jc05 (both at mid strength)
# but pending inspection. finalize_step without carried_winners still renders
# the inherited-winner halos; picks.json records the step with carried empty.
finalize_step(STEP, inherited_winners=[INHERITED_NAME, FINE_NAME],
              ref_step="05", ref_variant=INHERITED_NAME,
              ref_label="step-05 carry (no jitter)")
write_picks_meta(STEP, inherited_from="05",
                  inherited=[INHERITED_NAME, FINE_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="No carry yet — awaiting visual pick (likely jf05_jc05).")
_HEADLESS_SCRIPT_DONE = True

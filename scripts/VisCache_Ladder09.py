"""
VisCache_Ladder09.py — Step 09: jitter-before-quantize head-to-head.

Takes the step-08 winner (pos_norm__pos__qmid + th_mid + fp1 — adjust below
once step-08 data lands) and overlays the two jitter flavors:

  jitterFilter  — per-position-seed jitter (asuint(pos) seed). Soft cell
                  boundaries. Each sample gets independent jitter → stochastic
                  grid → acts as a 3D reconstruction kernel.

  jitterCell    — per-cell-index-seed jitter (baseIdx seed, Binder 2018).
                  Each cell redirects by a fixed offset → grid shifts per
                  cell → boundaries stay hard but land at new positions.

Four variants × {x1, x4 SPP}:

  jf0_jc0   no jitter                          (reference / step-08 winner reprint)
  jf1_jc0   jitter-filter only                 (3D reconstruction kernel)
  jf0_jc1   jitter-cell only                   (Binder-style grid shift)
  jf1_jc1   both, offsets summed (±1.0 cells)  (stacked)

Both scales are in "cells": 1.0 = standard ±0.5-cell offset at the current
level's cellSize (the shader multiplies by cellSize, so multi-level caches
auto-scale). Jitter defaults to 0 in every earlier step — this is the first
ladder step where it is non-zero.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder09.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, QUANT_SWEEP, SUBFRAME_2x2

STEP = "09"
res = int(os.environ.get("RES", "512"))

# Step-08 winner: pos_norm__pos + qmid + th_mid + fp025.
WINNER_08_BASE_NAME = "pos_norm__pos__qmid"
WINNER_08_THRESH  = {"bootThreshold": 4, "matureThreshold": 128}  # th_mid
WINNER_08_SCALE   = {"footprintScale": 0.25}                       # fp025

JITTER_VARIANTS = [
    ("jf0_jc0", {"jitterFilter": 0.0, "jitterCell": 0.0}),  # neither — baseline reference
    ("jf1_jc0", {"jitterFilter": 1.0, "jitterCell": 0.0}),
    ("jf0_jc1", {"jitterFilter": 0.0, "jitterCell": 1.0}),
    ("jf1_jc1", {"jitterFilter": 1.0, "jitterCell": 1.0}),
]

# Base: the step-08 winner variant (no jitter). Jitter variants layer on top.
_base_variants = [v for v in make_norm_variants(quant=QUANT_SWEEP["qmid"],
                                                 base=PRESET_MINIMAL,
                                                 quant_tag="qmid")
                  if v[0] == WINNER_08_BASE_NAME]
assert _base_variants, f"could not find winner base {WINNER_08_BASE_NAME!r}"
_winner_name, _winner_overrides = _base_variants[0]
_winner_overrides = {**_winner_overrides, **WINNER_08_THRESH, **WINNER_08_SCALE}

VARIANTS_09 = [
    (f"{_winner_name}__{jtag}", {**_winner_overrides, **joverrides})
    for (jtag, joverrides) in JITTER_VARIANTS
]

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
        variants=VARIANTS_09,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP, prev_winner=f"{_winner_name}__jf1_jc1")
_HEADLESS_SCRIPT_DONE = True

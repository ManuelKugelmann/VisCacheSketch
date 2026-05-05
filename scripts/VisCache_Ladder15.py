"""
VisCache_Ladder15.py - Step 15: jitter activation on step-14 winner.

STATUS: Tests jitterFilter / jitterCell on top of step-14 winner config
(cell4x4 ct=16 vt=0.01 pm=0.02 multi-level). Step-14 used NO_JITTER
exclusively; this step quantifies whether activating jitter at the
universal winner reduces local regression (worse_artifact_5_pct).

  jitterFilter - per-position-seed jitter, 3D reconstruction kernel.
                 Soft cell boundaries; samples land at random offsets.
                 Expected effect: smooths cell-boundary artifacts.
  jitterCell   - per-cell-index-seed jitter (Binder 2018, hard
                 boundaries shifted per cell). Each cell offset by a
                 fixed amount; boundaries still hard but land at
                 different positions across frames -> temporal averaging.

Sweep: 4 variants on hard-shadow + Bistro + Sponza:
  jf00_jc00  no jitter (step-14 reference)
  jf10_jc00  filter-only
  jf00_jc10  cell-only
  jf10_jc10  both stacked

Scales in "cells": 1.0 = standard +-0.5-cell offset at the current
level's cellSize.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "15"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2
FD = 16
CT = 16     # step-14 winner ct
VT = 0.01
PM = 0.02

def _jt(jf, jc):
    return f"jf{int(round(jf*100)):03d}_jc{int(round(jc*100)):03d}"

# Scale sweep: 0, 0.25, 0.5, 1.0 along the most-promising axis (jitterCell)
# plus a small filter-only and stacked sample. Total 7 variants.
JITTER_PAIRS = [
    (_jt(0.0,    0.0  ), 0.0,    0.0  ),   # reference (universal winner)
    (_jt(0.125,  0.125), 0.125,  0.125),   # very-low both-axes (grid-dither)
    (_jt(0.0,  0.25), 0.0,  0.25),   # cell-only weak
    (_jt(0.0,  0.5 ), 0.0,  0.5 ),   # cell-only mid
    (_jt(0.0,  1.0 ), 0.0,  1.0 ),   # cell-only full
    (_jt(0.25, 0.0 ), 0.25, 0.0 ),   # filter-only weak
    (_jt(0.5,  0.0 ), 0.5,  0.0 ),   # filter-only mid
    (_jt(0.5,  0.5 ), 0.5,  0.5 ),   # both mid
]

DEFAULT_SCENES = ["CornellBox_1PointLight", "CornellBox_32PointLights",
                  "BistroInterior", "Sponza"]

BASE_15 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS_15 = []
for (base_name, base_overrides) in BASE_15:
    for jtag, jf, jc in JITTER_PAIRS:
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell4x4_ct{CT:03d}_vt010_pm002_{jtag}"
        VARIANTS_15.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":                 CT,
            "matureThreshold":               max(64, CT * 4),
            "varThreshold":                  VT,
            "stderrThreshold":               0.0,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM,
            "bayerN":                        BAYER_N,
            "enableDecayAutoTune":           False,
            "jitterFilter":                  jf,
            "jitterCell":                    jc,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4, 16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=MF_CONFIGS,
        scene_file=scene_file,
        variants=VARIANTS_15,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[],
              ref_step="14",
              ref_variant="pos_norm__pos__qa012__bayer2x2_cell4x4_ct0016_vt010_pm002",
              ref_label="step-14 winner (no jitter)")
write_picks_meta(STEP, inherited_from="14", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Jitter activation on step-14 winner (cell4x4 ct=16). "
                        "Tests if jitter reduces local cache regression "
                        "(worse_artifact_5_pct) at the cost of soft cell "
                        "boundaries. 4 variants x 3 SPP x 4 scenes = 48 runs.")
_HEADLESS_SCRIPT_DONE = True

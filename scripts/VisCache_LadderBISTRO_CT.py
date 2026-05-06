"""
VisCache_LadderBISTRO_CT.py — generalize Sponza ct/vt finding to Bistro.

SPONZA_CT showed ct=2 → ct=8 breaks the cell4×4 saturation; SPONZA_VT
showed trust gates re-activate at ct=8 with SPP-dependent optima
(x4 wants vt=0.10, x16 wants vt=0.001). Test whether the same framework
applies to BistroExterior + BistroInterior.

Sweep: cell4×4 + bayer2×2 + pm=0.02 + 4-corner test:
  (ct=2,  vt=0.10)   — step-18 baseline (saturated on Sponza)
  (ct=8,  vt=0.10)   — Sponza x4 winner
  (ct=8,  vt=0.001)  — Sponza x16 winner
  (ct=32, vt=0.001)  — even higher ct (probe diminishing returns)
on BistroExt + BistroInt at x{4, 16}.

4 variants × 2 scenes × 2 SPPs = 16 captures. ~10-15 min.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s BISTRO_CT \
        -c "BistroExterior,BistroInterior"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "BISTRO_CT"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; PM = 0.02

# 4-corner test in (ct, vt) space:
CORNERS = [(2, 0.100), (8, 0.100), (8, 0.001), (32, 0.001)]

DEFAULT_SCENES = ["BistroExterior", "BistroInterior"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (ct, vt) in CORNERS:
        cell_n = int(round(CELL_PX**0.5))
        ct_tag = f"ct{ct:03d}"
        vt_tag = f"vt{int(round(vt*1000)):04d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{vt_tag}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   ct,
            "matureThreshold": max(64, ct * 4),
            "varThreshold":    vt,
            "stderrThreshold": 0.0,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":        CELL_PX,
            "cascadeWindowForward":           12,
            "enableHierarchicalConsistency":  False,
            "hierarchicalMuTolerance":        0.20,
            "accelDecayDisagreeThresh":       0.0,
            "pMin":                           PM,
            "bayerN":                         BAYER_N,
            "enableDecayAutoTune":            False,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, "tableCapacity": 1 << 25}
MF_CONFIGS = [(0, 0, 4, 1), (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    run_baseline(step_name="00", frame_configs=[(0, 0, 1)],
                  scene_file=scene_file, resX=res, resY=res,
                  extra_spp=[4, 16], mogwai_globals=globals())
    run_variants(step_name=STEP, frame_configs=MF_CONFIGS,
                  scene_file=scene_file, variants=VARIANTS,
                  resX=res, resY=res, mogwai_globals=globals(),
                  step_overrides=STEP_OVERRIDES)

finalize_step(STEP, inherited_winners=[])
_HEADLESS_SCRIPT_DONE = True

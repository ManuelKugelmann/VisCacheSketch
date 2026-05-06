"""
VisCache_LadderSPONZA_VT.py — vt sweep at ct=8 on Sponza.

Tests whether the step-18 "trust gates have zero leverage" finding lifts
once ct is no longer the bottleneck. SPONZA_CT showed ct=8 is the knee
on Sponza x4 (art5 23.36 → 17.53 vs ct=2). At ct=8, do vt/se/cwf gates
now produce variation — or is the residual art5=17.53 floor structural?

Sweep: cell4×4 + bayer2×2 + ct=8 + pm=0.02 + vt ∈ {0.001, 0.01, 0.05,
0.10, 0.30, 1.0} on Sponza, x{4, 16}.

Six variants × 2 SPPs = 12 captures. ~7-10 min Mogwai.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_VT -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_VT"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02
VT_VALUES = [0.001, 0.010, 0.050, 0.100, 0.300, 1.000]

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for vt in VT_VALUES:
        cell_n = int(round(CELL_PX**0.5))
        vt_tag = f"vt{int(round(vt*1000)):04d}"
        ct_tag = f"ct{CT:03d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{vt_tag}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
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

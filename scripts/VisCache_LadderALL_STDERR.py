"""
VisCache_LadderALL_STDERR.py — validate stderr=0.10 across all scenes.

SPONZA_STDERR established stderr=0.10 as the principled SPP-adaptive
trust gate: at x4 it refuses trust on cold cells (matching strict-vt
behaviour); at x16 it trusts mature cells aggressively (matching
Wilson_e40 / loose-vt regime, relmse 2.5× better than vt=0.001).

This sweep tests whether the result generalizes across the full scene
matrix at single-bounce DI:

  Cornell × {1AL, 1PL, 3AL, 32PL}  +  Sponza  +  BistroExt  +  BistroInt

Two configs per scene:
  - vt001_seoff: vt=0.001 baseline (per-SPP-strict reference)
  - se010:       stderr=0.10  (the new candidate canonical)

7 scenes × 2 configs × 2 SPPs = 28 captures. ~30 min.

Pass criterion: at every scene, stderr=0.10 produces at LEAST se005-like
behaviour at x4 (refuses trust, no quality regression vs vt=0.001) AND
at x16 either matches or improves on vt=0.001's metric battery (relmse,
PSNR, RMSE, art5). Known firefly-class scenes (32PL, BistroInt) may
amplify the relmse improvement; penumbra-class single-light scenes
(Cornell_1AL, Sponza) should hold the art5 trade.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s ALL_STDERR
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "ALL_STDERR"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02

# (label, vt, se)
VARIANTS_PER_BASE = [
    ("vt001_seoff", 0.001, 0.00),  # per-SPP-strict reference
    ("se010",       0.001, 0.10),  # the new candidate canonical
]

DEFAULT_SCENES = [
    "CornellBox_1AreaLight", "CornellBox_1PointLight",
    "CornellBox_3AreaLights", "CornellBox_32PointLights",
    "Sponza", "BistroExterior", "BistroInterior",
]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, vt, se) in VARIANTS_PER_BASE:
        cell_n = int(round(CELL_PX**0.5))
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        ct_tag = f"ct{CT:03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{label}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
            "varThreshold":    vt,
            "stderrThreshold": se,
            "wilsonZSquared":  0.0,
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

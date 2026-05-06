"""
VisCache_LadderSPONZA_AC.py — Agresti-Coull shrinkage on cached μ.

Tests whether Bayesian shrinkage of the cached cell μ̃ = (X+z²/2)/(N+z²)
stabilises CV+RRR cold-cell variance. Orthogonal to the trust gate
(stderr=0.10 stays canonical); changes WHAT the cache stores at low N,
not WHEN we trust it.

Sweep at Sponza x{4, 16}, fixed canonical (cell4×4 bayer2×2 ct=8 stderr=0.10
pm=0.02), with z² ∈ {0=off (raw μ), 1, 4, 8, 16}:

  - ac0:  raw μ = X/N (legacy, baseline)
  - ac1:  z²=1   → "add 0.5, 1" — mild prior
  - ac4:  z²=4   → "add 2, 4"   — 95%-CI Beta(2,2) prior (canonical A-C)
  - ac8:  z²=8   → stronger
  - ac16: z²=16  → very strong shrinkage

Pass criterion: at least one z² > 0 produces a detectable improvement
on relmse / RMSE / PSNR at one or both SPPs without regressing perceptual
metrics (art5, OkLab err) by more than 0.1pp. Hypothesis: the strict
"variance reduction at cold cells" pitch implies wins at x4 (cold cell
regime); x16 mature cells should be unaffected (shrinkage vanishes).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_AC -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_AC"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02; SE = 0.10

# (label, muShrinkZSquared)
AC_VARIANTS = [
    ("ac00",  0.0),   # baseline (raw μ)
    ("ac01",  1.0),   # mild prior
    ("ac04",  4.0),   # canonical A-C ("add 2,4")
    ("ac08",  8.0),
    ("ac16",  16.0),
]

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, ac) in AC_VARIANTS:
        cell_n = int(round(CELL_PX**0.5))
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        ct_tag = f"ct{CT:03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{label}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
            "varThreshold":    0.001,
            "stderrThreshold": SE,
            "wilsonZSquared":  0.0,
            "muShrinkZSquared": ac,
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

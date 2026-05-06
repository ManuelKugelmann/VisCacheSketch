"""
VisCache_LadderSPONZA_WILSON.py — Wilson-interval gate sweep on Sponza.

Validates LADDER_PLAN improvement A: replace varThreshold with binomial
Wilson confidence interval to absorb the SPP-dependent vt finding from
SPONZA_VT (x4 wants vt=0.10, x16 wants vt=0.001).

Sweep at Sponza x{4, 16}:
  - wilsonZSquared ∈ {0 (off — vt=0.10 baseline), 3.8416 (95%), 6.6349 (99%)}
  - wilsonEps ∈ {0.005, 0.01, 0.02, 0.05}

Plus reference rows from SPONZA_VT carry: vt=0.10 (x4 optimum) and vt=0.001
(x16 optimum) at wilson off. The Wilson sweep should land within 1% of
each per-SPP optimum on full metric battery — ONE config across both x4
and x16 → strict improvement (collapses the per-SPP carry table).

Pass criterion: at wilsonZSquared=3.8416 wilsonEps=0.01 (95% CI / 1%
margin), Sponza x4 art5 ≤ 18 (matches vt=0.10 carry's 17.53) AND x16
art5 ≤ 16 (matches vt=0.001 carry's 15.21). Full-metric battery
checked too — RMSE / relmse / PSNR should not regress.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_WILSON -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_WILSON"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02

# Reference points: vt=0.10 (x4 carry) and vt=0.001 (x16 carry).
# Then Wilson sweep at wz∈{0, 3.8416, 6.6349} × eps∈{0.005, 0.01, 0.02, 0.05}.
WILSON_VARIANTS = [
    # (label, vt, wz, eps)
    ("vt100_wzoff",     0.100, 0.0, 0.01),  # SPONZA_VT x4 carry reference
    ("vt001_wzoff",     0.001, 0.0, 0.01),  # SPONZA_VT x16 carry reference
    ("wz38_eps005",     0.001, 3.8416, 0.005),  # 95% CI, ε=0.005 (strict)
    ("wz38_eps050",     0.001, 3.8416, 0.050),  # 95% CI, ε=0.05
    ("wz38_eps100",     0.001, 3.8416, 0.100),  # 95% CI, ε=0.10 (loose)
    ("wz38_eps200",     0.001, 3.8416, 0.200),  # 95% CI, ε=0.20 (very loose)
    ("wz38_eps400",     0.001, 3.8416, 0.400),  # 95% CI, ε=0.40 (vt=0.10-like trust window)
    ("wz66_eps200",     0.001, 6.6349, 0.200),  # 99% CI, ε=0.20 (Wilson stricter via larger z)
]

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, vt, wz, eps) in WILSON_VARIANTS:
        cell_n = int(round(CELL_PX**0.5))
        ct_tag = f"ct{CT:03d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{label}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
            "varThreshold":    vt,
            "wilsonZSquared":  wz,
            "wilsonEps":       eps,
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

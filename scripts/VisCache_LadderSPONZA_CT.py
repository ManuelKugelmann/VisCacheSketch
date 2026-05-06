"""
VisCache_LadderSPONZA_CT.py — naive raise-base-ct test on Sponza.

Tests the user's "if any samples disagree we know penumbra; if all agree
we can't be sure → need more N" reframe by sweeping ct on the saturated
cell4×4 ct=2 baseline. If art5 drops monotonically with ct, the trust-
gate exhaustion finding from step 18 was just "premature all-same
trust" and naive raise-base-ct is the fix. If art5 stays flat at ~23.4,
the saturation is structural (cell estimator itself is biased on the
affected pixels) and ct can't fix it.

  cell4×4 + bayer2×2 + vt=0.10 + pm=0.02 + ct ∈ {2, 4, 8, 16, 32, 64}
  Sponza only, x{1, 4, 16}.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_CT -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_CT"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16   # cell4×4 = 16 px²
VT = 0.10; PM = 0.02
CT_VALUES = [2, 4, 8, 16, 32, 64]

DEFAULT_SCENES = ["Sponza"]

# Pull just the pos__pos__qa012 variant tuple from make_norm_variants and
# use its overrides as the per-variant base.
BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for ct in CT_VALUES:
        cell_n = int(round(CELL_PX**0.5))
        ct_tag = f"ct{ct:03d}"
        vt_tag = f"vt{int(round(VT*1000)):03d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{vt_tag}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   ct,
            "matureThreshold": max(64, ct * 4),
            "varThreshold":    VT,
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
MF_CONFIGS = [(0, 0, 1, 1), (0, 0, 4, 1), (0, 0, 16, 1)]

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

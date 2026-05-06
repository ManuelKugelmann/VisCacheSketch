"""
VisCache_LadderBISTRO_ADD.py — accelDecayDisagreeThresh sweep on Bistro.

BISTRO_CT showed Bistro saturation is structural (ct/vt zero-leverage).
Diagnosis: bias-locked cells from Bayer-stratified geometry sampling.
accelDecayDisagreeThresh (existing param, default 0.0) half-decays cell
count when |new_sample − μ| > threshold — actively breaks lock-in when
sampling pattern shifts (Bayer phase rotation eventually hits the
visible side; |1 − 0| = 1.0 triggers regardless of threshold).

Sweep: cell4×4 + bayer2×2 + ct=8 + vt=0.10 + pm=0.02 + adddt ∈
{0.0 (off), 0.05, 0.10, 0.30, 0.50}. BistroExt + BistroInt at x{4, 16}.

5 variants × 2 scenes × 2 SPPs = 20 captures. ~12-15 min.

Pass criterion: art5 drops below the BISTRO_CT bit-identical floor
(BiI 29.93/42.87, BiE 21.78) by ≥2pp at any threshold → mechanism works
on bias-locked structural saturation. If art5 stays at the floor → bias
too geometric for half-decay; need full-reset-on-disagree or stochastic
cell migration.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s BISTRO_ADD \\
        -c "BistroExterior,BistroInterior"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "BISTRO_ADD"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; VT = 0.10; PM = 0.02
ADDDT_VALUES = [0.00, 0.05, 0.10, 0.30, 0.50]

DEFAULT_SCENES = ["BistroExterior", "BistroInterior"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for adddt in ADDDT_VALUES:
        cell_n = int(round(CELL_PX**0.5))
        ct_tag = f"ct{CT:03d}"
        vt_tag = f"vt{int(round(VT*1000)):03d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        ad_tag = f"ad{int(round(adddt*100)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{vt_tag}_{pm_tag}_{ad_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
            "varThreshold":    VT,
            "stderrThreshold": 0.0,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":        CELL_PX,
            "cascadeWindowForward":           12,
            "enableHierarchicalConsistency":  False,
            "hierarchicalMuTolerance":        0.20,
            "accelDecayDisagreeThresh":       adddt,
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

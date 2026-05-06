"""
VisCache_LadderSPONZA_SCALE.py — direct SPP-scaling of ct + vt vs Wilson.

User question (2026-05-06): does Wilson actually outperform direct
SPP-scaling of the existing ct + vt knobs? If a single user-set
(vt_base, ct_base) plus an SPP-scaling exponent (k_vt, k_ct) reproduces
the per-SPP optima from SPONZA_CT/SPONZA_VT, Wilson's mathematical
formulation needs to JUSTIFY ITSELF against the simpler engineering.

Calibration from prior sweeps:
- SPONZA_CT: x4 knee = ct=8, x16 monotonic-best = ct=64. Ratio 8× over
  4× SPP. log(8)/log(4) = 1.5. → k_ct = 1.5.
- SPONZA_VT: x4 = vt=0.10, x16 = vt=0.001. Ratio 100× over 4× SPP.
  log(0.01)/log(0.25) = 3.32. → k_vt = 3.32.

Sweep at Sponza x{4, 16}, fixed cell4×4 + bayer2×2 + pm=0.02, with
ct base = 8 and vt base = 0.10 (calibrated at refSpp=4):

  ref_x4    : ct=8  vt=0.10  k_ct=0  k_vt=0  (no scaling, x4 baseline)
  ref_x16   : ct=8  vt=0.001 k_ct=0  k_vt=0  (no scaling, x16 carry)
  scale_vt32: ct=8  vt=0.10  k_ct=0  k_vt=3.2  (vt scaling only)
  scale_vt33: ct=8  vt=0.10  k_ct=0  k_vt=3.32 (vt scaling, calibrated)
  scale_ct15: ct=8  vt=0.10  k_ct=1.5  k_vt=0  (ct scaling only)
  scale_both: ct=8  vt=0.10  k_ct=1.5  k_vt=3.32 (both scalings)
  wilson_e40: ct=8  vt=*  wz=3.8416 eps=0.40   (Wilson's best from prior sweep)

Per-SPP target (from SPONZA_VT):
  x4  optimum (art5): art5≈17.5 (vt=0.10), art5≈18.0 (vt=0.001)
  x16 optimum (art5): art5≈15.2 (vt=0.001 OR Wilson eps=0.40)

Pass criterion for direct scaling: scale_both should match or beat
ref_x16 at x16 (art5 ≤ 15.5) AND match ref_x4 at x4 (art5 ≤ 17.7) —
ONE config covers both regimes. If it does, Wilson is **NOT NEEDED**;
if it doesn't, Wilson's narrower x16 leverage justifies its complexity.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_SCALE -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_SCALE"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; PM = 0.02

# (label, ct_base, vt_base, k_ct, k_vt, wz, eps)
SCALE_VARIANTS = [
    ("ref_x4base",    8, 0.100, 0.00, 0.00, 0.0,    0.01),
    ("ref_x16carry",  8, 0.001, 0.00, 0.00, 0.0,    0.01),
    ("scale_vt32",    8, 0.100, 0.00, 3.20, 0.0,    0.01),
    ("scale_vt33",    8, 0.100, 0.00, 3.32, 0.0,    0.01),
    ("scale_ct15",    8, 0.100, 1.50, 0.00, 0.0,    0.01),
    ("scale_both",    8, 0.100, 1.50, 3.32, 0.0,    0.01),
    ("wilson_e40",    8, 0.100, 0.00, 0.00, 3.8416, 0.40),
]

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, ct, vt, kct, kvt, wz, eps) in SCALE_VARIANTS:
        cell_n = int(round(CELL_PX**0.5))
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{label}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   ct,
            "matureThreshold": max(64, ct * 4),
            "varThreshold":    vt,
            "ctSppScaleK":     kct,
            "vtSppScaleK":     kvt,
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

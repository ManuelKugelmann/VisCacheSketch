"""
VisCache_LadderSPONZA_STDERR.py — stderr gate sweep on Sponza x{4,16}.

Architecture clarification (2026-05-06): the project accumulates frames
with PathTracer SPP=1 each, NOT internal-SPP > 1. So `gSpp` in slang is
always 1 regardless of the harness's "x4"/"x16" tag. SPP-scaling on a
constant gSpp can't be SPP-adaptive.

The principled N-aware gate is **stderr**: trust if `√(var/N) ≤ τ`.
Per-cell N accumulates across frames, so stderr drops naturally as
cells mature. This is what should produce SPP-adaptive trust without
any explicit SPP knob.

Sweep at Sponza x{4, 16}, fixed canonical (qa012, cell4×4, bayer2×2,
ct=8, pm=0.02), comparing:
  - vt100 (vt=0.10, stderr off): SPONZA_VT x4 baseline
  - vt001 (vt=0.001, stderr off): SPONZA_VT x16 carry
  - se005 (stderr=0.05): trusts cells with N ≥ ~100
  - se010 (stderr=0.10): trusts cells with N ≥ ~25
  - se020 (stderr=0.20): trusts cells with N ≥ ~6 (loose)
  - se040 (stderr=0.40): trusts cells with N ≥ ~2 (very loose)
  - se080 (stderr=0.80): trusts almost always (degenerate)

Pass criterion: at one of {se005, se010}, results should match or beat
the per-SPP vt optima at BOTH x4 and x16 simultaneously — that's the
principled N-aware solution to the SPP-dependent vt finding.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_STDERR -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "SPONZA_STDERR"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02

# (label, vt, se)
STDERR_VARIANTS = [
    ("vt100_seoff", 0.100, 0.00),  # SPONZA_VT x4 baseline
    ("vt001_seoff", 0.001, 0.00),  # SPONZA_VT x16 carry
    ("se005",       0.001, 0.05),  # stderr ≤ 0.05 (tight, N ≥ ~100)
    ("se010",       0.001, 0.10),  # stderr ≤ 0.10 (canonical, N ≥ ~25)
    ("se020",       0.001, 0.20),  # stderr ≤ 0.20 (loose, N ≥ ~6)
    ("se040",       0.001, 0.40),  # stderr ≤ 0.40 (very loose, N ≥ ~2)
    ("se080",       0.001, 0.80),  # stderr ≤ 0.80 (degenerate, almost always)
]

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, vt, se) in STDERR_VARIANTS:
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
            "ctSppScaleK":     0.0,
            "vtSppScaleK":     0.0,
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

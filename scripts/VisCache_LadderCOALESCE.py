"""
VisCache_LadderCOALESCE.py — A/B test warp-coalesced cache lookup.

Improvement J from LADDER_PLAN. Adds SM 6.5 WaveMatch coalescing to
vhfLookup: lanes targeting the same (addr, fp) cell share one
vhfFindSlot probe + table read via WaveReadLaneAt. Fingerprint
mismatch falls back to per-lane lookup so correctness is preserved.

Sweep at Sponza canonical (cell4×4 bayer2×2 ct=8 stderr=0.10):
  - off:  enableWarpCoalescedLookup=0 (legacy per-lane)
  - on:   enableWarpCoalescedLookup=1 (coalesced)

Pass criteria:
  1. CORRECTNESS — error metrics (mean_err_pct, art5, RMSE, PSNR)
     match within stochastic noise (≤ 0.1pp on err%, ≤ 1% relative on
     RMSE/PSNR). Confirms WaveMatch coalescing returns the same data
     to all lanes.
  2. PERFORMANCE — gpu_tracepass_ms drops with coalescing on. The
     ~15-20 ms/frame hash-lookup overhead surfaced by TIMING should
     shrink to whatever fraction comes from leader-only probes (1/N
     where N is the average lane-coalescing group size).

Both criteria are needed: a 50% wall-clock drop with art5 +5pp would
indicate broken coalescing (lanes reading other lanes' wrong cell).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s COALESCE -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "COALESCE"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02; SE = 0.10

DEFAULT_SCENES = ["Sponza"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (label, enableWarpCoalescedLookup)
COALESCE_VARIANTS = [
    ("off", False),
    ("on",  True),
]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for (label, ec) in COALESCE_VARIANTS:
        cell_n = int(round(CELL_PX**0.5))
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        ct_tag = f"ct{CT:03d}"
        se_tag = f"se{int(round(SE*1000)):03d}"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{se_tag}_coalesce_{label}_{pm_tag}"
        VARIANTS.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":   CT,
            "matureThreshold": max(64, CT * 4),
            "varThreshold":    0.001,
            "stderrThreshold": SE,
            "wilsonZSquared":  0.0,
            "muShrinkZSquared": 0.0,
            "enableWarpCoalescedLookup": ec,
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

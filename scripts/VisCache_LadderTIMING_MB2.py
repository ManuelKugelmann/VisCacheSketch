"""
VisCache_LadderTIMING_MB2.py — multibounce wall-clock via the SAME harness as TIMING.

The original TIMING_MB used `_run_baseline_variant` for the cache path,
which produced ~250 ms/frame numbers that don't reflect per-frame cost
(the harness adds extra render-graph passes per renderFrame). This
script uses `run_variants` for cache + `run_baseline` for vanilla —
the exact same harness as the corrected single-bounce TIMING.

Sponza × b ∈ {0, 4} at x4 with run_variants + maxBounces:
  - vanilla_b0_x4 / vanilla_b4_x4 via run_baseline → TIMING_VAN_MB/
  - cache canonical b={0, 4} via run_variants → TIMING_MB2/

Pass criterion: cache b=4 wall-clock save % > b=0 wall-clock save %
(67% rays saved at b=4 vs 27% at b=0 — multibounce should give bigger
wall-clock wins).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s TIMING_MB2 -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "TIMING_MB2"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02; SE = 0.10

DEFAULT_SCENES = ["Sponza"]

# Build cache variant (same as TIMING canonical)
BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    cell_n = int(round(CELL_PX**0.5))
    pm_tag = f"pm{int(round(PM*1000)):03d}"
    ct_tag = f"ct{CT:03d}"
    se_tag = f"se{int(round(SE*1000)):03d}"
    tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{se_tag}_{pm_tag}"
    VARIANTS.append((f"{base_name}__{tag}", {
        **base_overrides,
        "bootThreshold":   CT,
        "matureThreshold": max(64, CT * 4),
        "varThreshold":    0.001,
        "stderrThreshold": SE,
        "wilsonZSquared":  0.0,
        "muShrinkZSquared": 0.0,
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
MF_CONFIGS = [(0, 0, 4, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    # Vanilla per-bounce baselines via run_baseline (same harness as TIMING_VAN/).
    for mb in (0, 4):
        run_baseline(step_name="TIMING_VAN_MB", frame_configs=[(0, 0, 1)],
                      scene_file=scene_file, resX=res, resY=res,
                      maxBounces=mb, gt_spp=4096, extra_spp=[4],
                      variant_tag=f"vanilla_b{mb}",
                      mogwai_globals=globals())
    # Cache variants per bounce — run_variants + maxBounces.
    for mb in (0, 4):
        run_variants(step_name=f"{STEP}_b{mb}", frame_configs=MF_CONFIGS,
                      scene_file=scene_file, variants=VARIANTS,
                      maxBounces=mb,
                      resX=res, resY=res, mogwai_globals=globals(),
                      step_overrides=STEP_OVERRIDES)

_HEADLESS_SCRIPT_DONE = True

"""
VisCache_LadderTIMING.py — vanilla vs cache wall-clock comparison.

Measures gpu_tracepass_ms on Sponza x{4, 16} with the canonical cache
(stderr=0.10) vs vanilla (no cache). Converts the algorithmic
rays_traced_pct cost-proxy into actual GPU ms.

Both paths use the same profiler hook (run_baseline + run_variants
both populate gpu_tracepass_ms). The first variant per scene-load
shows warmup confound; we intentionally render vanilla FIRST as the
warmup absorber, then the cache config gets a clean reading.

Pass criterion: cache gpu_tracepass_ms is meaningfully lower than
vanilla at the same scene + SPP, in proportion to rays_traced_pct
(73% rays traced → ~75–85% of vanilla's ms, accounting for cache
hash-lookup overhead per ray).

Output: SPONZA_TIMING captures dir + stats.csv with both paths.
Compare ms via:
    runtime/pythondist/python.exe -c "
import csv
for r in csv.DictReader(open('runtime/captures/ladder/TIMING/stats.csv')):
    print(r['scene'], r['variant'], r['spp'], 'rays', r['rays_traced_pct'],
          'gpu', r.get('gpu_tracepass_ms', '-'))
    "

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s TIMING -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "TIMING"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; PM = 0.02; SE = 0.10

DEFAULT_SCENES = ["Sponza"]

# Single canonical cache variant — stderr=0.10
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
MF_CONFIGS = [(0, 0, 4, 1), (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    # Vanilla baseline FIRST (absorbs cold-start GPU warmup so the cache
    # variant gets a clean reading). Vanilla path now also emits
    # gpu_tracepass_ms via the run_baseline profiler hook.
    run_baseline(step_name="00", frame_configs=[(0, 0, 1)],
                  scene_file=scene_file, resX=res, resY=res,
                  extra_spp=[4, 16], mogwai_globals=globals())
    # Cache variant — gets the warm GPU.
    run_variants(step_name=STEP, frame_configs=MF_CONFIGS,
                  scene_file=scene_file, variants=VARIANTS,
                  resX=res, resY=res, mogwai_globals=globals(),
                  step_overrides=STEP_OVERRIDES)

_HEADLESS_SCRIPT_DONE = True

"""
VisCache_LadderBISTRO_DECAY.py — periodic-decay sweep on Bistro.

BISTRO_ADD showed accelDecayDisagreeThresh creates runaway oscillation
on Bistro. Test the ALTERNATIVE de-trust mechanism: unconditional periodic
decay (existing decayPeriod knob). decayPeriod=N means 1/N of the table
is touched per frame, each touched entry loses 1/8 of both counters
(mean-preserving, N-shrinking).

For x16 SPP (16-frame render): decayPeriod=300 means ~5% chance per cell
of any decay during the render — effectively no decay. Need much smaller
decayPeriod to see effect during the render window.

Sweep: cell4×4 + bayer2×2 + ct=8 + vt=0.10 + pm=0.02 + decayPeriod ∈
{0 (off), 2, 4, 8, 16, 64, 300 (default)}. BistroInt at x{4, 16}.

Hypothesis: decay's effect depends on whether Bayer phase rotation
during the decay window gives meaningful sample diversity. If the
geometry lock is fundamental (no Bayer slot ever sees the visible
side), decay won't help. If it's temporary lock-in, fast decay
should break the saturation.

7 variants × 1 scene × 2 SPPs = 14 captures. ~8-10 min Mogwai.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s BISTRO_DECAY \\
        -c BistroInterior
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_variants, run_baseline, get_scenes, finalize_step,
    make_norm_variants,
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP,
)

STEP = "BISTRO_DECAY"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

BAYER_N = 2; CELL_PX = 16; CT = 8; VT = 0.10; PM = 0.02
DECAY_VALUES = [0, 2, 4, 8, 16, 64, 300]

DEFAULT_SCENES = ["BistroInterior"]

BASE_TUPLES = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                              quant_tag=QUANT_TAG)
               if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS = []
for (base_name, base_overrides) in BASE_TUPLES:
    for dp in DECAY_VALUES:
        cell_n = int(round(CELL_PX**0.5))
        ct_tag = f"ct{CT:03d}"
        vt_tag = f"vt{int(round(VT*1000)):03d}"
        pm_tag = f"pm{int(round(PM*1000)):03d}"
        dp_tag = f"dp{dp:03d}" if dp > 0 else "dpoff"
        tag = f"bayer{BAYER_N}x{BAYER_N}_cell{cell_n}x{cell_n}_{ct_tag}_{vt_tag}_{pm_tag}_{dp_tag}"
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
            "accelDecayDisagreeThresh":       0.0,    # toxic per BISTRO_ADD
            "pMin":                           PM,
            "bayerN":                         BAYER_N,
            "enableVisCacheDecay":            (dp > 0),
            "decayPeriod":                    max(1, dp),
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

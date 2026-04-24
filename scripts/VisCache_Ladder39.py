"""
VisCache_Ladder39.py — Step 39: enable decay pass for Sponza x16 bias.

Sponza x16 plateau at 124% blob under dir_dist is the unsolved problem.
Hypothesis: biased cell μ accumulates over many samples and new disagreeing
evidence drowns. The existing (disabled) `VisCacheDecay.cs.slang` pass
halves counters of 1/decayPeriod of the table per frame — effectively
forgetting 1/8 of history on each visit, which unmatures cells and lets
new evidence dominate.

Four decay configs at dir_dist + fd16+hcOn+tol020+sub4:
  a_off     — decay disabled (step-36 baseline)
  b_dp300   — decayPeriod=300 (gentle, default C++ value)
  c_dp60    — decayPeriod=60  (moderate)
  d_dp15    — decayPeriod=15  (aggressive — fast-action setting)

4 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "39"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

VARIANTS = [
    ("a_off",  False, 0),
    ("b_dp300", True, 300),
    ("c_dp60",  True, 60),
    ("d_dp15",  True, 15),
]

VARIANTS_39 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    for (suffix, decayOn, dp) in VARIANTS:
        VARIANTS_39.append((f"{base_name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "enableVisCacheDecay":           decayOn,
            "decayPeriod":                   dp,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(ALL_SCENES)):
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4, 16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=MF_CONFIGS,
        scene_file=scene_file,
        variants=VARIANTS_39,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="36", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Periodic decay pass sweep. Target Sponza x16 blob "
                        "plateau by periodically halving cell counters — "
                        "forgets 1/8 of history each sweep, unmatures "
                        "cells for revalidation. Designed for animated "
                        "scenes but might help static-scene bias by "
                        "preventing biased-mu lock-in.")
_HEADLESS_SCRIPT_DONE = True

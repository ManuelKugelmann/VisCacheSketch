"""
VisCache_Ladder40.py — Step 40: combine decay + distB=0.24 for x4 stack.

Step 37 d_d15_s24 (distB=0.24) cuts Sponza x4 blob 191 -> 110 (-42%).
Step 39 b_dp300 (decay on, period 300) cuts Sponza x4 blob 156 -> 110 (-29%).

Both land at ~110 — but do they stack further? Or is 110 a hard floor for
dir_dist Sponza x4? Four combinations:

  a_baseline               — default distB=0.48, decay off
  b_distB024               — distB=0.24, decay off (step-37 winner)
  c_dp300                  — distB=0.48, decay dp300 (step-39 winner)
  d_distB024_dp300         — stacked

4 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "40"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

# (suffix, distB, decayOn, decayPeriod)
VARIANTS = [
    ("a_baseline",        0.48, False, 0),
    ("b_distB024",        0.24, False, 0),
    ("c_dp300",           0.48, True, 300),
    ("d_distB024_dp300",  0.24, True, 300),
]

VARIANTS_40 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    for (suffix, distB, decayOn, dp) in VARIANTS:
        VARIANTS_40.append((f"{base_name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "distBCoarse":                   distB,
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
        variants=VARIANTS_40,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="39", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Stack distB=0.24 and decayPeriod=300 — both hit "
                        "~110 blob at Sponza x4 alone. Combine to check "
                        "if the mechanisms complement (different origin: "
                        "addressing vs retention) for a lower floor.")
_HEADLESS_SCRIPT_DONE = True

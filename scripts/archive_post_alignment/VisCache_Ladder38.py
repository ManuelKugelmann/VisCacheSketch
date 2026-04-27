"""
VisCache_Ladder38.py — Step 38: subframeN sweep on dir_dist addressing.

Step 22 found sub4 (4x4 Bayer) best for pos addressing. dir_dist addressing
(step 36) restructures the cache around view cones — might interact with
Bayer slot coverage differently. Test whether sub8 or sub16 recovers
Sponza x16 blob (~124% under dir_dist default).

Four subframeN values at dir_dist + fd16+hcOn+tol020 + d15_s48:
  a_sub2   — 2×2 Bayer (4 slots)
  b_sub4   — 4×4 Bayer (16 slots, step-36 default)
  c_sub8   — 8×8 Bayer (64 slots)
  d_sub16  — 16×16 Bayer (256 slots, matches x16 SPP)

4 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "38"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

VARIANTS = [
    ("a_sub2",   2),
    ("b_sub4",   4),
    ("c_sub8",   8),
    ("d_sub16", 16),
]

VARIANTS_38 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    for (suffix, sub) in VARIANTS:
        VARIANTS_38.append((f"{base_name}__ct4_fd16_hcOn_tol020_pm005_{suffix}", {
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
            "pMin":                          PM_INH,
            "subframeN":                     sub,
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
        variants=VARIANTS_38,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="36", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="subframeN sweep on dir_dist addressing. sub16 "
                        "matches x16 SPP so each slot contributes exactly "
                        "one frame; potentially cleaner bias recovery at "
                        "high SPP if slot-diversity aligns with cache-"
                        "convergence rate.")
_HEADLESS_SCRIPT_DONE = True

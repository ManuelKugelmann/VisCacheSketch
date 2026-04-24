"""
VisCache_Ladder37.py — Step 37: tune dirB / distB for dir_dist addressing.

Step 36 finding: dir_dist addressing cuts Sponza x1 blob −49% and x16
blob −35% at the cost of ~50% more rays. The default dirB=15° / distB=
0.48 came from the original pos-addressing sweep; dir_dist has different
structural constraints and may benefit from its own tuning.

Sweep dirB × distB at dir_dist + fd16+hcOn+tol020:

  a_d15_s48   — default (step-36 baseline)
  b_d08_s48   — finer angular (8° bins)
  c_d30_s48   — coarser angular (30° bins)
  d_d15_s24   — finer distance (0.24 cells)
  e_d15_s96   — coarser distance (0.96 cells)

5 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "37"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = dict(QUANT_SWEEP[_qa_tag])

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

# (suffix, dirBCoarse, distBCoarse)
VARIANTS = [
    ("a_d15_s48", 15.0, 0.48),
    ("b_d08_s48",  8.0, 0.48),
    ("c_d30_s48", 30.0, 0.48),
    ("d_d15_s24", 15.0, 0.24),
    ("e_d15_s96", 15.0, 0.96),
]

VARIANTS_37 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    for (suffix, dirB, distB) in VARIANTS:
        VARIANTS_37.append((f"{base_name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "dirBCoarse":                    dirB,
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
        variants=VARIANTS_37,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="36", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Tune dirB/distB for dir_dist addressing. Step 36 "
                        "kept the pos-addressing quant defaults; dir_dist "
                        "might benefit from its own angular/radial "
                        "resolution. Finer bins = more cells, potentially "
                        "better discrimination but more contention.")
_HEADLESS_SCRIPT_DONE = True

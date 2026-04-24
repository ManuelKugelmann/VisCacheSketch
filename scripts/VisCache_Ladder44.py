"""
VisCache_Ladder44.py — Step 44: dirB coarseness vs 1AL regression (triple).

Step 43 established dir_dist as the robust Sponza win (blob -54 to -81,
>>1σ). But single-run step 36 showed dir_dist regresses 1AL blob +35%
(19 → 26). Step 37 single-runs hinted dirB=30° might help.

Triple-trial 3 dirB values on 1AL and Sponza to check:
  a_d15  — dirB=15° (session default)
  b_d30  — dirB=30° (coarser, more samples per cell)
  c_d60  — dirB=60° (very coarse, fewer cells)

3 variants × 3 trials × 3 spp × 2 scenes = 54 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "44"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

VARIANT_CELLS = [
    ("a_d15", 15.0),
    ("b_d30", 30.0),
    ("c_d60", 60.0),
]

VARIANTS_44 = []
for trial in (1, 2, 3):
    for (base_name, base_overrides) in BASE_DIR_DIST:
        for (suffix, dirB) in VARIANT_CELLS:
            VARIANTS_44.append((f"{base_name}__{suffix}__t{trial}", {
                **base_overrides,
                **NO_JITTER,
                "dirBCoarse":                    dirB,
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
        variants=VARIANTS_44,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="43", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="dirB coarseness × triple-trial on 1AL+Sponza. "
                        "Find cell size that keeps Sponza win without "
                        "regressing 1AL.")
_HEADLESS_SCRIPT_DONE = True

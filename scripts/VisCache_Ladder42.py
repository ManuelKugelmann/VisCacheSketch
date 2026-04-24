"""
VisCache_Ladder42.py — Step 42: triple-trial Sponza variance measurement.

Across steps 31-41 I repeatedly ran nominally identical configs on Sponza
and got wildly different blob numbers (e.g. step-33 a_se000 x4=129,
step-34 a_ad000 x4=203, step-41 x4=181 — all the same config). Single-
run data is untrustworthy below the ~70% blob floor that appears to
match GPU-atomic noise.

Three identical variants on Sponza to quantify the noise floor:

  trial_1, trial_2, trial_3 — all dir_dist + fd16+hcOn+tol020+sub4
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "42"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

VARIANTS_42 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    for trial in (1, 2, 3):
        VARIANTS_42.append((f"{base_name}__trial{trial}", {
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
        variants=VARIANTS_42,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="36", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Triple trial of same config to measure the GPU-"
                        "atomic-race-induced run-to-run variance. All "
                        "three variants identical; only the trial index "
                        "differs. Blob spread across trials = measurement "
                        "noise floor.")
_HEADLESS_SCRIPT_DONE = True

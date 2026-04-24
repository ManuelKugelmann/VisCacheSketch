"""
VisCache_Ladder43.py — Step 43: triple-trial ABCD comparison on Sponza.

Step 42 showed Sponza blob noise floor is ~90 units across identical
trials. So any single-run comparison is noise-limited. This step runs
three trials of each of four variants so we can compute means and
confidence intervals:

  A_pos_off    — pos addressing, no HC, no decay (step-31 a_fd0_hcOff)
  B_pos_hc     — pos addressing, HC peek on (step-31 e_fd0_hcOn)
  C_dirdist    — dir_dist, HC peek on, no decay (step-36 c_dir_dist)
  D_full       — dir_dist, HC peek on, decay dp15 (step-39 d_dp15)

4 variants × 3 trials × 3 spp × 1 scene = 36 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "43"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS      = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

def common(hcOn, decayOn, decayPeriod):
    return {
        **NO_JITTER,
        "bootThreshold":                 4,
        "matureThreshold":               128,
        "varThreshold":                  0.01,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       16,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": hcOn,
        "hierarchicalMuTolerance":       0.20,
        "accelDecayDisagreeThresh":      0.0,
        "enableVisCacheDecay":           decayOn,
        "decayPeriod":                   decayPeriod,
        "pMin":                          PM_INH,
        "subframeN":                     4,
    }

VARIANTS_43 = []
for trial in (1, 2, 3):
    # A: pos addressing, no HC, no decay
    for (base_name, base_overrides) in BASE_POS:
        VARIANTS_43.append((f"{base_name}__A_pos_off__t{trial}", {
            **base_overrides, **common(False, False, 0),
        }))
    # B: pos addressing, HC peek
    for (base_name, base_overrides) in BASE_POS:
        VARIANTS_43.append((f"{base_name}__B_pos_hc__t{trial}", {
            **base_overrides, **common(True, False, 0),
        }))
    # C: dir_dist addressing, HC peek
    for (base_name, base_overrides) in BASE_DIR_DIST:
        VARIANTS_43.append((f"{base_name}__C_dirdist__t{trial}", {
            **base_overrides, **common(True, False, 0),
        }))
    # D: dir_dist + HC peek + decay
    for (base_name, base_overrides) in BASE_DIR_DIST:
        VARIANTS_43.append((f"{base_name}__D_full__t{trial}", {
            **base_overrides, **common(True, True, 15),
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
        variants=VARIANTS_43,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="42", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Triple-trial ABCD comparison to separate signal "
                        "from the ~90-unit Sponza noise floor documented "
                        "in step 42.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder41.py — Step 41: universal-best config documentation run.

Pin the session's best-found universal configuration and run it across
all scenes for a clean reference. The config combines the four real
wins from steps 31-39:

  * N=32000 cascade with stride=(N-1)/32 (step 31)
  * Analytical entry level, fd=16 (step 31)
  * Hierarchical consistency peek at levelStride, tol=0.20 (step 31+32)
  * dir_dist addressing (step 36)
  * Periodic decay pass with dp=15 (step 39)

Variant: a single `best` variant. 1 × 3 spp × 5 scenes = 15 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "41"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{_qa_tag}"]

VARIANTS_41 = []
for (base_name, base_overrides) in BASE_DIR_DIST:
    VARIANTS_41.append((f"{base_name}__best_universal", {
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
        "enableVisCacheDecay":           True,
        "decayPeriod":                   15,
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
        variants=VARIANTS_41,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="39", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Session-best universal: dir_dist + fd16 + hcOn + "
                        "tol020 + dp15 + sub4. Combines all four committed "
                        "wins (31, 36, 39) into one variant for documentation.")
_HEADLESS_SCRIPT_DONE = True

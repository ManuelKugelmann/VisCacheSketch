"""
VisCache_Ladder22.py — Step 22: finer pMin granularity around pm010.

Step 20 locked pm010 as a big win (1PL x1 blob 71→39). This step
probes the local optimum: is pm010 the sweet spot or do pm008/pm012
recover more?

Three variants: pm008, pm010 (baseline), pm012. All at step-20 carry
(ct16+vt005+fp0+fd0 with w=1 and w=2). 3 × 6 × 7 = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 22
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "22"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("20")
if INHERITED_NAME is None:
    raise RuntimeError("[22] step 20 picks.json missing — run step 20 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[22] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_22 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

PM_SWEEP = {"pm008": 0.08, "pm010": 0.10, "pm012": 0.12}

VARIANTS_22 = []
for (name, base_overrides) in BASE_22:
    for pm_tag, pm_val in PM_SWEEP.items():
        tag = f"ct16_vt005_fp0_fd0_{pm_tag}"
        VARIANTS_22.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          pm_val,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        frame_configs=[(1, 0, 1, 1),  (1, 0, 1, 4),  (1, 0, 1, 16),
                       (2, 0, 1, 1),  (2, 0, 1, 4),  (2, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_22,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="20", ref_variant=INHERITED_NAME,
              ref_label="step-20 carry (pm010)")
write_picks_meta(STEP, inherited_from="20", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Finer pMin granularity around pm010. Tests whether "
                        "pm008/pm012 recover more than pm010. Carry set "
                        "post-inspection if a clear local optimum emerges.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder11.py — Step 11: pMin sweep at step-10 multi-level carry (multi-frame).

First step of the post-archive, multi-frame-regime ladder. Re-validates
the pre-archive finding that pMin=0.10 is a significant quality win
over the original pMin=0.05 — this time under the correct sample
scheduling (frames=N, spp=1).

Inherits step-10's multi-level carry (qa012, ct4 or whatever step 10
picks after its multi-frame re-run).

Three variants: pm005 (baseline), pm010 (pre-archive winner), pm020
(aggressive corrective tracing). 3 × (x1 + x4 + x16) × (w=1 + w=2)
× 7 scenes = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 11
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "11"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("10")
if INHERITED_NAME is None:
    raise RuntimeError("[11] step 10 picks.json missing — run step 10 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[11] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_11 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

PM_SWEEP = {"pm005": 0.05, "pm010": 0.10, "pm020": 0.20}

VARIANTS_11 = []
for (name, base_overrides) in BASE_11:
    for pm_tag, pm_val in PM_SWEEP.items():
        tag = f"ct{CT_INH}_vt005_fp0_fd0_{pm_tag}"
        VARIANTS_11.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
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

# Multi-frame configs — spp=1, frames=N for dispersion.
MF_CONFIGS = [(1, 0, 1, 1),  (1, 0, 4, 1),  (1, 0, 16, 1),
              (2, 0, 1, 1),  (2, 0, 4, 1),  (2, 0, 16, 1)]

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
        variants=VARIANTS_11,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="10", ref_variant=INHERITED_NAME,
              ref_label="step-10 carry (pm005)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Re-validation of pm010 under multi-frame regime "
                        "(post-archive ladder). Picker uses per-scene "
                        "outlier gate; no variant wins if it regresses "
                        "any scene catastrophically. Carry set post-"
                        "inspection if pm010 survives.")
_HEADLESS_SCRIPT_DONE = True

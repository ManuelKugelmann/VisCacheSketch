"""
VisCache_Ladder18.py — Step 18: stderr gate stacked with step-12 ct16+w2 carry.

Narrow, targeted: combines step-12's ct16+w2 multi-level carry (best
Cornell 1PL blob defender) with step-07's stderr-gate principle
(best single-level blob lever). Never tested together — step 15 used
ct=4, step 12 had no stderr.

Two variants:
  se0 = 0.0    — step-12 baseline with stderr gate OFF (legacy)
  se0 = 0.05   — step-12 carry + stderr gate active

Frame configs match step 12 (x1/x4/x16, w=1/w=2).
Run on all 7 scenes to see if the combination is universal or
scene-conditional.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 18
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "18"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[18] step 12 picks.json missing — run step 12 first.")

# Extract step-12 carry quant.
_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[18] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

# Inherit step-12 params from its tag: ct=16, vt=0.05, fp=0, fd=0.
# The carry name also implies warmup=2 (set via frame_configs).
INHERITED = parse_variant_tags(INHERITED_NAME)

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_18 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

SE_SWEEP = {"se0": 0.0, "se05": 0.05}

VARIANTS_18 = []
for (name, base_overrides) in BASE_18:
    for se_tag, se_val in SE_SWEEP.items():
        tag = f"ct16_vt005_fp0_fd0_{se_tag}"
        VARIANTS_18.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               se_val,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
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

    # Match step-12 frame_configs: x1/x4/x16 × w=1/w=2.
    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1),  (1, 0, 1, 4),  (1, 0, 1, 16),
                       (2, 0, 1, 1),  (2, 0, 1, 4),  (2, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_18,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (no stderr)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Targeted 2-variant test: does stderr gate (se=0.05) "
                        "stack with step-12's ct16+w=2 carry? Never tested "
                        "together — step 15 used ct=4, step 12 had no stderr. "
                        "Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True

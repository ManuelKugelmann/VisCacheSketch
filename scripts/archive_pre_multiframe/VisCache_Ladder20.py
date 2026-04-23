"""
VisCache_Ladder20.py — Step 20: pMin floor sweep on step-12 carry.

Five gate-sweep steps in a row (16/17/18/19) came back negative. The
step-12 carry (ct16 + vt0.05 + w=2) is stable, but 1PL x4 blob is
still ~86. One lever has been pinned since step 05 and never swept
at the current carry: pMin.

pMin = RR floor. Raising it forces more tracing at "confident" cells
(low var, high N) that the adaptive-pMin formula would otherwise
deem trust-worthy. Hypothesis: confident-but-biased cells (mostly-
shadow cells at penumbra edges where μ≈0.02 but the pixel is
actually in light) would benefit from a higher floor — the bias
is exactly the regime adaptive-pMin reduces tracing in.

Three variants at step-12 carry + pMin:
  pm005  — 0.05 (current baseline — re-measure in same run)
  pm010  — 0.10 (modestly more defensive)
  pm020  — 0.20 (1-in-5 forced trace even on confident cells)

Frame configs match step 12 (x1/x4/x16, w=1/w=2). 3 × 6 × 7 = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 20
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "20"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[20] step 12 picks.json missing — run step 12 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[20] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_20 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

PM_SWEEP = {"pm005": 0.05, "pm010": 0.10, "pm020": 0.20}

VARIANTS_20 = []
for (name, base_overrides) in BASE_20:
    for pm_tag, pm_val in PM_SWEEP.items():
        tag = f"ct16_vt005_fp0_fd0_{pm_tag}"
        VARIANTS_20.append((f"{name}__{tag}", {
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
        variants=VARIANTS_20,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

CARRY_20 = f"{WINNER_NAME}__ct16_vt005_fp0_fd0_pm010"
finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              carried_winners=[CARRY_20],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (pm005)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={"pos": [CARRY_20]}, rule=_DEFAULT_PICKER_RULE,
                  notes="Manual carry: pm010 (pMin=0.10). 1PL x1 blob "
                        "71→39 at w=1 (45% relative gain), 39→31 at w=2. "
                        "Sponza x4 err +3.88 → +2.18 (43% relative). "
                        "Small 1PL x16 blob regression 60→87 (acceptable). "
                        "Rays cost negligible. pm020 rejected: catastrophic "
                        "1AL x1 w2 (8.87→109.54) and 1AL x16 w2 (30.84→117) "
                        "regressions outweigh the extra 1PL gain.")
_HEADLESS_SCRIPT_DONE = True

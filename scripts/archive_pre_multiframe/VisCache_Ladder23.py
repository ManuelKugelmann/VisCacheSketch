"""
VisCache_Ladder23.py — Step 23: vt × pm010 sweep.

vt (varThreshold) has been pinned at 0.05 since step 6. It was chosen
under the old pMin=0.05 floor. Now that pm010 provides rate-defense,
looser vt (trust more cells as converged) may save rays without
quality cost — the pMin floor keeps corrective tracing regardless.

Three variants: vt003 / vt005 (baseline) / vt008 with pm=0.10 fixed.
3 × 6 × 7 = 126 runs.

Hypothesis: vt=0.08 saves rays on variance-dominated scenes (Bistro,
32PL, 3AL) with minimal quality cost, because pm010 catches the
occasional wrong trust. vt=0.03 (tighter) may help bias-dominated
Sponza by demanding tighter convergence.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 23
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "23"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("20")
if INHERITED_NAME is None:
    raise RuntimeError("[23] step 20 picks.json missing — run step 20 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[23] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_23 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VT_SWEEP = {"vt003": 0.03, "vt005": 0.05, "vt008": 0.08}

VARIANTS_23 = []
for (name, base_overrides) in BASE_23:
    for vt_tag, vt_val in VT_SWEEP.items():
        tag = f"ct16_{vt_tag}_fp0_fd0_pm010"
        VARIANTS_23.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  vt_val,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          0.10,
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
        variants=VARIANTS_23,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

CARRY_23 = f"{WINNER_NAME}__ct16_vt003_fp0_fd0_pm010"
finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              carried_winners=[CARRY_23],
              ref_step="20", ref_variant=INHERITED_NAME,
              ref_label="step-20 carry (vt005)")
write_picks_meta(STEP, inherited_from="20", inherited=[INHERITED_NAME],
                  carried={"pos": [CARRY_23]}, rule=_DEFAULT_PICKER_RULE,
                  notes="Manual carry: vt003 (vt=0.03). Sponza x4 err "
                        "breakthrough: +0.17% to +0.65% vs +2.85-3.56% at "
                        "vt005 (parity with vanilla). BistroInterior err "
                        "-18.60 vs -18.23. Rays cost +1.7pp average. Modest "
                        "1PL blob regression (53→60) and 1AL blob swing "
                        "(26→50) accepted — Sponza x4 improvement is "
                        "largest signal-per-delta in the ladder.")
_HEADLESS_SCRIPT_DONE = True

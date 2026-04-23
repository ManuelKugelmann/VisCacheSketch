"""
VisCache_Ladder21.py — Step 21: ct efficiency test under pm010.

Step 20 confirmed pMin=0.10 is a rate-defense that fixes 1PL/1AL
bias (blob 71→39 at 1PL x1 w1). Step 12 previously raised ct from 4
to 16 as a quality defense — paying +23pp rays on 32PL x4 (17.5→40.5).

Question: if pMin now defends bias directly, can we lower ct back
toward step-11 and recover the rays savings without losing quality?

Two variants: step-20 carry `ct16_pm010` vs `ct4_pm010`. Everything
else (vt, w, fp, fd) matches the step-20 carry. 2 × 6 × 7 = 84 runs.

If ct4+pm010 matches ct16+pm010's quality but saves rays on 32PL/1PL,
the new carry is (ct4, pm010) — step-12's high-ct trade-off was
compensating for what pMin now does more cheaply.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 21
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "21"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("20")
if INHERITED_NAME is None:
    raise RuntimeError("[21] step 20 picks.json missing — run step 20 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[21] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_21 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

CT_SWEEP = {"ct4": 4, "ct16": 16}

VARIANTS_21 = []
for (name, base_overrides) in BASE_21:
    for ct_tag, ct_val in CT_SWEEP.items():
        tag = f"{ct_tag}_vt005_fp0_fd0_pm010"
        VARIANTS_21.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct_val,
            "matureThreshold":               128,
            "varThreshold":                  0.05,
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
        variants=VARIANTS_21,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="20", ref_variant=INHERITED_NAME,
              ref_label="step-20 carry (ct16_pm010)")
write_picks_meta(STEP, inherited_from="20", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Efficiency probe at pm010: can ct drop from 16 to "
                        "4 now that pMin defends bias directly? Step 12 "
                        "raised ct to 16 to defend 1PL quality (at the cost "
                        "of +23pp rays on 32PL). If pm010 does that job "
                        "cheaper, ct4+pm010 is the new carry.")
_HEADLESS_SCRIPT_DONE = True

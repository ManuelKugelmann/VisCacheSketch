"""
VisCache_Ladder24.py — Step 24: ct × vt003 × pm010 re-test.

Step 21 showed ct4+pm010 unlocks HUGE rays savings (32PL x4 halved,
Bistro -20pp) but costs Sponza x4 quality (err +2.34 → +6.99, 3×
worse). Step 23 showed vt003+pm010 ESSENTIALLY FIXES Sponza x4
(err +2.85 → +0.17 at ct=16). Question: does vt003 rescue Sponza
at ct=4 too?

If yes: ct4+vt003+pm010 delivers Sponza parity AND Bistro rays savings
AND 32PL rays savings — a universal win.

Three variants: ct4_vt003_pm010, ct8_vt003_pm010, ct16_vt003_pm010.
3 × 6 × 7 = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 24
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "24"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("23")
if INHERITED_NAME is None:
    raise RuntimeError("[24] step 23 picks.json missing — run step 23 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[24] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_24 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

CT_SWEEP = {"ct4": 4, "ct8": 8, "ct16": 16}

VARIANTS_24 = []
for (name, base_overrides) in BASE_24:
    for ct_tag, ct_val in CT_SWEEP.items():
        tag = f"{ct_tag}_vt003_fp0_fd0_pm010"
        VARIANTS_24.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct_val,
            "matureThreshold":               128,
            "varThreshold":                  0.03,
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
        variants=VARIANTS_24,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="23", ref_variant=INHERITED_NAME,
              ref_label="step-23 carry (ct16)")
write_picks_meta(STEP, inherited_from="23", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="ct × vt003 × pm010 cross-sweep. Step 21 showed ct4 "
                        "saves 20-37pp rays but Sponza x4 err regressed +2.3 "
                        "→ +7.0. Step 23 showed vt003 gives Sponza x4 "
                        "parity (+0.17%). Does vt003 rescue Sponza at ct=4 "
                        "so we can unlock the rays savings? Carry set "
                        "post-inspection if ct4+vt003 delivers both.")
_HEADLESS_SCRIPT_DONE = True

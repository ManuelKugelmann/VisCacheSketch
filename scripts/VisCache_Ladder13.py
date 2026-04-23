"""
VisCache_Ladder13.py — Step 13: ct sweep at pm+vt carry (multi-frame).

Pre-archive step 21 showed ct=4 delivers massive rays savings but
regresses bias-dominated scenes (Sponza). Pre-archive step 24 showed
ct × vt are orthogonal bias defenses. This step re-measures the
landscape under multi-frame at the post-archive pm+vt carry.

Four variants: ct2, ct4, ct8, ct16 (baseline). 4 × 6 × 7 = 168 runs.

Expected: ct16 wins for Sponza/1PL (bias), ct4 wins Bistro/32PL (rays).
The per-scene outlier picker will either pick a universal compromise
or mark it as inconclusive (no variant passes every scene's gate).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 13
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "13"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[13] step 12 picks.json missing — run step 12 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[13] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.03))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.10))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_13 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

CT_SWEEP = {"ct2": 2, "ct4": 4, "ct8": 8, "ct16": 16}

def _vt_tag(v):
    return "vt0" if v <= 0.005 else f"vt{int(round(v * 100)):03d}"

def _pm_tag(v):
    return f"pm{int(round(v * 100)):03d}"

VARIANTS_13 = []
for (name, base_overrides) in BASE_13:
    for ct_tag, ct_val in CT_SWEEP.items():
        tag = f"{ct_tag}_{_vt_tag(VT_INH)}_fp0_fd0_{_pm_tag(PM_INH)}"
        VARIANTS_13.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct_val,
            "matureThreshold":               128,
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        variants=VARIANTS_13,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="ct sweep at pm+vt carry under multi-frame. "
                        "Tests whether the single-frame-era scene regime "
                        "split (Bistro wants low ct, Sponza wants high) "
                        "holds under multi-frame. Carry set post-"
                        "inspection.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder24.py — Step 24: jitter revisit under multi-frame + sub4.

Archive step 9 tested jitter (jitterFilter, jitterCell) at single-level
single-frame sub2 and found no benefit — NO_JITTER has been carried
ever since. Under multi-frame × sub4 × multi-level, the cache behavior
is fundamentally different; jitter might help soft boundary cases.

Four variants at step-22 sub4 carry:
  nojitter   — baseline (current carry)
  jf05       — per-position filter jitter 0.5
  jc05       — per-cell jitter 0.5 [Binder 2018]
  jf05_jc05  — both stacked

4 × 6 × 7 = 168 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 24
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "24"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[24] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[24] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

BASE_24 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# Each: (suffix, jf, jc)
JITTER_VARIANTS = [
    ("nojitter",  0.0, 0.0),
    ("jf05",      0.5, 0.0),
    ("jc05",      0.0, 0.5),
    ("jf05_jc05", 0.5, 0.5),
]

VARIANTS_24 = []
for (name, base_overrides) in BASE_24:
    for (suffix, jf, jc) in JITTER_VARIANTS:
        VARIANTS_24.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_sub4_{suffix}", {
            **base_overrides,
            "jitterFilter":                  jf,
            "jitterCell":                    jc,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
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
        variants=VARIANTS_24,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (no jitter)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Jitter revisit under multi-frame + sub4. Archive "
                        "step 9 found jitter unhelpful at single-level "
                        "single-frame; test whether the multi-frame + sub4 "
                        "regime unlocks jitter as a soft-boundary defense.")
_HEADLESS_SCRIPT_DONE = True

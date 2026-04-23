"""
VisCache_Ladder26.py — Step 26: tableCapacity sweep at sub4 carry.

tableCapacity has been pinned at 1<<25 (32M entries × 8 bytes = 256MB)
since the multi-level switch at step 10. Test whether smaller (memory
savings) or larger (fewer hash collisions) capacities matter.

Three variants:
  tc24 — 16M entries (128MB) — half memory
  tc25 — 32M entries (256MB) — current baseline
  tc26 — 64M entries (512MB) — double memory

3 × 12 configs × 7 scenes = 252 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 26
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "26"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[26] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[26] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_26 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

TC_VARIANTS = [
    ("tc24", 1 << 24),
    ("tc25", 1 << 25),
    ("tc26", 1 << 26),
]

VARIANTS_26 = []
for (name, base_overrides) in BASE_26:
    for (suffix, tc) in TC_VARIANTS:
        VARIANTS_26.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
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
            "tableCapacity":                 tc,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI}  # tableCapacity per-variant

# Use w=0 as step-25 finding suggested
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
        variants=VARIANTS_26,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (tc25)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="tableCapacity sweep at sub4 carry. tc24=128MB, "
                        "tc25=256MB (baseline), tc26=512MB. Tests whether "
                        "smaller table costs quality (collisions) or larger "
                        "table helps. Also first step using w=0 default per "
                        "step-25 finding.")
_HEADLESS_SCRIPT_DONE = True

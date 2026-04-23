"""
VisCache_Ladder12.py — Step 12: vt sweep at pm010 carry (multi-frame).

Pre-archive step 23 found vt=0.03 was a big Sponza win at pm010
under the single-frame regime. Step 25 pushed vt=0.01 for further
Sponza gain but was never validated under multi-frame. This step
re-measures the vt landscape under multi-frame at the post-archive
pm010 carry.

Four variants: vt001, vt003, vt005 (baseline), vt010. 4 × 6 × 7 = 168 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 12
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "12"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("11")
if INHERITED_NAME is None:
    raise RuntimeError("[12] step 11 picks.json missing — run step 11 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[12] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.10))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_12 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

VT_SWEEP = {"vt001": 0.01, "vt003": 0.03, "vt005": 0.05, "vt010": 0.10}

def _pm_tag(v):
    return f"pm{int(round(v * 100)):03d}"

VARIANTS_12 = []
for (name, base_overrides) in BASE_12:
    for vt_tag, vt_val in VT_SWEEP.items():
        tag = f"ct{CT_INH}_{vt_tag}_fp0_fd0_{_pm_tag(PM_INH)}"
        VARIANTS_12.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  vt_val,
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
        variants=VARIANTS_12,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="11", ref_variant=INHERITED_NAME,
              ref_label="step-11 carry (vt005)")
write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="varThreshold sweep at pm010 under multi-frame. "
                        "Pre-archive vt003 was a Sponza win under single-"
                        "frame; step 27 showed Sponza regression under "
                        "multi-frame. This step finds the correct vt for "
                        "multi-frame Sponza. Carry set post-inspection.")
_HEADLESS_SCRIPT_DONE = True

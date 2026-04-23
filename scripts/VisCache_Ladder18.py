"""
VisCache_Ladder18.py — Step 18: subframeN (Bayer grid size) sweep under multi-frame.

All prior ladder steps used SUBFRAME_2x2 (4 Bayer slots). Multi-frame
now uses Bayer-slot rotation across frames for temporal dispersion.
With 4 slots and x16 sampling = 16 frames, slots cycle 4× across the
run. With 4x4 (16 slots), each slot gets exactly 1 frame. This could
either (a) improve cell coverage diversity or (b) slow cache maturation
because each slot contributes less.

Test three subframe sizes at step-12 carry (ct4, vt001, pm005):
  sub1 — 1×1 (no Bayer gating, full-frame sampling, no rotation)
  sub2 — 2×2 (current baseline)
  sub4 — 4×4 (fine Bayer grid, full slot sweep per x16)

3 × 6 × 7 = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 18
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, \
    SUBFRAME_1x1, SUBFRAME_2x2, SUBFRAME_4x4

STEP = "18"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[18] step 12 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[18] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_18 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# SubframeN variants — note: the step_overrides SUBFRAME_2x2 applies globally,
# but here we override per-variant to probe each N.
SUB_VARIANTS = [
    ("sub1", 1),
    ("sub2", 2),
    ("sub4", 4),
]

VARIANTS_18 = []
for (name, base_overrides) in BASE_18:
    for (suffix, N) in SUB_VARIANTS:
        VARIANTS_18.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_{suffix}", {
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
            "subframeN":                     N,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI}  # no SUBFRAME_2x2 default; per-variant

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
        variants=VARIANTS_18,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (subN=2)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="SubframeN sweep under multi-frame. 1×1=no Bayer, "
                        "2×2=baseline, 4×4=fine Bayer grid. With multi-frame "
                        "slot rotation, 4×4 provides maximum spatial "
                        "diversity but each slot contributes less to each "
                        "cell. Tests whether finer Bayer improves the bias-"
                        "dominated Sponza regime via better spatial coverage.")
_HEADLESS_SCRIPT_DONE = True

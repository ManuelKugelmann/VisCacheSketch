"""
VisCache_Ladder22.py — Step 22: push subframeN further (sub4 vs sub8 vs sub16).

Step 18 discovery: sub4 dramatically fixes Sponza (err +18.7% → -3.6%).
Mechanism: finer Bayer grid × multi-frame rotation = more spatial
diversity per cell. If N=4 helps this much, does N=8 or N=16 go further?

Limitation: with multi-frame x16 and subframeN=16, each slot contributes
exactly 1 frame per x16 run. Cells get 1 sample per slot → 16 distinct
samples per cell, max spatial diversity. But each cell receives only
1 sample per frame from any single pixel → may not accumulate enough
per cell.

Three variants at step-18 carry (ct4, vt001, pm005):
  sub4  — baseline (current carry)
  sub8  — 8×8 Bayer (64 slots, 4× more diversity than sub4)
  sub16 — 16×16 Bayer (256 slots, maximum for multi-frame x16)

3 × 6 × 7 = 126 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 22
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "22"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[22] step 18 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[22] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_22 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

SUB_VARIANTS = [("sub4", 4), ("sub8", 8), ("sub16", 16)]

VARIANTS_22 = []
for (name, base_overrides) in BASE_22:
    for (suffix, N) in SUB_VARIANTS:
        VARIANTS_22.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_{suffix}", {
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

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI}

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
        variants=VARIANTS_22,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="18", ref_variant=INHERITED_NAME,
              ref_label="step-18 carry (sub4)")
write_picks_meta(STEP, inherited_from="18", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Push subframeN further: 4/8/16. Step 18 showed "
                        "sub4 is a Sponza breakthrough. Does finer Bayer "
                        "grid (more slot diversity) extend the gain, or "
                        "does cell under-population at higher N bite back?")
_HEADLESS_SCRIPT_DONE = True

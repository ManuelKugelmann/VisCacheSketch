"""
VisCache_Ladder20.py — Step 20: matureThreshold sweep under multi-frame.

matureThreshold controls when cells stop accepting writes (cell's
sample total frozen). Pinned at 128 since step 00 — never probed.
Under multi-frame, cells accumulate over many frames; a low mature
threshold might freeze cells too early, while a high one wastes
memory on over-stuffed cells.

Four variants at step-12 carry (ct4, vt001, pm005):
  m32   — aggressive freeze (cell locked at 32 samples)
  m64   — moderate freeze
  m128  — baseline (current default)
  m512  — keeps accumulating for much longer

4 × 6 × 7 = 168 runs.

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
    raise RuntimeError("[20] step 12 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[20] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_20 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

MATURE_SWEEP = [("m32", 32), ("m64", 64), ("m128", 128), ("m512", 512)]

VARIANTS_20 = []
for (name, base_overrides) in BASE_20:
    for (suffix, m) in MATURE_SWEEP:
        VARIANTS_20.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               m,
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
        variants=VARIANTS_20,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (m128)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="matureThreshold sweep. Controls when cell writes "
                        "stop (cell freezes at N samples). Lower values "
                        "freeze cells earlier preserving fast initial "
                        "estimate; higher values keep accumulating. Untested "
                        "axis — pinned at 128 since step 00.")
_HEADLESS_SCRIPT_DONE = True

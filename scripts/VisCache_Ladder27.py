"""
VisCache_Ladder27.py — Step 27: focused forceDescendFootprintPx (fd) sweep.

Direct attack on user observation that Sponza has large cells that
don't get refined. forceDescendFootprintPx (fd) is the hard lever:
when cellPx > fd, vhfLookup refuses to early-stop on "converged"
and ALWAYS descends to finer levels. Different from fp (which makes
big cells require more samples before trust); fd just bypasses the
convergence early-stop.

Five variants at sub4 carry:
  fd0       — baseline (no force-descend)
  fd256     — descent at cellPx > 256 (16×16px) — aggressive
  fd1024    — descent at cellPx > 1024 (32×32px) — paper-ish
  fd4096    — descent at cellPx > 4096 (64×64px) — only big cells
  fd16384   — descent at cellPx > 16384 (128×128px) — only very big cells

5 × 3 spp × 7 scenes = 105 runs. Uses w=0.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 27
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "27"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[27] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[27] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_27 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, fd_px²)
# User direction: descend until cell footprint is 2x2 or 4x4 px.
# 2x2 = 4 px²    → descend if cellPx > 4   (very aggressive)
# 4x4 = 16 px²   → descend if cellPx > 16  (aggressive)
# 8x8 = 64 px²   → descend if cellPx > 64  (moderate)
# 16x16 = 256 px² → descend if cellPx > 256 (light)
FD_VARIANTS = [
    ("fd0",     0),    # off (baseline)
    ("fd4",     4),    # descend until ≤2x2 px
    ("fd16",   16),    # descend until ≤4x4 px
    ("fd64",   64),    # descend until ≤8x8 px
    ("fd256", 256),    # descend until ≤16x16 px
]

VARIANTS_27 = []
for (name, base_overrides) in BASE_27:
    for (suffix, fd) in FD_VARIANTS:
        VARIANTS_27.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_pm{int(round(PM_INH*100)):03d}_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

# w=0 per step-25 finding
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
        variants=VARIANTS_27,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (fd=0)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Focused forceDescendFootprintPx sweep at sub4 carry. "
                        "Direct attack on Sponza large-cell bias: descend "
                        "until cell footprint reaches 2x2 (fd4), 4x4 (fd16), "
                        "8x8 (fd64), 16x16 (fd256) pixel size. Cascade always "
                        "descends past converged big cells until pixel-sized "
                        "regime where cache is most accurate.")
_HEADLESS_SCRIPT_DONE = True

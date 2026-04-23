"""
VisCache_Ladder23.py — Step 23: stack sub4 + dir_dist (two orthogonal Sponza wins).

Two independent Sponza breakthroughs discovered:
- Step 18: sub4 (4×4 Bayer × multi-frame) → Sponza err +18.70% → -3.63%
- Step 19: dir_dist addressing → Sponza err +18.60% → -1.77%

They attack the bias problem via different mechanisms:
- sub4: spatial slot rotation provides cells with samples from diverse
  positions, averaging across the boundary
- dir_dist: splits cells by direction-to-light, so shadow/light samples
  don't mix in the same cell

If mechanisms are independent, stacking should either:
(a) improve further (both defenses compound)
(b) saturate (either alone suffices)
(c) hurt (over-dispersion — each sub-cell now has too few samples)

Four variants at step-13 carry (ct4, vt001, pm005):
  sub4_pos        — step 18 winner
  sub2_dirdist    — step 19 winner
  sub4_dirdist    — the stack
  sub2_pos        — baseline (current multi-frame step-12 carry)

4 × 6 × 7 = 168 runs. dirdist increases hash pressure; tableCapacity
doubled for the dir_dist variants.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 23
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "23"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("13")
if INHERITED_NAME is None:
    raise RuntimeError("[23] step 13 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[23] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

def _common(**extra):
    return {
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
        **QUANT_WINNER,
        **extra,
    }

tag = f"ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}"

VARIANTS_23 = [
    (f"pos_norm__pos__{_qa_tag}__{tag}_sub2_pos", _common(
        enableVisCacheDirDistAddr=False,
        enableVisCacheNormalAddr=True,
        subframeN=2,
    )),
    (f"pos_norm__pos__{_qa_tag}__{tag}_sub4_pos", _common(
        enableVisCacheDirDistAddr=False,
        enableVisCacheNormalAddr=True,
        subframeN=4,
    )),
    (f"pos_norm__dir_dist__{_qa_tag}__{tag}_sub2_dirdist", _common(
        enableVisCacheDirDistAddr=True,
        enableVisCacheNormalAddr=True,
        subframeN=2,
    )),
    (f"pos_norm__dir_dist__{_qa_tag}__{tag}_sub4_dirdist", _common(
        enableVisCacheDirDistAddr=True,
        enableVisCacheNormalAddr=True,
        subframeN=4,
    )),
]

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 26}  # 2× for dir_dist cell growth

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
        variants=VARIANTS_23,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="13", ref_variant=INHERITED_NAME,
              ref_label="step-13 carry (sub2, pos)")
write_picks_meta(STEP, inherited_from="13", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Stacks sub4 × dir_dist — two orthogonal Sponza "
                        "breakthroughs from steps 18 and 19. Tests whether "
                        "the mechanisms compound (spatial slot rotation + "
                        "directional cell split) or interfere (over-"
                        "dispersion with too few samples per sub-cell).")
_HEADLESS_SCRIPT_DONE = True

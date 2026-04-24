"""
VisCache_Ladder28.py — Step 28: refine the fp family around fp=2.0.

Step 26 surfaced a striking result: Sponza fp=2.0 at x4 gives err -12.89%
(cache beats vanilla by 12.9%) and blob 0.0 (ZERO visual artifact).
Cost: 96% rays — near vanilla. User flagged the plate as promising.

This step sweeps fp finer to find the quality/rays sweet spot and
tests combinations with ct / fd to reduce rays while preserving the
clean image.

Seven variants at sub4 carry:
  fp12      — fp=1.2 (lower rays, hopefully still clean)
  fp15      — fp=1.5
  fp18      — fp=1.8
  fp20      — fp=2.0 (step-26 Sponza winner, baseline)
  fp20_ct8  — fp=2.0 with ct=8 (more samples before trust; should
              lower rays since pre-trust cells fall through to direct)
  fp20_fd64 — fp=2.0 with forceDescend-to-8x8px; may trim rays by
              not trusting still-big cells even at fp20
  fp25      — fp=2.5 (more aggressive; curiosity)

7 × 3 spp × 7 scenes = 147 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "28"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[28] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[28] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_28 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, ct, fp factor, fd px²)
FP_VARIANTS = [
    ("fp12",       4, 1.2,    0),
    ("fp15",       4, 1.5,    0),
    ("fp18",       4, 1.8,    0),
    ("fp20",       4, 2.0,    0),  # step-26 Sponza winner
    ("fp20_ct8",   8, 2.0,    0),
    ("fp20_fd64",  4, 2.0,   64),
    ("fp25",       4, 2.5,    0),
]

VARIANTS_28 = []
for (name, base_overrides) in BASE_28:
    for (suffix, ct, fp, fd) in FP_VARIANTS:
        VARIANTS_28.append((f"{name}__ct{ct}_vt{int(round(VT_INH*100)):03d}_pm{int(round(PM_INH*100)):03d}_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct,
            "matureThreshold":               128,
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": fp,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

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
        variants=VARIANTS_28,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (fp=0)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Refine fp family. Step 26 Sponza fp20 x4: err "
                        "-12.89%, blob 0.0, rays 96% — user flagged as "
                        "promising but expensive. Sweep fp 1.2-2.5 and "
                        "combine with ct8/fd64 to see if clean-image "
                        "quality can be held at lower rays.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder25.py — Step 25: warmup sweep at sub4 carry under multi-frame.

warmupFirst (Bayer slots write-only in frame 0) has been pinned at 1
across all post-archive steps. Under multi-frame x16 = 16 frames with
slot rotation, frame 0 warmup affects only 1 of 16 frames — diminishing
relative impact. Test other warmup values:

  w0 — no warmup (frame 0 query immediately, all slots active)
  w1 — current baseline (1 slot write-only in frame 0)
  w2 — 2 slots write-only in frame 0 (more bootstrap before query)
  w4 — all 4 slots write-only in frame 0 (full warmup frame)

Note: frame_configs use warmupFirst dimension as the first config tuple
element. We pass each config as a separate variant rather than as
warmup variations of the same variant.

Implementation: 4 variants × 3 spp × 1 wf=0 (each variant sets its own
implicit wf via base config). Actually simpler: sweep wf via config tuple.
4 configs × 3 spp × 7 scenes = 84 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 25
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "25"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("22") or read_carried_winner("18")
if INHERITED_NAME is None:
    raise RuntimeError("[25] need step 22/18 picks.json")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[25] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_25 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# Single variant — sweep done via frame_configs warmup dimension
VARIANTS_25 = []
for (name, base_overrides) in BASE_25:
    VARIANTS_25.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_sub4", {
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
    }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

# Warmup sweep: w0/w1/w2/w4 × x1/x4/x16
# warmupFirst is the first element of frame_config tuple
MF_CONFIGS = [
    (0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1),
    (1, 0, 1, 1),  (1, 0, 4, 1),  (1, 0, 16, 1),
    (2, 0, 1, 1),  (2, 0, 4, 1),  (2, 0, 16, 1),
    (4, 0, 1, 1),  (4, 0, 4, 1),  (4, 0, 16, 1),
]

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
        variants=VARIANTS_25,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="22", ref_variant=INHERITED_NAME,
              ref_label="step-22 carry (w=1/2)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="warmupFirst sweep at sub4 carry. Tests whether "
                        "additional warmup frames (w2/w4) or no warmup (w0) "
                        "help under multi-frame slot rotation. Single "
                        "variant × 12 frame_configs × 7 scenes = 84 runs.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder21.py — Step 21: fireflyBudget sweep under multi-frame.

fireflyBudget controls when high-contribution paths force tracing
instead of trusting the cache (firefly defense). Pinned at 0.05
since step 00 — untested axis.

Formula (VisCache.slang:1051):
  contrib = contribLuminance * max(mu, 1-mu)
  pFloor = clamp(contrib / fireflyBudget, pMinEff, 1)

Lower budget = more aggressive firefly-force-trace (more rays,
less bias at bright paths). Higher = looser (more cache trust,
more potential for fireflies and bias at bright edges).

Under multi-frame, bias has emerged on Sponza; tighter firefly
budget might force extra corrective tracing at the bright-sun-lit
edges where Sponza bias concentrates.

Four variants at step-12 carry:
  fb001 — aggressive firefly defense (20× more trace-force than baseline)
  fb005 — baseline
  fb010 — relaxed
  fb020 — much more permissive

4 × 6 × 7 = 168 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 21
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "21"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("12")
if INHERITED_NAME is None:
    raise RuntimeError("[21] step 12 picks.json missing.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[21] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.01))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.05))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_21 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

FB_SWEEP = [("fb001", 0.01), ("fb005", 0.05), ("fb010", 0.10), ("fb020", 0.20)]

VARIANTS_21 = []
for (name, base_overrides) in BASE_21:
    for (suffix, fb) in FB_SWEEP:
        VARIANTS_21.append((f"{name}__ct{CT_INH}_vt{int(round(VT_INH*100)):03d}_fp0_fd0_pm{int(round(PM_INH*100)):03d}_{suffix}", {
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
            "fireflyBudget":                 fb,
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
        variants=VARIANTS_21,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="12", ref_variant=INHERITED_NAME,
              ref_label="step-12 carry (fb005)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="fireflyBudget sweep. Controls when high-contribution "
                        "paths force trace (firefly defense). Lower = more "
                        "aggressive defense. Tightening may help Sponza bias "
                        "at sun-lit edges; relaxing may reduce rays cost.")
_HEADLESS_SCRIPT_DONE = True

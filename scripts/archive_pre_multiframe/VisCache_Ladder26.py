"""
VisCache_Ladder26.py — Step 26: parent-preinit on vs off at step-23 carry.

Parent-preinit has been OFF throughout the ladder (PRESET_MINIMAL
inherits FEATURES_OFF which sets enableVisCacheParentPreinit=False).
Child cells currently start at total=0 and accumulate from scratch.

Paper §5 advocates preinit to accelerate cascade construction. The
current shader fires `seed = parent >> 3` unconditionally on every
fresh child claim. Risk: at penumbra-boundary cells, parent μ ≈ 0.5
propagates to a child that might actually be entirely 0 or 1.

Before gating preinit with an ambiguity cutoff (step 27+), first
validate the baseline: does enabling preinit at all help?

Two variants at step-23 carry:
  ppOff  — enableVisCacheParentPreinit=False (current carry baseline)
  ppOn   — enableVisCacheParentPreinit=True (unconditional paper §5)

2 × 6 × 7 = 84 runs.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 26
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "26"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("23")
if INHERITED_NAME is None:
    raise RuntimeError("[26] step 23 picks.json missing — run step 23 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[26] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_26 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

PP_SWEEP = {"ppOff": False, "ppOn": True}

VARIANTS_26 = []
for (name, base_overrides) in BASE_26:
    for pp_tag, pp_val in PP_SWEEP.items():
        tag = f"ct16_vt003_fp0_fd0_pm010_{pp_tag}"
        VARIANTS_26.append((f"{name}__{tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 16,
            "matureThreshold":               128,
            "varThreshold":                  0.03,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       0,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          0.10,
            "enableVisCacheParentPreinit":   pp_val,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

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
        frame_configs=[(1, 0, 1, 1),  (1, 0, 1, 4),  (1, 0, 1, 16),
                       (2, 0, 1, 1),  (2, 0, 1, 4),  (2, 0, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_26,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="23", ref_variant=INHERITED_NAME,
              ref_label="step-23 carry (preinit off)")
write_picks_meta(STEP, inherited_from="23", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="parent-preinit baseline: on vs off at step-23 carry. "
                        "Preinit has been OFF throughout the ladder; this "
                        "step tests whether enabling paper §5 behavior "
                        "(unconditional preinit seed = parent>>3) helps or "
                        "hurts. If preinit helps, step 27 will gate it on "
                        "parent ambiguity.")
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_Ladder14.py — Step 14: parent-preinit + ambiguity gate (new shader param).

Parent-preinit seeds a freshly-claimed child cell with parent's μ
weighted by parent_total/8 (paper §5). This accelerates cascade
construction but risks propagating BIASED parent μ into the child
if the parent is at a visibility boundary (μ ≈ 0.5).

This step introduces the `preinitAmbiguityCutoff` shader parameter
(new): when parent μ ∈ [cutoff, 1-cutoff], SKIP preinit for this
child. Keeps preinit's speedup for confident parents (μ near 0 or 1),
blocks bias-propagation from ambiguous parents.

Three variants at step-13 carry:
  ppOff    — preinit off entirely (current default)
  ppOn     — preinit on, unconditional (paper §5 literal)
  pp_pa30  — preinit on, ambiguity cutoff 0.30 (new gated version)

3 × 6 × 7 = 126 runs.

Requires: VisCache rebuild after shader/C++ edits (gPreinitAmbiguityCutoff
param added to VisCache.slang / VisCache.h / VisCache.cpp).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 14
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, parse_variant_tags, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "14"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = read_carried_winner("13")
if INHERITED_NAME is None:
    raise RuntimeError("[14] step 13 picks.json missing — run step 13 first.")

_qa_tag = None
for tok in INHERITED_NAME.split("__"):
    if tok.startswith("qa") and tok[2:].isdigit():
        _qa_tag = tok
        break
if _qa_tag is None:
    raise RuntimeError(f"[14] cannot parse qa tag from {INHERITED_NAME}")
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

INHERITED_TAGS = parse_variant_tags(INHERITED_NAME)
CT_INH = int(INHERITED_TAGS.get("bootThreshold", 4))
VT_INH = float(INHERITED_TAGS.get("varThreshold", 0.03))
PM_INH = float(INHERITED_TAGS.get("pMin", 0.10))

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE_14 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

def _vt_tag(v):
    return "vt0" if v <= 0.005 else f"vt{int(round(v * 100)):03d}"

def _pm_tag(v):
    return f"pm{int(round(v * 100)):03d}"

PREINIT_VARIANTS = [
    ("ppOff",    {"enableVisCacheParentPreinit": False, "preinitAmbiguityCutoff": 0.0}),
    ("ppOn",     {"enableVisCacheParentPreinit": True,  "preinitAmbiguityCutoff": 0.0}),
    ("pp_pa30",  {"enableVisCacheParentPreinit": True,  "preinitAmbiguityCutoff": 0.30}),
]

VARIANTS_14 = []
for (name, base_overrides) in BASE_14:
    for (pp_tag, pp_overrides) in PREINIT_VARIANTS:
        tag = f"ct{CT_INH}_{_vt_tag(VT_INH)}_fp0_fd0_{_pm_tag(PM_INH)}_{pp_tag}"
        VARIANTS_14.append((f"{name}__{tag}", {
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
            **pp_overrides,
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
        variants=VARIANTS_14,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="13", ref_variant=INHERITED_NAME,
              ref_label="step-13 carry (preinit off)")
write_picks_meta(STEP, inherited_from="13", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Parent-preinit + ambiguity gate test. Preinit has "
                        "been OFF throughout the ladder; paper §5 expects "
                        "it ON. Hypothesis: unconditional preinit "
                        "propagates biased parent μ at boundaries; the "
                        "new ambiguity gate (pa30 = skip preinit when "
                        "parent μ ∈ [0.3, 0.7]) preserves cascade speedup "
                        "without the bias cost.")
_HEADLESS_SCRIPT_DONE = True

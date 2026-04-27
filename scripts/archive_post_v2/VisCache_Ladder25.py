"""
VisCache_Ladder25.py — Step 25: bootstrapBreak × parentPreinit.

Inherits step-24 carry pos_norm__pos__qa006__bayer4x4_cell4x4_ct256_vt0030_pm020_hc005.

The BiI x16 blob=14.56 invariant floor (steps 19-24) is structural
fireflies for the most part — averaging-based caches inherently can't
reproduce singular high-luminance path samples. But two cell-init
mechanisms are wired in the shader and never actually tested under
the corrected cascade:

  - **enableVisCacheBootstrapBreak**: when a fresh cell is bootstrapping
    (count < bootThreshold) and an arriving sample disagrees significantly
    with the running mean, restart the bootstrap. Stops biased early
    samples from dominating the cell's μ — directly attacks the "first
    few rays were unlucky and now the cell is permanently biased" mode.

  - **enableVisCacheParentPreinit**: initialize a newly-created child cell
    from its parent's μ instead of zero. Faster maturation and less
    susceptibility to early-sample bias.

2×2 = 4 variants on bias scenes. Both flags are bit-packed into the
shader's `flags` field (memory: project_lookup_cascade marks both as
"still TODO" — empirically validate or rule out).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "25"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("24")
if INHERITED is None:
    raise RuntimeError("[25] step 24 picks.json missing carried winner.")

QUANT_TAG = "qa006"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 256
VT_INH = 0.03
PM_INH = 0.20

BASE_25 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (bb_tag, bb, pp_tag, pp)
INIT_CONFIGS = [
    ("bb0", False, "pp0", False),
    ("bb1", True,  "pp0", False),
    ("bb0", False, "pp1", True),
    ("bb1", True,  "pp1", True),
]

VARIANTS_25 = []
for (base_name, base_overrides) in BASE_25:
    for bb_tag, bb, pp_tag, pp in INIT_CONFIGS:
        VARIANTS_25.append((f"{base_name}__bayer4x4_cell4x4_ct256_vt0030_pm020_hc005_{bb_tag}_{pp_tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       0.05,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
            "enableVisCacheBootstrapBreak":  bb,
            "enableVisCacheParentPreinit":   pp,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(MULTI_LEVEL_SCENES)):
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

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="24", ref_variant=INHERITED,
              ref_label="step-24 carry (qa006/ct256/hc005)")
write_picks_meta(STEP, inherited_from="24", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="bootstrapBreak x parentPreinit at qa006/ct256/hc005. "
                        "These are wired in the shader but flagged TODO in "
                        "memory: bootstrapBreak prevents biased early "
                        "samples from dominating cell mu; parentPreinit "
                        "seeds new child cells from parent mu instead of "
                        "zero. 2x2=4 variants. Best case: structural fix "
                        "for BiI x16=14.56 floor.")
_HEADLESS_SCRIPT_DONE = True

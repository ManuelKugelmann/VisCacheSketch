"""
VisCache_Ladder28.py — Step 28: vt re-sweep at ct=64/pm=0.10 carry.

Step 17 swept vt {0.005, 0.01, 0.02, 0.03, 0.05} but predated the
merge-order fix that honors per-variant pMin. Effective pMin was 0.05
(RR_ADAPTIVE clobbered), and the data showed vt<0.02 catastrophic on
Sponza (cache_a3 ≈ 113 vs vanilla 35).

Hypothesis: with proper pm=0.10 (post-merge-fix), the pMin floor forces
10% of trusted-cell pixels to still trace and compensates for a lenient
vt gate. vt=0.005 might be artifact-clean AND save more rays.

User observation: "vt0005 seems also good" — possibly visually checked
post-fix and finds it OK.

Sweep vt ∈ {0.005, 0.01, 0.02, 0.03, 0.05} at ct=64/pm=0.10 carry.
5 variants on bias scenes (32PL+Bistro+Sponza); Cornell already covered
by step 17.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "28"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 64
PM_INH = 0.10

BASE_28 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VT_VALUES = [0.005, 0.01, 0.02, 0.03, 0.05]

VARIANTS_28 = []
for (base_name, base_overrides) in BASE_28:
    for vt in VT_VALUES:
        vt_tag = f"vt{int(round(vt*1000)):04d}"
        VARIANTS_28.append((f"{base_name}__bayer4x4_cell4x4_ct064_{vt_tag}_pm010", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  vt,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
            "enableDecayAutoTune":           False,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

INHERITED = "pos_norm__pos__qa012__bayer4x4_cell4x4_ct064_vt0030_pm010"

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
        variants=VARIANTS_28,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="18", ref_variant=INHERITED,
              ref_label="step-18 ct=64 lane")
write_picks_meta(STEP, inherited_from="18", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="vt re-sweep at ct=64/pm=0.10 (post-merge-fix). "
                        "Step 17 was pre-fix so pm was clobbered. With "
                        "proper pm=0.10 the floor catches wrong-trust "
                        "events; vt=0.005 may be artifact-clean and "
                        "cheaper than vt=0.03.")
_HEADLESS_SCRIPT_DONE = True

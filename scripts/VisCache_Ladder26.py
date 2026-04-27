"""
VisCache_Ladder26.py — Step 26: decayPeriod sweep at ct=16 carry.

Inherits step 18 ct=016 lane: pos_norm__pos__qa012__bayer4x4_cell4x4_ct016_vt0030_pm010.

Hypothesis: ct~spp linear scaling (ct=16 needed for x1, ct=256 for x16) is
a workaround for the lack of decay. Without decay, biased cells stay
biased forever and their wrong-trust events accumulate over multi-frame
renders. With decay, biased cells lose their counter and re-bootstrap
with fresh samples — the cache becomes SPP-invariant.

Sweep: decayPeriod ∈ {0 (disabled, baseline), 2, 4, 8} frames. Lower =
more aggressive decay. At decayPeriod=2 within a 16-frame accumulation,
cells decay 8 times during the render — biased cells get many chances
to re-converge.

If small decayPeriod cleans Sponza x4 / x16 at ct=16, the cache is
SPP-invariant and the ct=256 strict carry becomes obsolete.

4 variants on 32PL + Bistro + Sponza (the bias scenes where ct=16
showed artifacts). Cornell already clean at ct=16/vt=0.03/pm=0.10.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "26"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16
VT_INH = 0.03
PM_INH = 0.10

BASE_26 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# decayPeriod values: 0 = disabled (baseline), {2,4,8} = decay during multi-frame
DP_VALUES = [0, 2, 4, 8]

VARIANTS_26 = []
for (base_name, base_overrides) in BASE_26:
    for dp in DP_VALUES:
        dp_tag = f"dp{dp:03d}"
        VARIANTS_26.append((f"{base_name}__bayer4x4_cell4x4_ct016_vt0030_pm010_{dp_tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
            "decayPeriod":                   dp,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

INHERITED = read_carried_winner("18") or "pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm010"

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
        variants=VARIANTS_26,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="18", ref_variant=INHERITED,
              ref_label="step-18 ct=128 lane")
write_picks_meta(STEP, inherited_from="18", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="decayPeriod sweep at ct=16 carry. Tests if "
                        "decay between frames lets ct=16 work clean at "
                        "x4/x16 on bias scenes (where ct=16 currently "
                        "shows artifacts). Decay re-bootstraps biased "
                        "cells with fresh samples. dp {0, 2, 4, 8}.")
_HEADLESS_SCRIPT_DONE = True

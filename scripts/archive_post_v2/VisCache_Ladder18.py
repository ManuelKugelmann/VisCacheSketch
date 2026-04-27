"""
VisCache_Ladder18.py — Step 18: ct revisit on bias-dominated scenes.

Inherits step-17 carry vt=0.03 (= step-16 vt003_pm010).

Step 17 confirmed vt=0.03 as the trust-gate floor — below it Sponza/Bistro
break, but residual blob on dense-bounce scenes is huge (BistroInterior
130-156, Sponza 89+, BistroExterior 67 at x16). Trust-gate widening
cannot fix this. The bias floor needs a different mechanism.

Pre-archive step 52 found ct=128 brought Sponza x1 blob to 3.4 (vs 148
at session start), at 87% rays cost. That was under the broken cascade.
This step re-tests the ct axis under the corrected cascade with the
vt=0.03 carry — does higher ct still buy blob reduction on bias-dominated
scenes?

Sweep: ct {16, 64, 128, 256}.

4 variants. Skip 1PL/32PL pre-test (those are saturated/insensitive to ct
at vt=0.03 — confirmed by step 12). Run directly on Bistro+Sponza+32PL
(32PL kept as sanity).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "18"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("17")
if INHERITED is None:
    raise RuntimeError("[18] step 17 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
VT_INH = 0.03
PM_INH = 0.10

BASE_18 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

CT_VALUES = [16, 64, 128, 256]

VARIANTS_18 = []
for (base_name, base_overrides) in BASE_18:
    for ct in CT_VALUES:
        ct_tag = f"ct{ct:03d}"
        VARIANTS_18.append((f"{base_name}__bayer4x4_cell4x4_{ct_tag}_vt0030_pm010", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct,
            "matureThreshold":               max(128, ct),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

# Default scene set: 32PL + Bistro + Sponza (the bias-floor offenders).
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
        variants=VARIANTS_18,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="17", ref_variant=INHERITED,
              ref_label="step-17 carry (vt003 ct16)")
write_picks_meta(STEP, inherited_from="17", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="ct revisit on bias-dominated scenes (32PL+Bistro+"
                        "Sponza) at vt=0.03 carry. Step 12 picked ct=16 "
                        "but only on 1PL+32PL pre-test; bias floor on "
                        "Bistro/Sponza wasn't visible there. Pre-archive "
                        "ct=128 reached Sponza blob 3.4 — re-test in the "
                        "corrected-cascade regime.")
_HEADLESS_SCRIPT_DONE = True

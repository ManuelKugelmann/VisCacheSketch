"""
VisCache_Ladder24.py — Step 24: accelDecayDisagreeThresh sweep.

Inherits step-23 carry pos_norm__pos__qa006__bayer4x4_cell4x4_ct256_vt0030_pm020_hc005.

Steps 19-23 hit a structural floor on Bistro/Sponza x16:
  - BistroInterior x16 blob = 14.6 invariant across 6+ variants spanning
    pMin/fp/HC/qa/ct sweeps. Trust-axis defenses cannot fix it.
  - Sponza x16: 21.1 → 13.1 across the ladder, but ct=512 cost is ~95%
    rays (cache nearly disabled).

Hypothesis: at x16 (16 frames of accumulation), specific cells store
biased μ that never gets fixed. Trust gates can't decline an already-
trusted cell. Cell-size tweaks couldn't help BiI. The remaining
mechanism is **temporal decay**: actively forget cells that show
evidence of bias by half-decaying the counter when an insert sample
disagrees with the current μ.

Sweep: accelDecayDisagreeThresh ∈ {0.0 (off), 0.05, 0.10, 0.20}.

Lower = more aggressive (more cells get reset). 4 variants on bias
scenes. Optimum-in-middle bet: ad=0.10.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "24"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("23")
if INHERITED is None:
    raise RuntimeError("[24] step 23 picks.json missing carried winner.")

QUANT_TAG = "qa006"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 256
VT_INH = 0.03
PM_INH = 0.20

BASE_24 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

AD_VALUES = [0.0, 0.05, 0.10, 0.20]

VARIANTS_24 = []
for (base_name, base_overrides) in BASE_24:
    for ad in AD_VALUES:
        ad_tag = f"ad{int(round(ad*100)):03d}"  # ad000, ad005, ad010, ad020
        VARIANTS_24.append((f"{base_name}__bayer4x4_cell4x4_ct256_vt0030_pm020_hc005_{ad_tag}", {
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
            "accelDecayDisagreeThresh":      ad,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
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
        variants=VARIANTS_24,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="23", ref_variant=INHERITED,
              ref_label="step-23 carry (qa006/ct256)")
write_picks_meta(STEP, inherited_from="23", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="accelDecayDisagreeThresh sweep at qa006/ct256/hc005 "
                        "carry. Tests temporal decay as defense for x16 "
                        "biased-cell artifacts (BiI invariant 14.6, Sponza "
                        "13-21). Half-decays cells whose insert sample "
                        "disagrees with current μ by > thresh. Optimum-in-"
                        "middle bet: ad=0.10.")
_HEADLESS_SCRIPT_DONE = True

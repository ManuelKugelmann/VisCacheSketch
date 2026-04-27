"""
VisCache_Ladder27.py — Step 27: accelDecayDisagreeThresh re-sweep.

Inherits step 18 ct=016 lane: pos_norm__pos__qa012__bayer4x4_cell4x4_ct016_vt0030_pm010.

Step 24 found accelDecay no-op, but that data was rendered with the
merge-order bug — RR_ADAPTIVE clobbered per-variant pMin to 0.05, so
almost no rays reached trusted cells and accelDecay had nothing to
trigger on. Post-merge-fix (commit 8611ce5), pMin=0.10 is honored, so
~10% of trusted-cell pixels still trace and accelDecay has insert
samples to compare against stored μ.

Sweep: ad ∈ {0 (off, baseline), 0.05, 0.10, 0.20}. Lower threshold =
more aggressive (any minor disagreement triggers half-decay).

Same hypothesis as step 26 but a different mechanism: instead of
periodic full-table decay, accelDecay reacts to specific cells whose
samples disagree with stored μ (catches biased cells locally).

4 variants on 32PL + Bistro + Sponza.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "27"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16
VT_INH = 0.03
PM_INH = 0.10

BASE_27 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

AD_VALUES = [0.0, 0.05, 0.10, 0.20]

VARIANTS_27 = []
for (base_name, base_overrides) in BASE_27:
    for ad in AD_VALUES:
        ad_tag = f"ad{int(round(ad*100)):03d}"
        VARIANTS_27.append((f"{base_name}__bayer4x4_cell4x4_ct016_vt0030_pm010_{ad_tag}", {
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
            "accelDecayDisagreeThresh":      ad,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
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
        variants=VARIANTS_27,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="18", ref_variant=INHERITED,
              ref_label="step-18 ct=128 lane")
write_picks_meta(STEP, inherited_from="18", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="accelDecayDisagreeThresh re-sweep at ct=16 "
                        "carry. Step 24 found ad no-op but that pre-"
                        "dated the merge-order fix that honors pMin. "
                        "Post-fix, ~10% of trusted-cell pixels still "
                        "trace and accelDecay has insert samples to "
                        "compare against stored μ. ad {0, 0.05, 0.10, "
                        "0.20}.")
_HEADLESS_SCRIPT_DONE = True

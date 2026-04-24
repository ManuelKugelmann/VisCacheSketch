"""
VisCache_Ladder35.py — Step 35: stack stderr + accelDecay.

Step 33 stderr se003 cut Sponza x1 blob 160 -> 103 but regressed x4.
Step 34 accelDecay ad030 cut Sponza x16 blob 201 -> 148 but modest on x4.
Each helps a different SPP regime; try stacking to cover the full range.

4 combinations at fd16+hcOn+tol020:
  a_off           — no stderr, no accelDecay (baseline)
  b_se003         — stderr=0.03 only (step-33 best)
  c_ad030         — accelDecay=0.30 only (step-34 best-ish)
  d_se003_ad030   — both stacked

4 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "35"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = "pos_norm__pos__qa012__ct4_vt001_fp0_fd0_pm005_sub4"
_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

BASE_35 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, stderrThreshold, accelDecayDisagreeThresh)
VARIANTS = [
    ("a_off",          0.00, 0.00),
    ("b_se003",        0.03, 0.00),
    ("c_ad030",        0.00, 0.30),
    ("d_se003_ad030",  0.03, 0.30),
]

VARIANTS_35 = []
for (name, base_overrides) in BASE_35:
    for (suffix, se, ad) in VARIANTS:
        VARIANTS_35.append((f"{name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               se,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      ad,
            "pMin":                          PM_INH,
            "subframeN":                     4,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

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
        variants=VARIANTS_35,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="34", ref_variant=INHERITED_NAME,
              ref_label="step-34 carry")
write_picks_meta(STEP, inherited_from="34", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Stack stderr + accelDecay. Step 33 stderr helps "
                        "Sponza x1, step 34 accelDecay helps x16. Test "
                        "whether they complement (stderr suppresses "
                        "premature-convergence, accelDecay corrects stable-"
                        "but-biased cells — orthogonal mechanisms) or "
                        "conflict (both intervene on the same cells).")
_HEADLESS_SCRIPT_DONE = True

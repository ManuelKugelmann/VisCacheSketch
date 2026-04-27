"""
VisCache_Ladder34.py — Step 34: accelerated-decay on strong disagreement.

Sponza x16 stays at blob 150-200% regardless of HC peek or stderr gate.
Hypothesis: at high SPP the cache has many samples per cell, mu stabilises
at a biased value, and new disagreeing samples get drowned out. The fix
mechanism already exists: `gAccelDecayDisagreeThresh`. When a new sample
disagrees with current mu by more than the threshold, the cell's counters
get halved before the new delta is applied, so the disagreeing evidence
gets amplified weight.

Sweep `accelDecayDisagreeThresh` on the step-32 winner (fd16+hcOn+tol020):

  a_ad000   — accelDecay=0 (off, step-32 baseline)
  b_ad030   — 0.30  (only rebel if sample diff > 30%)
  c_ad050   — 0.50  (half-maximum disagreement triggers)
  d_ad080   — 0.80  (paranoid — only extreme outliers)

4 × 3 spp × scenes. Expect: higher accelDecay value = fewer decays = less
intervention. Lower value = more aggressive response to disagreement =
potentially faster blob resolution but more noise.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "34"
res = int(os.environ.get("RES", "512"))

INHERITED_NAME = "pos_norm__pos__qa012__ct4_vt001_fp0_fd0_pm005_sub4"
_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]
WINNER_NAME = f"pos_norm__pos__{_qa_tag}"

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

BASE_34 = [v for v in make_norm_variants(quant=QUANT_WINNER,
                                           base=PRESET_MINIMAL,
                                           quant_tag=_qa_tag)
           if v[0] == WINNER_NAME]

# (suffix, accelDecayDisagreeThresh)
VARIANTS = [
    ("a_ad000", 0.00),
    ("b_ad030", 0.30),
    ("c_ad050", 0.50),
    ("d_ad080", 0.80),
]

VARIANTS_34 = []
for (name, base_overrides) in BASE_34:
    for (suffix, ad) in VARIANTS:
        VARIANTS_34.append((f"{name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 4,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               0.0,
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
        variants=VARIANTS_34,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED_NAME],
              ref_step="32", ref_variant=INHERITED_NAME,
              ref_label="step-32 carry")
write_picks_meta(STEP, inherited_from="32", inherited=[INHERITED_NAME],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="accelDecayDisagreeThresh sweep. Target: fix x16 "
                        "blob (150-200% on Sponza) by accelerating bias "
                        "correction — new samples that disagree strongly "
                        "with cached mu halve counters before being "
                        "added, giving disagreeing evidence amplified "
                        "weight. Off baseline vs 0.30/0.50/0.80.")
_HEADLESS_SCRIPT_DONE = True

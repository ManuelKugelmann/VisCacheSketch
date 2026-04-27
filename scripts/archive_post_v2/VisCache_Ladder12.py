"""
VisCache_Ladder12.py — Step 12: ct × stderr trust requirement.

Inherits step-11 carry pos_norm__pos__qa012__ct4_bayer4x4_cell4x4 (matched
4×4 Bayer + 4×4 px cell, multi-level cascade). Sweeps two interrelated
trust gates:

  - bootThreshold (ct): minimum samples per cell before cache is consulted
    for trust. Higher = more evidence required, more rays traced before
    cache helps.
  - stderrThreshold (se): Bernoulli stderr gate sqrt(var/N) ≤ threshold.
    Combines variance and N into one principled gate (low var alone with
    few samples is rejected). 0 disables.

Hypothesis: ct=4 (step-10 carry) is too loose; cells trust on ~4 samples
even at penumbrae. ct≈16 + se≈0.02 should require real evidence before
gating. Optimum-in-middle bet: middle column/row of the 3×3 grid.

3 ct × 3 stderr = 9 variants. Pre-test on 1PL+32PL.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "12"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("11")
if INHERITED is None:
    raise RuntimeError("[12] step 11 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4   # bayer4x4 from step 11
FD = 16          # cell4x4 from step 11

BASE_12 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

CT_VALUES = [4, 16, 64]
SE_VALUES = [0.0, 0.02, 0.05]

VARIANTS_12 = []
for (base_name, base_overrides) in BASE_12:
    for ct in CT_VALUES:
        for se in SE_VALUES:
            se_tag = f"se{int(round(se*1000)):03d}"  # se000 / se020 / se050
            VARIANTS_12.append((f"{base_name}__bayer4x4_cell4x4_ct{ct}_{se_tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(128, ct),
                "varThreshold":                  0.10,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       FD,
                "stderrThreshold":               se,
                "enableHierarchicalConsistency": False,
                "hierarchicalMuTolerance":       0.20,
                "accelDecayDisagreeThresh":      0.0,
                "subframeN":                     SUBFRAME_N,
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
        variants=VARIANTS_12,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="11", ref_variant=INHERITED,
              ref_label="step-11 carry (bayer4x4_cell4x4)")
write_picks_meta(STEP, inherited_from="11", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="ct × stderr trust-requirement sweep at step-11 "
                        "carry. ct=4 (step-10 baseline) likely under-"
                        "samples penumbrae; expecting ct≈16 + se≈0.02 to "
                        "land in the middle. Higher ct trades rays for "
                        "blob; stderr makes few-sample low-variance cells "
                        "reject themselves.")
_HEADLESS_SCRIPT_DONE = True

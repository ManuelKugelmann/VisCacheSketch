"""
VisCache_Ladder13.py — Step 13: pMin × hierarchicalConsistency.

Inherits step-12 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct16_se000
(matched 4×4 Bayer + 4×4 px cell + ct=16 + stderr off). Sweeps two
interrelated quality knobs:

  - pMin: per-trace Russian-roulette floor. With adaptive pMin, this is
    the minimum probability that a ray is traced regardless of cache
    confidence. Higher = more rays, lower blob (forces some tracing
    even on confidently-cached cells).
  - hierarchicalConsistency: when a converged coarse cell is about to be
    trusted, peek the next finer level. If μ disagrees by more than
    `hierarchicalMuTolerance`, descend further (don't trust the coarse μ).

Both reduce blob at ray cost; tested together because they overlap in
"add safety net to the trust decision".

3 pMin × 3 HC variants = 9 variants. Pre-test on 1PL+32PL.
Optimum-in-middle bet: pMin=0.05 + HC tol=0.10.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "13"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("12")
if INHERITED is None:
    raise RuntimeError("[13] step 12 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16

BASE_13 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (pMin, hcEnabled, hcTol)
HC_CONFIGS = [
    ("hcOff",  False, 0.0),
    ("hc010",  True,  0.10),
    ("hc020",  True,  0.20),
]
PMIN_VALUES = [0.02, 0.05, 0.10]

VARIANTS_13 = []
for (base_name, base_overrides) in BASE_13:
    for pm in PMIN_VALUES:
        pm_tag = f"pm{int(round(pm*100)):03d}"
        for hc_tag, hc_on, hc_tol in HC_CONFIGS:
            VARIANTS_13.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH}_{pm_tag}_{hc_tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 CT_INH,
                "matureThreshold":               max(128, CT_INH),
                "varThreshold":                  0.10,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       FD,
                "stderrThreshold":               0.0,
                "enableHierarchicalConsistency": hc_on,
                "hierarchicalMuTolerance":       hc_tol if hc_on else 0.20,
                "accelDecayDisagreeThresh":      0.0,
                "pMin":                          pm,
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
        variants=VARIANTS_13,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="12", ref_variant=INHERITED,
              ref_label="step-12 carry (ct16)")
write_picks_meta(STEP, inherited_from="12", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="pMin × HC sweep at step-12 carry. Both add safety "
                        "to the trust gate. Optimum-in-middle bet: "
                        "pm005 + hc010.")
_HEADLESS_SCRIPT_DONE = True

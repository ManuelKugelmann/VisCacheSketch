"""
VisCache_Ladder19.py — Step 19: pMin re-sweep at ct=128 carry.

Inherits step-18 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm010.

Step 18 broke through on Bistro/Sponza at x1/x4 by raising ct from 16 to
128 — the cache produces vanilla-quality results when given enough sample
evidence per cell. But x16 remains artifact-territory on Bistro/Sponza
(blob 14–17 across ct {16, 64, 128, 256}): with 16 frames of accumulation,
many cells mature and the trust gate doesn't catch biased cells fast
enough. Higher ct alone can't fix this — we need a "rate defense" that
forces extra ray tracing even at trusted cells.

Step 13 found pMin to be no-op at vt=0.10. Now with ct=128 + vt=0.03,
the operating regime is different — mature cells dominate at x16, and
pMin's "trace at probability ≥ pMin" floor may finally bite.

Sweep: pMin ∈ {0.05, 0.10, 0.20, 0.30}.

4 variants. Run on bias scenes only (32PL+Bistro+Sponza) where x16 is
the open problem. Cornell variants are saturated/already-solved.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "19"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("18")
if INHERITED is None:
    raise RuntimeError("[19] step 18 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 128
VT_INH = 0.03

BASE_19 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

PMIN_VALUES = [0.05, 0.10, 0.20, 0.30]

VARIANTS_19 = []
for (base_name, base_overrides) in BASE_19:
    for pm in PMIN_VALUES:
        pm_tag = f"pm{int(round(pm*100)):03d}"
        VARIANTS_19.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH:03d}_vt0030_{pm_tag}", {
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
            "pMin":                          pm,
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
        variants=VARIANTS_19,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="18", ref_variant=INHERITED,
              ref_label="step-18 carry (ct128)")
write_picks_meta(STEP, inherited_from="18", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="pMin sweep at ct=128 carry to attack the x16 "
                        "bias-floor on Bistro/Sponza. Hypothesis: at higher "
                        "ct + tighter vt, pMin's RR-floor finally bites. "
                        "Optimum-in-middle bet: pMin=0.10 or 0.20.")
_HEADLESS_SCRIPT_DONE = True

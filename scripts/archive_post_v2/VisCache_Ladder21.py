"""
VisCache_Ladder21.py — Step 21: hierarchicalConsistency at ct=128/pm020 carry.

Inherits step-19 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm020.

The x16 bias-floor on Bistro/Sponza (blob 14-21) is structurally about
*biased cells getting trusted*. pMin (step 19) and footprintScale (step 20)
both add rays at adjacent pixels but cannot fix already-cached wrong μ.
HC takes a different approach: when a coarse cell is about to be trusted,
peek the next finer level. If finer-level μ disagrees by more than tol,
descend further (don't trust the coarse μ).

This is a structural defense — it catches biased trust before it
propagates, rather than mitigating downstream.

Sweep: hierarchicalMuTolerance ∈ {0.03, 0.05, 0.10, 0.20} with HC enabled.
Plus one HC-off baseline (= step 19 pm020 carry).

5 variants on 32PL+Bistro+Sponza. Optimum-in-middle bet: HC tol 0.05.
Step 13 found HC no-op at vt=0.10 — but that test was with the merge bug
(HC-on tol settings were the only HC-affecting parameters; step_overrides
RR_ADAPTIVE doesn't include HC keys, so HC sweeps WERE valid in step 13).
The HC-on no-op there was at a different regime (vt=0.10 = lots of cells
not even trusted, HC peek redundant). At vt=0.03 + ct=128 + pm020, many
cells DO get trusted at x16 — that's the regime where HC peek bites.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "21"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("19")
if INHERITED is None:
    raise RuntimeError("[21] step 19 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 128
VT_INH = 0.03
PM_INH = 0.20

BASE_21 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (tag, hc_on, tol)
HC_CONFIGS = [
    ("hcOff", False, 0.20),  # baseline = carry
    ("hc003", True,  0.03),
    ("hc005", True,  0.05),
    ("hc010", True,  0.10),
    ("hc020", True,  0.20),
]

VARIANTS_21 = []
for (base_name, base_overrides) in BASE_21:
    for hc_tag, hc_on, hc_tol in HC_CONFIGS:
        VARIANTS_21.append((f"{base_name}__bayer4x4_cell4x4_ct128_vt0030_pm020_{hc_tag}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": hc_on,
            "hierarchicalMuTolerance":       hc_tol,
            "accelDecayDisagreeThresh":      0.0,
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
        variants=VARIANTS_21,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="19", ref_variant=INHERITED,
              ref_label="step-19 carry (pm020, HC-off)")
write_picks_meta(STEP, inherited_from="19", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="HC sweep at ct=128/pm020 carry. Tests whether "
                        "hierarchicalConsistency (peek finer level before "
                        "trusting coarse) catches biased x16 cells that "
                        "pMin/fp can't. tol {0.03, 0.05, 0.10, 0.20} + "
                        "HC-off baseline. Optimum-in-middle bet: hc005.")
_HEADLESS_SCRIPT_DONE = True

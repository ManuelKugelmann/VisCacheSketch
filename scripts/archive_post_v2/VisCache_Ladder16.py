"""
VisCache_Ladder16.py — Step 16: varThreshold × pMin.

Inherits step-15 carry (= step-12 carry):
pos_norm__pos__qa012__bayer4x4_cell4x4_ct16_se000.

Step 13 found pMin to be a no-op at varThreshold=0.10 — the variance gate
fires first and strips RR safety nets of anything to do. The hypothesis
under test: tighter varThreshold opens a regime in which pMin actually
bites.

  - varThreshold: variance-driven RR gate. Lower = more rays traced even
    when the cell looks confident. 0.10 = inherited (the vt=0.10 row
    here re-validates step 13's pMin no-op finding under the corrected
    cascade as a sanity check).
  - pMin: per-trace RR floor. Higher = more rays traced regardless of
    cache confidence.

3 vt × 3 pMin = 9 variants. Pre-test on 1PL+32PL.
Optimum-in-middle bet: vt=0.05 + pMin=0.05.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "16"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("15")
if INHERITED is None:
    raise RuntimeError("[16] step 15 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16

BASE_16 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VT_VALUES   = [0.03, 0.05, 0.10]
PMIN_VALUES = [0.02, 0.05, 0.10]

VARIANTS_16 = []
for (base_name, base_overrides) in BASE_16:
    for vt in VT_VALUES:
        vt_tag = f"vt{int(round(vt*100)):03d}"   # vt003 / vt005 / vt010
        for pm in PMIN_VALUES:
            pm_tag = f"pm{int(round(pm*100)):03d}"
            VARIANTS_16.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH}_{vt_tag}_{pm_tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 CT_INH,
                "matureThreshold":               max(128, CT_INH),
                "varThreshold":                  vt,
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
        variants=VARIANTS_16,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="15", ref_variant=INHERITED,
              ref_label="step-15 carry (= step-12 carry)")
write_picks_meta(STEP, inherited_from="15", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="varThreshold x pMin sweep at step-12 carry. Step "
                        "13 found pMin no-op at vt=0.10 — this widens the "
                        "vt axis to 0.03/0.05 to test whether tighter vt "
                        "opens a regime where pMin bites. Optimum-in-"
                        "middle bet: vt005 + pm005.")
_HEADLESS_SCRIPT_DONE = True

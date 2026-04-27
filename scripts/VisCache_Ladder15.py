"""
VisCache_Ladder15.py — Step 15: bootThresholdFactorFootprintPx × matureThreshold.

Inherits step-12 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct16_se000.
Sweeps two interrelated "trust ceiling" knobs:

  - bootThresholdFactorFootprintPx (footprintScale): scales the boot
    threshold by log2(cellPixels). Big cells (more pixels per cell)
    require proportionally more samples before trust. Caps coarse-cell
    over-trust independent of ct.
  - matureThreshold: the saturation cap above which counters stop
    accumulating (per VHF protocol). Higher = more "memory" per cell,
    longer to forget bias.

3 footprintScale × 3 matureThreshold = 9 variants. Pre-test on 1PL+32PL.
Optimum-in-middle bet: footprintScale=1.0 + matureThreshold=128.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "15"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("14")
if INHERITED is None:
    raise RuntimeError("[15] step 14 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16

BASE_15 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

FP_VALUES = [0.0, 1.0, 2.0]
MAT_VALUES = [64, 128, 256]

VARIANTS_15 = []
for (base_name, base_overrides) in BASE_15:
    for fp in FP_VALUES:
        fp_tag = f"fp{int(round(fp*10)):03d}"   # fp000 / fp010 / fp020
        for mat in MAT_VALUES:
            mat_tag = f"mat{mat:03d}"
            VARIANTS_15.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH}_{fp_tag}_{mat_tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 CT_INH,
                "matureThreshold":               max(mat, CT_INH),
                "varThreshold":                  0.10,
                "bootThresholdFactorFootprintPx": fp,
                "forceDescendFootprintPx":       FD,
                "stderrThreshold":               0.0,
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
        variants=VARIANTS_15,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="14", ref_variant=INHERITED,
              ref_label="step-14 carry (= step-12)")
write_picks_meta(STEP, inherited_from="14", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="footprintScale x matureThreshold sweep at step-12 "
                        "carry. footprintScale enforces 'more samples for "
                        "big cells' to cap coarse over-trust. mature is "
                        "the counter saturation cap. Optimum-in-middle bet: "
                        "fp=1.0 + mat=128.")
_HEADLESS_SCRIPT_DONE = True

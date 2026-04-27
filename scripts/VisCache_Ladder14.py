"""
VisCache_Ladder14.py — Step 14: addressing × normalACoarse.

Inherits step-12 carry (step 13 was no-op).
Sweeps two interrelated cell-key choices:

  - addressing: pos vs dir_dist. pos uses (posA, posB=light) endpoint;
    dir_dist uses (posA, dirBin, distBin) — the ray's outgoing direction
    quantized into octahedral bins + distance bin. dir_dist had appeared
    to win on Sponza in earlier broken-cascade ladders; this re-validates
    against the corrected shader.
  - normalACoarse: angular bin size for surface-normal-aware addressing
    (folds normal into qa hash). Smaller = more cells per surface (e.g.
    floor vs wall corner), larger = collapsed.

2 addressing × 3 normalACoarse = 6 variants. Pre-test on 1PL+32PL.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "14"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("13")
if INHERITED is None:
    raise RuntimeError("[14] step 13 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16

ALL_B = make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                            quant_tag=QUANT_TAG)
BASE_POS      = [v for v in ALL_B if v[0] == f"pos_norm__pos__{QUANT_TAG}"]
BASE_DIR_DIST = [v for v in ALL_B if v[0] == f"pos_norm__dir_dist__{QUANT_TAG}"]

NORMAL_VALUES = [30.0, 60.0, 90.0]

VARIANTS_14 = []
for addr_tag, base_list in [("pos", BASE_POS), ("dirdist", BASE_DIR_DIST)]:
    for (base_name, base_overrides) in base_list:
        for n_deg in NORMAL_VALUES:
            n_tag = f"n{int(round(n_deg)):02d}"
            VARIANTS_14.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH}_{n_tag}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 CT_INH,
                "matureThreshold":               max(128, CT_INH),
                "varThreshold":                  0.10,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       FD,
                "stderrThreshold":               0.0,
                "enableHierarchicalConsistency": False,
                "hierarchicalMuTolerance":       0.20,
                "accelDecayDisagreeThresh":      0.0,
                "normalACoarse":                 n_deg,
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
        variants=VARIANTS_14,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="13", ref_variant=INHERITED,
              ref_label="step-13 carry (= step-12 carry)")
write_picks_meta(STEP, inherited_from="13", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="addressing x normalACoarse. pos vs dir_dist re-"
                        "validation under corrected cascade. normalACoarse "
                        "30/60/90 = fine/mid/coarse normal binning.")
_HEADLESS_SCRIPT_DONE = True

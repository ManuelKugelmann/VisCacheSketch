"""
VisCache_Ladder12.py - Step 12: cascade-on baseline [BASELINE, SUPERSEDED].

STATUS: Cascade-on default (cascadeWindowForward=12) baseline that established
vt=0.03 rejects all penumbra cells (Bernoulli theorem — see step 13 docstring).
Saturated at ~100% rays on 1AreaLight; useful as baseline for comparing
step 13/14 winners. Step 14 supersedes with the canonical fd × ct sweep.

Same bayer x cell-footprint matrix as step 11, but with the cascade
descent enabled (cascadeWindowForward=12, the production default).
Step 11 set cascadeWindowForward=0 (entry-level only) to isolate the
entry-math correctness; step 12 verifies whether cascade descent
reduces ray rate or improves trust at no cost.

Sweep: bayer in {2, 4} x fd in {1, 4, 16, 64} = 8 variants.
ct calibrated per cell (ct = K_FRAMES * cell_pixels) so each cell needs
the same 2 frames to mature regardless of size.

Compare side-by-side with step 11 plates:
- step 11 entry-only: lookup visits ONLY targetLvl - cells at sub-pixel
  scales (cell1x1 -> lvl 13) cold-miss heavily
- step 12 cascade-on: lookup visits [targetLvl, targetLvl+12] - finer
  cells get queried first; coarser cells inserted via parent-preinit
  amortization. Reads still <= target footprint (no back window).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "12"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("10")
if INHERITED is None:
    raise RuntimeError("[12] step 10 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
VT = 0.03
PM = 0.10
# ct calibrated per cell size: ct = K_FRAMES x cell_pixels.
# Each cell needs the same number of frames to mature regardless of size:
#   1x1 cell  ->  1 sample/frame  -> ct = K_FRAMES x 1
#   2x2 cell  ->  4 samples/frame -> ct = K_FRAMES x 4
#   4x4 cell  -> 16 samples/frame -> ct = K_FRAMES x 16
#   8x8 cell  -> 64 samples/frame -> ct = K_FRAMES x 64
# K_FRAMES = 2 -> mature in 2 logical frames at any cell size. Fair
# comparison: each variant gets the same opportunity to converge.
K_FRAMES = 2

BASE_12 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

BAYER_VALUES = [2, 4]
FD_VALUES    = [1, 4, 16, 64]  # 1x1, 2x2, 4x4, 8x8 cells; cell_pixels = fd

VARIANTS_12 = []
for (base_name, base_overrides) in BASE_12:
    for bayer_n in BAYER_VALUES:
        for fd in FD_VALUES:
            cell_n = int(round(fd**0.5))
            ct = K_FRAMES * fd  # ct prop cell pixels - fair maturation time
            tag = f"bayer{bayer_n}x{bayer_n}_cell{cell_n}x{cell_n}"
            VARIANTS_12.append((f"{base_name}__{tag}_ct{ct:03d}_vt0030_pm010", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(128, ct * 2),
                "varThreshold":                  VT,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       fd,
                "stderrThreshold":               0.0,
                "enableHierarchicalConsistency": False,
                "hierarchicalMuTolerance":       0.20,
                "accelDecayDisagreeThresh":      0.0,
                "pMin":                          PM,
                "bayerN":                        bayer_n,
                "enableDecayAutoTune":           False,
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
              ref_step="10", ref_variant=INHERITED,
              ref_label="step-10 carry (qa012/ct4)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Bayer x cell footprint matrix. bayer {2x2, 4x4} "
                        "x cell {1x1, 2x2, 4x4, 8x8} = 8 variants. ct "
                        "calibrated per-variant as 2 x cell_pixels "
                        "(ct=2/8/32/128 for cells 1x1/2x2/4x4/8x8) so "
                        "each cell needs the same 2 frames to mature "
                        "regardless of size. Tests matched vs mismatched "
                        "Bayer-cell symmetry on a level playing field.")
_HEADLESS_SCRIPT_DONE = True

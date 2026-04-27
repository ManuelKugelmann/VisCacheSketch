"""
VisCache_Ladder11.py — Step 11 v3: bayer × cell-footprint matrix.

Post-archive restart. Cell-size is the first axis to map. User feedback:
- bayer 1x1 breaks 1spp (no multiframe averaging)
- bayer 8x8 is too much (64 slots — wasteful)
- bayer 2x2 and 4x4 are the practical range
- cell footprint (fd) should span 1x1 to 8x8 to see "matched vs mismatched"
  Bayer-cell symmetry effects

Sweep: bayer ∈ {2, 4} × fd ∈ {1, 4, 16, 64} = 8 variants. Single ct=64.

  bayer  fd   layout
  2x2    1×1  bayer larger than cell (4 slots, 1 px cell)
  2x2    2×2  matched (4 slots, 4 px cell)
  2x2    4×4  cell larger than bayer
  2x2    8×8  cell much larger than bayer
  4x4    1×1  bayer much larger than cell
  4x4    2×2  bayer larger than cell
  4x4    4×4  matched (16 slots, 16 px cell)
  4x4    8×8  cell larger than bayer

Diagonals (matched) and off-diagonals tell us how Bayer-cell symmetry
matters. After cascade-lookup fix that ensures reads stay at-or-finer
than entry level, the cell-footprint is the actual cache spatial unit
the lookup queries.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "11"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("10")
if INHERITED is None:
    raise RuntimeError("[11] step 10 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
VT = 0.03
PM = 0.10
# ct calibrated per cell size: ct = K_FRAMES × cell_pixels.
# Each cell needs the same number of frames to mature regardless of size:
#   1x1 cell  →  1 sample/frame  → ct = K_FRAMES × 1
#   2x2 cell  →  4 samples/frame → ct = K_FRAMES × 4
#   4x4 cell  → 16 samples/frame → ct = K_FRAMES × 16
#   8x8 cell  → 64 samples/frame → ct = K_FRAMES × 64
# K_FRAMES = 2 → mature in 2 logical frames at any cell size. Fair
# comparison: each variant gets the same opportunity to converge.
K_FRAMES = 2

BASE_11 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

BAYER_VALUES = [2, 4]
FD_VALUES    = [1, 4, 16, 64]  # 1x1, 2x2, 4x4, 8x8 cells; cell_pixels = fd

VARIANTS_11 = []
for (base_name, base_overrides) in BASE_11:
    for sub_n in BAYER_VALUES:
        for fd in FD_VALUES:
            cell_n = int(round(fd**0.5))
            ct = K_FRAMES * fd  # ct ∝ cell pixels — fair maturation time
            tag = f"bayer{sub_n}x{sub_n}_cell{cell_n}x{cell_n}"
            VARIANTS_11.append((f"{base_name}__{tag}_ct{ct:03d}_vt0030_pm010", {
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
                "subframeN":                     sub_n,
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
        variants=VARIANTS_11,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="10", ref_variant=INHERITED,
              ref_label="step-10 carry (qa012/ct4)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Bayer × cell footprint matrix. bayer {2x2, 4x4} "
                        "× cell {1x1, 2x2, 4x4, 8x8} = 8 variants. ct "
                        "calibrated per-variant as 2 × cell_pixels "
                        "(ct=2/8/32/128 for cells 1x1/2x2/4x4/8x8) so "
                        "each cell needs the same 2 frames to mature "
                        "regardless of size. Tests matched vs mismatched "
                        "Bayer-cell symmetry on a level playing field.")
_HEADLESS_SCRIPT_DONE = True

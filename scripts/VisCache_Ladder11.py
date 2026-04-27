"""
VisCache_Ladder11.py — Step 11: subframeN × fd Bayer-cell symmetry.

Inherits step-10 carry pos_norm__pos__qa012__ct4 (multi-level cascade,
qa012 quantization, bootThreshold=4). Sweeps two interrelated params:

  - subframeN: Bayer slot count from step 01 convention (sub2 = 2x2 Bayer
    = 4 slots, sub4 = 4x4 = 16 slots, sub8 = 8x8 = 64 slots).
  - fd (forceDescendFootprintPx): pixel-footprint target for the cascade
    entry level. Cell-size target = pixelSize * sqrt(fd). fd=4 means 2x2
    pixel cells, fd=16 means 4x4, fd=64 means 8x8.

Hypothesis: matched pairs (sub2,fd=4) / (sub4,fd=16) / (sub8,fd=64) align
the Bayer slot grid with the target cell footprint — each cell receives
exactly 1 sample from each Bayer slot per frame. We expect matched pairs
to outperform mismatched ones, with optimum-in-middle at (sub4, fd=16).

3 subframeN x 3 fd = 9 variants. Pre-test on 1PL+32PL (~25 min).
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
    raise RuntimeError("[11] step 10 picks.json missing — run step 10 first.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

# Step-10 carry baseline: pos_norm__pos with qa012__ct4
NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
CT_INH = 4

BASE_11 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                           quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (subframeN, fd) — 3 x 3 grid; matched diagonal is (2,4), (4,16), (8,64).
# Naming follows step 01 NxN convention: sub2x2 / sub4x4 / sub8x8 = Bayer
# slot grid; cell2x2 / cell4x4 / cell8x8 = target pixel-footprint cell.
# The matched diagonal is (sub2x2, cell2x2), (sub4x4, cell4x4), (sub8x8, cell8x8).
SUB_FD_GRID = [
    (2,  4),   (2, 16),   (2, 64),
    (4,  4),   (4, 16),   (4, 64),
    (8,  4),   (8, 16),   (8, 64),
]

def _cell_tag(fd_value):
    side = int(round(fd_value ** 0.5))
    return f"{side}x{side}"

VARIANTS_11 = []
for (base_name, base_overrides) in BASE_11:
    for (sub, fd) in SUB_FD_GRID:
        VARIANTS_11.append((f"{base_name}__ct{CT_INH}_bayer{sub}x{sub}_cell{_cell_tag(fd)}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               128,
            "varThreshold":                  0.10,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       fd,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "subframeN":                     sub,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

# Multi-frame: frames=N, spp=1. Three SPP tiers (x1, x4, x16) for the
# pre-test; full run can extend if step picker gates pass.
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
              ref_label="step-10 carry (qa012__ct4)")
write_picks_meta(STEP, inherited_from="10", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="subframeN x fd Bayer-cell symmetry sweep. Matched "
                        "diagonal (sub2,fd=4)/(sub4,fd=16)/(sub8,fd=64) "
                        "tiles target cell with Bayer slots so each cell "
                        "gets exactly 1 sample per slot per frame. Off-"
                        "diagonal mismatches predicted to fragment samples "
                        "or under-fill cells. Optimum-in-middle bet: "
                        "(sub4, fd=16).")
_HEADLESS_SCRIPT_DONE = True

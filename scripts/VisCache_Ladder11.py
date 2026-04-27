"""
VisCache_Ladder11.py — Step 11 v2: entry-level cell size × ct.

Post-archive restart on the corrected metric pipeline (cascade-lookup
fix, log-space tone-map, multi-scale median artifact, cache-vanilla
deltas). The first axis: get the cell size right.

Entry-level cell footprint (NxN pixels): 1, 2, 4, 8 px-square (= fd
1, 4, 16, 64 px²). Each paired with subframeN=N for Bayer-cell symmetry
(every cell receives one sample per slot per frame, exactly tiling the
target footprint).

  (subframeN=1, fd=1)   — 1×1 px cell, no Bayer dispersion
  (subframeN=2, fd=4)   — 2×2 cell, 4 Bayer slots
  (subframeN=4, fd=16)  — 4×4 cell, 16 slots (current default)
  (subframeN=8, fd=64)  — 8×8 cell, 64 slots

Second axis: ct ∈ {32, 128, 512}, the bootstrap trust threshold.
Cheaper ct trusts cells earlier; stricter ct waits for more samples.

4 × 3 = 12 variants. Targeted span: 10–60% rays, 0–30% err.
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
VT = 0.03   # mid value; isolated for this sweep
PM = 0.10   # post-merge-fix default

BASE_11 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# (subframe_N, fd_px²) — matched Bayer-cell pairs. NxN cell footprint.
SIZE_CONFIGS = [(1, 1), (2, 4), (4, 16), (8, 64)]
CT_VALUES = [32, 128, 512]

VARIANTS_11 = []
for (base_name, base_overrides) in BASE_11:
    for sub_n, fd in SIZE_CONFIGS:
        size_tag = f"bayer{sub_n}x{sub_n}_cell{sub_n}x{sub_n}"
        for ct in CT_VALUES:
            ct_tag = f"ct{ct:03d}"
            VARIANTS_11.append((f"{base_name}__{size_tag}_{ct_tag}_vt0030_pm010", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(128, ct),
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
                  notes="entry-level cell size × ct. 4 size pairs (1x1, "
                        "2x2, 4x4, 8x8 px-square; each subframeN matched) "
                        "× 3 ct values (32, 128, 512). 12 variants. "
                        "First axis to map the rays-vs-err tradeoff "
                        "after the cascade-lookup fix that ensures "
                        "reads stay at-or-finer than entry level.")
_HEADLESS_SCRIPT_DONE = True

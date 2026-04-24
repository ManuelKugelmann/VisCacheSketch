"""
VisCache_Ladder36.py — Step 36: pos vs dir_dist addressing at HC peek.

Steps 31-35 plateaued at Sponza x16 blob ~150-200% regardless of gate
tuning. Hypothesis: the posB endpoint-position addressing lumps paths
through the same geometric cell with different shadow-source relationships
into the same cache entry, so biased mu locks in.

dir_dist addressing replaces posB with (ray direction × distance along
ray), separating cells by view-cone rather than world-space endpoint.
Should distinguish "shadow from sunlight" vs "shadow from window" paths
that share a posA but hit different B points.

Four addressing variants, all with fd16+hcOn+tol020+sub4:
  a_pos           — baseline (step-31 config)
  b_dir_dist1     — direction-only (distance collapsed)
  c_dir_dist      — direction + distance
  d_pos1          — position-only B (direction+distance both collapsed)

4 × 3 spp × scenes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "36"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

# Grab the full 4-variant B-side family (pos_norm__pos1, dir1_dist1, pos,
# dir_dist1, dir_dist) and iterate.
ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)

# Map the base-variant names to step-36 suffixes.
SUFFIX_MAP = {
    "pos_norm__pos__qa012":         "a_pos",
    "pos_norm__dir_dist1__qa012":   "b_dir_dist1",
    "pos_norm__dir_dist__qa012":    "c_dir_dist",
    "pos_norm__pos1__qa012":        "d_pos1",
}

VARIANTS_36 = []
for (base_name, base_overrides) in ALL_B:
    if base_name not in SUFFIX_MAP:
        continue
    suffix = SUFFIX_MAP[base_name]
    VARIANTS_36.append((f"{base_name}__ct4_fd16_hcOn_tol020_pm005_sub4_{suffix}", {
        **base_overrides,
        **NO_JITTER,
        "bootThreshold":                 4,
        "matureThreshold":               128,
        "varThreshold":                  0.01,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       16,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": True,
        "hierarchicalMuTolerance":       0.20,
        "accelDecayDisagreeThresh":      0.0,
        "pMin":                          PM_INH,
        "subframeN":                     4,
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
        variants=VARIANTS_36,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="35", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="B-side addressing sweep at step-32 carry. Test "
                        "whether dir_dist (view-cone cells) breaks the "
                        "Sponza x16 blob plateau by separating cells by "
                        "light-source rather than shared geometric "
                        "endpoint.")
_HEADLESS_SCRIPT_DONE = True

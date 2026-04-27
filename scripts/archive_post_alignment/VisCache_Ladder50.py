"""
VisCache_Ladder50.py — Step 50: ct=32 + stderr=0.02 on Cornell.

Step 49 found ct=32+stderr=0.02 massively improves Sponza (x4 blob
130 -> 31, x16 blob 140 -> 43). Verify no Cornell regression.

Two variants (pos), single-run (Cornell is stable):
  a_ct16_se002 — step-48 winner
  b_ct32_se002 — step-49 winner

2 * 3 spp * 4 Cornell = 24 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "50"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]

VARIANTS = [
    ("a_ct16_se002", 16, 0.02),
    ("b_ct32_se002", 32, 0.02),
]

VARIANTS_50 = []
for (base_name, base_overrides) in BASE_POS:
    for (suffix, ct, se) in VARIANTS:
        VARIANTS_50.append((f"{base_name}__fd16_hcOn_tol020_sub4_{suffix}", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct,
            "matureThreshold":               128,
            "varThreshold":                  0.01,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       16,
            "stderrThreshold":               se,
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
        variants=VARIANTS_50,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="49", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Verify step-49 Sponza winner (ct=32) doesn't "
                        "regress Cornell.")
_HEADLESS_SCRIPT_DONE = True

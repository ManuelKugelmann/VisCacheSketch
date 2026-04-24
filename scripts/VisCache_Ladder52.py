"""
VisCache_Ladder52.py — Step 52: full ct sweep at new carry.

Step 49-50 found ct=32+stderr=0.02 = universal win. Sweep further to
find where blob saturates and rays cost ramps.

5 ct values at pos, fd16+hcOn+tol020+se002+sub4, triple-trial on Sponza:
  a_ct008  — loose trust (steps before 47 used ct=4; try 8)
  b_ct016  — step-48 winner
  c_ct032  — step-49 winner (current carry)
  d_ct064  — double current
  e_ct128  — matureThreshold (ct=mature, treats "mature" as trust)

5 * 3 trials * 3 spp = 45 runs on Sponza.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "52"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]

VARIANTS = [
    ("a_ct008",   8),
    ("b_ct016",  16),
    ("c_ct032",  32),
    ("d_ct064",  64),
    ("e_ct128", 128),
]

VARIANTS_52 = []
for trial in (1, 2, 3):
    for (base_name, base_overrides) in BASE_POS:
        for (suffix, ct) in VARIANTS:
            VARIANTS_52.append((f"{base_name}__fd16_hcOn_tol020_se002_sub4_{suffix}__t{trial}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(128, ct),
                "varThreshold":                  0.01,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       16,
                "stderrThreshold":               0.02,
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
        variants=VARIANTS_52,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="50", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Full ct sweep 8/16/32/64/128 at current carry. "
                        "Find blob saturation point and the rays/blob "
                        "tradeoff curve.")
_HEADLESS_SCRIPT_DONE = True

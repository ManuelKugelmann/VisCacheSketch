"""
VisCache_Ladder46.py — Step 46: pMin tuning on post-clamp pos addressing.

With the clamp fix (commit f9460e3) pos addressing now works on env rays,
blob improved (148 -> 122 at x1 Sponza) but rays exploded (16% -> 57%).
Hypothesis: the cache now correctly identifies bimodal env cells as
"needs tracing" but we could push pMin lower to trust uniform env cells
more.

Triple-trial pMin sweep at pos + fd16+hcOn+tol020+sub4 on Sponza:

  a_pm010  — pMin=0.10 (loose RR floor, step-20+ default)
  b_pm005  — pMin=0.05 (session default)
  c_pm002  — pMin=0.02 (tight, trust cache more)
  d_pm001  — pMin=0.01 (very tight)

4 × 3 trials × 3 spp × 1 scene = 36 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "46"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]

VARIANTS = [
    ("a_pm010", 0.10),
    ("b_pm005", 0.05),
    ("c_pm002", 0.02),
    ("d_pm001", 0.01),
]

VARIANTS_46 = []
for trial in (1, 2, 3):
    for (base_name, base_overrides) in BASE_POS:
        for (suffix, pm) in VARIANTS:
            VARIANTS_46.append((f"{base_name}__ct4_fd16_hcOn_tol020_sub4_{suffix}__t{trial}", {
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
                "pMin":                          pm,
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
        variants=VARIANTS_46,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="45", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="pMin sweep with post-clamp pos addressing. See if "
                        "tighter RR floor reduces the 57%% rays cost that "
                        "the clamp fix introduced, without regressing "
                        "quality.")
_HEADLESS_SCRIPT_DONE = True

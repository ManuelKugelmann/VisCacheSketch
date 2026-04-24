"""
VisCache_Ladder51.py — Step 51: cascadeVisitCount stride sweep on Sponza.

With step-48/49 carry (ct=32 stderr=0.02 fd16 hcOn tol020 sub4), sweep
the cascade stride count. Smaller count = bigger cell-size steps per
stride = fewer writes per trace + wider coarse/fine gap per step.
Larger count = finer granularity + more per-trace writes.

  a_visit08 — 8 visits, factor 2.38x per stride
  b_visit16 — 16 visits, factor 1.58x per stride
  c_visit32 — 32 visits, factor 1.25x per stride (current default)
  d_visit64 — 64 visits, factor 1.12x per stride

Triple-trial on Sponza (pos addressing).
4 × 3 trials × 3 spp = 36 runs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "51"
res = int(os.environ.get("RES", "512"))

_qa_tag = "qa012"
QUANT_WINNER = QUANT_SWEEP[_qa_tag]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
PM_INH = 0.05

ALL_B = make_norm_variants(quant=QUANT_WINNER, base=PRESET_MINIMAL,
                            quant_tag=_qa_tag)
BASE_POS = [v for v in ALL_B if v[0] == f"pos_norm__pos__{_qa_tag}"]

VARIANTS = [
    ("a_visit08",  8),
    ("b_visit16", 16),
    ("c_visit32", 32),
    ("d_visit64", 64),
]

VARIANTS_51 = []
for trial in (1, 2, 3):
    for (base_name, base_overrides) in BASE_POS:
        for (suffix, vc) in VARIANTS:
            VARIANTS_51.append((f"{base_name}__ct32_fd16_hcOn_tol020_se002_sub4_{suffix}__t{trial}", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 32,
                "matureThreshold":               128,
                "varThreshold":                  0.01,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       16,
                "stderrThreshold":               0.02,
                "enableHierarchicalConsistency": True,
                "hierarchicalMuTolerance":       0.20,
                "accelDecayDisagreeThresh":      0.0,
                "pMin":                          PM_INH,
                "subframeN":                     4,
                "cascadeVisitCount":             vc,
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
        variants=VARIANTS_51,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP)
write_picks_meta(STEP, inherited_from="49", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Stride count sweep at step-49 carry. Tests user's "
                        "hypothesis that bigger level steps (fewer visits) "
                        "might work better — fewer writes per trace with "
                        "wider cell-size gaps between visited levels.")
_HEADLESS_SCRIPT_DONE = True

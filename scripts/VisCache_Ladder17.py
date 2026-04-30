"""
VisCache_Ladder17.py - posBCoarse sweep on Sponza.

Hypothesis: Sponza's 33% rays-saved ceiling is because posB cells at the
queried cascade level aggregate over multiple lights/directions, producing
penumbra-like mu values that vt=0.01 rejects categorically. Smaller posB
cells should resolve individual lights into separate cache entries with
mu near 0 or 1 — vt-trustable.

Sweep: posBCoarse ∈ {0.36, 0.18, 0.09, 0.04} at the step-14 winner config
       (cell4x4 ct=2 vt=0.01 pm=0.02). Sponza only.
4 variants × 3 SPP = 12 runs ~5 min.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, write_picks_meta, _DEFAULT_PICKER_RULE, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "17"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

SUBFRAME_N = 2
FD = 16
CT = 2
VT = 0.01
PM = 0.02

POSB_VALUES = [0.36, 0.18, 0.09, 0.04]

DEFAULT_SCENES = ["Sponza"]

BASE_17 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VARIANTS_17 = []
for (base_name, base_overrides) in BASE_17:
    for posB in POSB_VALUES:
        posb_tag = f"qB{int(round(posB*100)):03d}"
        tag = f"bayer{SUBFRAME_N}x{SUBFRAME_N}_cell4x4_ct{CT:03d}_vt010_pm002_{posb_tag}"
        VARIANTS_17.append((f"{base_name}__{tag}", {
            **base_overrides,
            "bootThreshold":                 CT,
            "matureThreshold":               max(64, CT * 4),
            "varThreshold":                  VT,
            "stderrThreshold":               0.0,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM,
            "subframeN":                     SUBFRAME_N,
            "enableDecayAutoTune":           False,
            "posBCoarse":                    posB,   # the swept axis
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, "tableCapacity": 1 << 25}
MF_CONFIGS = [(0, 0, 1, 1), (0, 0, 4, 1), (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    run_baseline(step_name="00", frame_configs=[(0, 0, 1)],
                  scene_file=scene_file, resX=res, resY=res,
                  extra_spp=[4, 16], mogwai_globals=globals())
    run_variants(step_name=STEP, frame_configs=MF_CONFIGS,
                  scene_file=scene_file, variants=VARIANTS_17,
                  resX=res, resY=res, mogwai_globals=globals(),
                  step_overrides=STEP_OVERRIDES)

finalize_step(STEP, inherited_winners=[], ref_step=None)
write_picks_meta(STEP, inherited_from="14", inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="posBCoarse sweep on Sponza. If Sponza's rays-saved "
                        "ceiling breaks at smaller posB, the limit was light "
                        "discrimination; if not, the limit is vt-rejection.")
_HEADLESS_SCRIPT_DONE = True

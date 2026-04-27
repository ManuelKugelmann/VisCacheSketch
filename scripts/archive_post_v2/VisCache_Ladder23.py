"""
VisCache_Ladder23.py — Step 23: ct extension + qa003 finer cells.

Inherits step-22 carry pos_norm__pos__qa006__bayer4x4_cell4x4_ct128_vt0030_pm020_hc005.

Step 22 trend: cell size halving (qa012→qa006) reduced Sponza x16 blob
from 21.1 to 15.3 (-27%). Two extrapolations to test:

  1. **qa003** (cell halved again): if the trend continues, qa003 should
     bring Sponza x16 blob to ~10 — at the artifact threshold.
  2. **Higher ct** (ct=256, 512) at qa006: more samples per cell before
     trust. Step 18 showed ct=256 didn't beat ct=128 at qa012, but
     untested at qa006+HC.

Combined sweep: 2 qa × 3 ct = 6 variants on Bistro+Sponza+32PL.
- qa006 + ct {128, 256, 512}
- qa003 + ct {128, 256, 512}

Optimum-in-middle bet: qa006 + ct=256, OR qa003 + ct=128.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, MULTI_LEVEL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "23"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("22")
if INHERITED is None:
    raise RuntimeError("[23] step 22 picks.json missing carried winner.")

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
VT_INH = 0.03
PM_INH = 0.20

QA_TAGS = ["qa006", "qa003"]
CT_VALUES = [128, 256, 512]

VARIANTS_23 = []
for qa_tag in QA_TAGS:
    quant = QUANT_SWEEP[qa_tag]
    base_list = make_norm_variants(quant=quant, base=PRESET_MINIMAL,
                                    quant_tag=qa_tag)
    base = next(v for v in base_list if v[0] == f"pos_norm__pos__{qa_tag}")
    base_name, base_overrides = base
    for ct in CT_VALUES:
        ct_tag = f"ct{ct:03d}"
        VARIANTS_23.append((f"{base_name}__bayer4x4_cell4x4_{ct_tag}_vt0030_pm020_hc005", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 ct,
            "matureThreshold":               max(128, ct),
            "varThreshold":                  VT_INH,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": True,
            "hierarchicalMuTolerance":       0.05,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
        }))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                  "tableCapacity": 1 << 25}

MF_CONFIGS = [(0, 0, 1, 1),  (0, 0, 4, 1),  (0, 0, 16, 1)]

for scene_file in get_scenes(default=list(MULTI_LEVEL_SCENES)):
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
        variants=VARIANTS_23,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="22", ref_variant=INHERITED,
              ref_label="step-22 carry (qa006 + ct128)")
write_picks_meta(STEP, inherited_from="22", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Combined cell-size + ct sweep. qa {qa006, qa003} x "
                        "ct {128, 256, 512}. Step 22 trend (qa012->qa006 = "
                        "-27% Sponza x16 blob) suggests qa003 lands near "
                        "artifact threshold. ct extension tests if even more "
                        "sample evidence helps at finer cells. Optimum-in-"
                        "middle bet: qa006 + ct=256, OR qa003 + ct=128.")
_HEADLESS_SCRIPT_DONE = True

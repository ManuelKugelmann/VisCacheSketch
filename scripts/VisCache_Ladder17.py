"""
VisCache_Ladder17.py — Step 17: varThreshold finer sweep below 0.03.

Inherits step-16 carry pos_norm__pos__qa012__bayer4x4_cell4x4_ct16_vt003_pm010.

Step 16 found tighter vt (0.03) to be a Pareto improvement on 1PL but
0.03 was the *bottom* of that grid — the optimum may be lower.

This step sweeps vt finer around the boundary:
  - vt=0.005 — risk: gate barely fires, cache approaches always-trace
  - vt=0.01  — aggressive but still gating
  - vt=0.02  — middle bet (optimum-in-middle)
  - vt=0.03  — step-16 carry
  - vt=0.05  — between step-16 (vt005) and old default (vt010)

5 variants. Pre-test on 1PL+32PL. Optimum-in-middle bet: vt=0.02.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "17"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("16")
if INHERITED is None:
    raise RuntimeError("[17] step 16 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
SUBFRAME_N = 4
FD = 16
CT_INH = 16
PM_INH = 0.10  # step-16 carry pm010

BASE_17 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

VT_VALUES = [0.005, 0.01, 0.02, 0.03, 0.05]

VARIANTS_17 = []
for (base_name, base_overrides) in BASE_17:
    for vt in VT_VALUES:
        # 3-digit pct: vt005=0.05, vt003=0.03, vt002=0.02, vt001=0.01, vt000=0.005 (rounds to 0)
        # use 4-digit fractional encoding: vt0005, vt0010, vt0020, vt0030, vt0050
        vt_tag = f"vt{int(round(vt*1000)):04d}"
        VARIANTS_17.append((f"{base_name}__bayer4x4_cell4x4_ct{CT_INH}_{vt_tag}_pm010", {
            **base_overrides,
            **NO_JITTER,
            "bootThreshold":                 CT_INH,
            "matureThreshold":               max(128, CT_INH),
            "varThreshold":                  vt,
            "bootThresholdFactorFootprintPx": 0.0,
            "forceDescendFootprintPx":       FD,
            "stderrThreshold":               0.0,
            "enableHierarchicalConsistency": False,
            "hierarchicalMuTolerance":       0.20,
            "accelDecayDisagreeThresh":      0.0,
            "pMin":                          PM_INH,
            "subframeN":                     SUBFRAME_N,
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
        variants=VARIANTS_17,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[INHERITED],
              ref_step="16", ref_variant=INHERITED,
              ref_label="step-16 carry (vt003)")
write_picks_meta(STEP, inherited_from="16", inherited=[INHERITED],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Finer vt sweep below the step-16 lower bound. "
                        "vt {0.005, 0.01, 0.02, 0.03, 0.05}, fixed pm=0.10. "
                        "Optimum-in-middle bet: vt=0.02.")
_HEADLESS_SCRIPT_DONE = True

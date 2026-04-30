"""
VisCache_Ladder11.py - Step 11: entry-level-only debug [VALIDATED, DEBUG ONLY].

STATUS: One-time debug to verify entry-level math (cascadeWindowForward=0 so
lookup visits ONLY targetLvl). Validated cell sizes vary correctly with fd
after PathTracer cbuffer-bind bug fix. Production code uses default
cascadeWindowForward=12 (step 12). Keep for diagnosis if entry math regresses.

Cascade descent disabled (cascadeWindowForward=0). vhfLookup queries ONLY
at targetLvl - if no cell exists there or it's too sparse, the lookup
returns no data (falls through to trace). Isolates whether the entry-
level math produces correctly-sized cells for different fd values.

Same bayer x cell-footprint matrix as step 12 (the cascade-on version),
so we can compare entry-only vs full-descent side-by-side. If the qA
hash plates show distinct cell sizes per fd here, the entry-level math
is right and step 12's "cells look uniform" issue is from cascade
descent collapsing back to a common level.

Sweep: bayer {2x2, 4x4} x fd {1, 4, 16, 64} = 8 variants. ct calibrated
per cell size (2 frames to mature, ct=2/8/32/128). cascadeWindowForward=0.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, read_carried_winner, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL_MULTI, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "11"
res = int(os.environ.get("RES", "512"))

INHERITED = read_carried_winner("10")
if INHERITED is None:
    raise RuntimeError("[11] step 10 picks.json missing carried winner.")

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}
VT = 0.03
PM = 0.10
K_FRAMES = 2

BASE_11 = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL_MULTI,
                                          quant_tag=QUANT_TAG)
           if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

BAYER_VALUES = [2, 4]
FD_VALUES    = [1, 4, 16, 64]

VARIANTS_11 = []
for (base_name, base_overrides) in BASE_11:
    for sub_n in BAYER_VALUES:
        for fd in FD_VALUES:
            cell_n = int(round(fd**0.5))
            ct = K_FRAMES * fd
            tag = f"bayer{sub_n}x{sub_n}_cell{cell_n}x{cell_n}"
            VARIANTS_11.append((f"{base_name}__{tag}_ct{ct:03d}_vt0030_pm010_entry", {
                **base_overrides,
                **NO_JITTER,
                "bootThreshold":                 ct,
                "matureThreshold":               max(128, ct * 2),
                "varThreshold":                  VT,
                "bootThresholdFactorFootprintPx": 0.0,
                "forceDescendFootprintPx":       fd,
                "cascadeWindowForward":          0,   # entry-only debug
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
                  notes="Entry-level-only debug: cascadeWindowForward=0 "
                        "disables cascade descent; vhfLookup queries only "
                        "at targetLvl. Same bayer x cell matrix as step 12. "
                        "Compare qA hash plates between step 11 (entry-only) "
                        "and step 12 (full descent) to verify entry-level "
                        "math produces distinct cell sizes per fd.")
_HEADLESS_SCRIPT_DONE = True

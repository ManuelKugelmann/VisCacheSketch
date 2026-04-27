"""
VisCache_Ladder99.py — Validation: viscache at 100% trace ≡ vanilla.

Sanity step. Runs viscache with pMin=1.0 (RR floor = always trace,
regardless of trust state) on all scenes. Output should match vanilla
to within RNG-stream noise floor.

If the cache and vanilla streams are properly aligned this should show:
- err Δ ≈ 0
- artifact Δ ≈ 0
- noise Δ ≈ 0

Currently they're NOT aligned (cache uses vcCreateSG for the gate
decision, plus Bayer sub-pixel dispersion vs vanilla's stratification).
The validation result tells us the magnitude of the comparison noise
floor — every cache result includes this floor as background noise.

Single variant. Runs on all 5 scenes (4 Cornell + 32PL). Each scene/SPP
combination tells us how much "noise" is irreducible just from the
cache infrastructure being structurally different from vanilla.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    write_picks_meta, _DEFAULT_PICKER_RULE, ALL_SCENES, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP

STEP = "99"
res = int(os.environ.get("RES", "512"))

QUANT_TAG = "qa012"
QUANT = QUANT_SWEEP[QUANT_TAG]

NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

BASE = [v for v in make_norm_variants(quant=QUANT, base=PRESET_MINIMAL,
                                       quant_tag=QUANT_TAG)
        if v[0] == f"pos_norm__pos__{QUANT_TAG}"]

# Single variant: pMin=1.0 forces every gate to "trace" — viscache
# becomes a structurally-equivalent path tracer. Bayer dispersion still
# differs (subframeN=4) so the noise floor reflects that difference.
VARIANTS_99 = []
for (base_name, base_overrides) in BASE:
    VARIANTS_99.append((f"{base_name}__bayer4x4_cell4x4_FORCED_TRACE_pm100", {
        **base_overrides,
        **NO_JITTER,
        "bootThreshold":                 16,
        "matureThreshold":               128,
        "varThreshold":                  0.03,
        "bootThresholdFactorFootprintPx": 0.0,
        "forceDescendFootprintPx":       16,
        "stderrThreshold":               0.0,
        "enableHierarchicalConsistency": False,
        "hierarchicalMuTolerance":       0.20,
        "accelDecayDisagreeThresh":      0.0,
        "pMin":                          1.0,   # ← always trace
        "subframeN":                     4,
        "enableDecayAutoTune":           False,
    }))

# Override RR_ADAPTIVE's pMin=0.05 so our pm=1.0 sticks — validation
# wants strict always-trace.
VALIDATION_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI,
                         "tableCapacity": 1 << 25,
                         "pMin": 1.0,
                         "enableVisCacheAdaptivePMin": False}

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
        variants=VARIANTS_99,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=VALIDATION_OVERRIDES,
    )

finalize_step(STEP, inherited_winners=[],
              ref_step=None, ref_variant=None, ref_label=None)
write_picks_meta(STEP, inherited_from=None, inherited=[],
                  carried={}, rule=_DEFAULT_PICKER_RULE,
                  notes="Validation: viscache forced 100% trace (pMin=1.0). "
                        "Output should match vanilla within RNG-stream + "
                        "Bayer-dispersion noise floor. Any err/artifact/noise "
                        "delta is the irreducible structural-comparison floor.")
_HEADLESS_SCRIPT_DONE = True

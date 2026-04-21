"""
VisCache_Ladder10.py — Step 10: quant × threshold sweep, MULTI-LEVEL.

Multi-level mirror of step 05 (single-level quant × threshold). Uses the
same defaults as step 11 (autoTuneCells=True, LEVELS_MULTI) so the sweeps
are directly comparable. Footprint off (step-11 winner), no jitter.

  3 quants × 3 thresholds = 9 variants × 2 SPP = 18 runs/scene

Quant axis = step-03 sweep (qa006 / qa012 / qa036). Threshold axis matches
step 05 and step 11 (th2 / th4 / th16, actual bootThreshold values).

Red-star reference = step-05 single-level best (`qA024_qB036__th2`) for
visual comparison of the multi-level gain on the same plot.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder10.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    finalize_step, make_norm_variants, \
    PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, QUANT_SWEEP, SUBFRAME_2x2

STEP = "10"
res = int(os.environ.get("RES", "512"))

THRESH_SWEEP = {
    "th2":  {"bootThreshold":  2, "matureThreshold": 128},
    "th4":  {"bootThreshold":  4, "matureThreshold": 128},
    "th16": {"bootThreshold": 16, "matureThreshold": 128},
}

FP_OFF = {"footprintScale": 0.0}
NO_JITTER = {"jitterFilter": 0.0, "jitterCell": 0.0}

QUANT_TAGS = ["qa006", "qa012", "qa036"]

VARIANTS_10 = []
for q_tag in QUANT_TAGS:
    base = [v for v in make_norm_variants(quant=QUANT_SWEEP[q_tag],
                                           base=PRESET_MINIMAL,
                                           quant_tag=q_tag)
            if v[0] == f"pos_norm__pos__{q_tag}"]
    for (name, overrides) in base:
        for t_tag, t_params in THRESH_SWEEP.items():
            VARIANTS_10.append((f"{name}__{t_tag}",
                                {**overrides, **t_params, **FP_OFF, **NO_JITTER}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[4],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_10,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

finalize_step(STEP, prev_winner="pos_norm__pos__qA024_qB036__th2",
              ref_step="05",
              ref_variant="pos_norm__pos__qA024_qB036__th2",
              ref_label="single-level best (step 05)")
_HEADLESS_SCRIPT_DONE = True

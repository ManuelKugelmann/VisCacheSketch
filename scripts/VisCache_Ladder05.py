"""
VisCache_Ladder05.py — Step 05: Maturity threshold sweep × footprint on/off.

Sweeps (bootThreshold, matureThreshold) ∈ {(8,128), (16,256), (32,512)}
× footprint ∈ {OFF, ON}, on the 2 norm-active B-side variants kept from step 4
onward (pos, dir_dist) at x1 / x4 SPP. Single-level cache; isolates the effect
of maturity thresholds and the footprint trust gate before the LOD cascade is
introduced at step 06.

Variant names carry the sweep as `{variant}__q{min|med|high}_fp{Off|On}` so the
plot's alpha gradient and legend can separate them.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder05.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_overviews, copy_summary_to_root, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID, \
    FOOTPRINT_OFF, FOOTPRINT_ON, SUBFRAME_2x2

res = int(os.environ.get("RES", "512"))

# Maturity threshold sweep (3 values).
QUALITY_SWEEP_05 = {
    "qmin":  {"bootThreshold":  8, "matureThreshold": 128},
    "qmed":  {"bootThreshold": 16, "matureThreshold": 256},
    "qhigh": {"bootThreshold": 32, "matureThreshold": 512},
}
# Footprint trust gate sweep (2 values).
FOOTPRINT_SWEEP_05 = {"fpOff": FOOTPRINT_OFF, "fpOn": FOOTPRINT_ON}

# Drop dir_dist1 after step 4 — only pos and dir_dist carry forward.
BASE_05 = [v for v in make_norm_variants(quant=QUANT_MID, base=PRESET_MINIMAL)
           if "__dir_dist1" not in v[0]]

# Fan out: 3 quality × 2 footprint × 2 base variants = 12 variants per SPP.
VARIANTS_05 = []
for q_tag, q_conf in QUALITY_SWEEP_05.items():
    for fp_tag, fp_conf in FOOTPRINT_SWEEP_05.items():
        for (name, overrides) in BASE_05:
            VARIANTS_05.append((f"{name}__{q_tag}_{fp_tag}",
                                {**overrides, **q_conf, **fp_conf}))

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
        step_name="05",
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_05,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

plot_overviews("05")
copy_summary_to_root("05")
_HEADLESS_SCRIPT_DONE = True

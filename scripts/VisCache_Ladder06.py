"""
VisCache_Ladder06.py — Step 06: Level cascade × maturity threshold sweep.

Same setup as step 05 (2 norm-active B-side variants pos / dir_dist, x1 / x4
SPP, footprint ON) but with the multi-level LOD cascade enabled. Sweeps
maturity thresholds to isolate the cascade's effect across quality regimes.

Variant names carry the quality tag as `{variant}__q{min|med|high}`.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder06.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_overviews, copy_summary_to_root, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, LEVELS_MULTI, \
    FOOTPRINT_ON, SUBFRAME_2x2

res = int(os.environ.get("RES", "512"))

# Maturity threshold sweep (3 values) — same list as step 05 so deltas line up.
QUALITY_SWEEP_06 = {
    "qmin":  {"bootThreshold":  8, "matureThreshold": 128},
    "qmed":  {"bootThreshold": 16, "matureThreshold": 256},
    "qhigh": {"bootThreshold": 32, "matureThreshold": 512},
}

# Drop dir_dist1 after step 4 — only pos and dir_dist carry forward.
BASE_06 = [v for v in make_norm_variants(base=PRESET_MINIMAL)
           if "__dir_dist1" not in v[0]]

# Fan out: 3 quality × 2 base variants = 6 variants per SPP.
VARIANTS_06 = []
for q_tag, q_conf in QUALITY_SWEEP_06.items():
    for (name, overrides) in BASE_06:
        VARIANTS_06.append((f"{name}__{q_tag}",
                            {**overrides, **q_conf}))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **FOOTPRINT_ON, **SUBFRAME_2x2,
                  "tableCapacity": 1 << 25}  # 32M entries (8× default) — cascade needs more slots

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
        step_name="06",
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_06,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

plot_overviews("06")
copy_summary_to_root("06")
_HEADLESS_SCRIPT_DONE = True

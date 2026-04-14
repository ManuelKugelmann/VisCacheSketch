"""
VisCache_Ladder07.py — Step 07: Multi-level cascade, higher quality thresholds.

Same as step 06 (PRESET_MINIMAL + RR_ADAPTIVE + LEVELS_MULTI + FOOTPRINT_ON) but
with QUALITY_DEFAULT (bootThreshold=64, varThreshold=0.20).
Compares against step 06 to isolate threshold sensitivity.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder07.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, get_scenes, \
    plot_rays_overview, make_norm_variants, PRESET_MINIMAL, RR_ADAPTIVE, \
    LEVELS_MULTI, QUALITY_DEFAULT, FOOTPRINT_ON

res = int(os.environ.get("RES", "512"))

STEP_OVERRIDES = {**RR_ADAPTIVE, **LEVELS_MULTI, **QUALITY_DEFAULT, **FOOTPRINT_ON}

VARIANTS_07 = make_norm_variants(base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(1, 0, 2)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="07",
        frame_configs=[(1, 0, 2, 1), (1, 0, 2, 16)],
        scene_file=scene_file,
        variants=VARIANTS_07,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=STEP_OVERRIDES,
    )

plot_rays_overview("07")
_HEADLESS_SCRIPT_DONE = True

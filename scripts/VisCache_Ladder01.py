"""
VisCache_Ladder01.py — Step 01: Single frame, all addressing variants × scenes.

1 warmup frame + 1 render frame. Tests hash table insert/lookup,
diagnostic pipeline, and all addressing modes across multiple scenes.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, VARIANTS_ALL, plot_rays_overview

SCENES = [
    "media/scenes/CornellBox_1AreaLight.pyscene",
    "media/scenes/CornellBox_1PointLight.pyscene",
    "media/scenes/CornellBox_3AreaLights.pyscene",
    "media/scenes/CornellBox_32PointLights.pyscene",
]

res = int(os.environ.get("RES", "512"))

all_stats = []
for scene_file in SCENES:
    stats = run_variants(
        step_name="01",
        frame_configs=[(1, 1, 1)],
        scene_file=scene_file,
        variants=VARIANTS_ALL,
        resX=res, resY=res,
        mogwai_globals=globals(),
    )
    all_stats.extend(stats)

plot_rays_overview("01", all_stats)
_HEADLESS_SCRIPT_DONE = True

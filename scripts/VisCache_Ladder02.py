"""
VisCache_Ladder02.py — Step 02: All addressing variants, adaptive RR.

PRESET_MINIMAL + RR_ADAPTIVE: 1 level, tiny boot, no features, adaptive pMin.
Isolates cache addressing accuracy with RR enabled.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder02.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    plot_overviews, copy_summary_to_root, PRESET_MINIMAL, RR_ADAPTIVE, FOOTPRINT_OFF, SUBFRAME_2x2

res = int(os.environ.get("RES", "512"))

QUANT_02 = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 5.0, "distB": 0.24}
VARIANTS_02 = _make_variants(normal_active=False, quant=QUANT_02, base=PRESET_MINIMAL) \
            + _make_variants(normal_active=True,  quant=QUANT_02, base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_variants(
        step_name="02",
        frame_configs=[(1, 0, 1, 1)],
        scene_file=scene_file,
        variants=VARIANTS_02,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **FOOTPRINT_OFF, **SUBFRAME_2x2},
    )

plot_overviews("02")
copy_summary_to_root("02")
_HEADLESS_SCRIPT_DONE = True

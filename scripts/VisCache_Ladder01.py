"""
VisCache_Ladder01.py — Step 01: All addressing variants, always-trace (pMin=1).

PRESET_MINIMAL + RR_OFF: 1 level, tiny boot, no features, every ray traced.
Isolates cache addressing accuracy from RR reduction.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    plot_rays_overview, PRESET_MINIMAL

res = int(os.environ.get("RES", "512"))

QUANT_01 = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 5.0, "distB": 0.24}
VARIANTS_01 = _make_variants(normal_active=False, quant=QUANT_01, base=PRESET_MINIMAL) \
            + _make_variants(normal_active=True,  quant=QUANT_01, base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_variants(
        step_name="01",
        frame_configs=[(1, 1, 1)],
        scene_file=scene_file,
        variants=VARIANTS_01,
        resX=res, resY=res,
        mogwai_globals=globals(),
    )

plot_rays_overview("01")
_HEADLESS_SCRIPT_DONE = True

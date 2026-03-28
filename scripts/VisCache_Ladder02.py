"""
VisCache_Ladder02.py — Step 02: Tuned quantization + adaptive RR.

PRESET_MINIMAL + RR_ADAPTIVE + QUANT_MID: tuned bin sizes, RR enabled.
Collapsed B-side (pos1, dir1_dist1) dropped after step 01. norm1 + norm.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder02.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    plot_rays_overview, PRESET_MINIMAL, RR_ADAPTIVE, QUANT_MID

res = int(os.environ.get("RES", "512"))

_all = _make_variants(normal_active=False, quant=QUANT_MID, base=PRESET_MINIMAL) \
     + _make_variants(normal_active=True,  quant=QUANT_MID, base=PRESET_MINIMAL)
VARIANTS_02 = [v for v in _all if "__pos1" not in v[0] and "__dir1_dist1" not in v[0]]

for scene_file in get_scenes():
    run_variants(
        step_name="02",
        frame_configs=[(1, 1, 1)],
        scene_file=scene_file,
        variants=VARIANTS_02,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides=RR_ADAPTIVE,
    )

plot_rays_overview("02")
_HEADLESS_SCRIPT_DONE = True

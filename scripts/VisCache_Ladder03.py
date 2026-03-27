"""
VisCache_Ladder03.py — Step 03: Normal comparison (pos_norm1 vs pos_norm).

Runs the 3 non-collapsed B-side variants (pos, dir_dist1, dir_dist) for
both norm1 (normal off) and norm (normal active), using QUANT_MID preset.
Skips pos1 and dir1_dist1 (collapsed baselines already covered in step 01).

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder03.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, run_baseline, BASE, get_scenes, \
    plot_rays_overview, _make_variants

res = int(os.environ.get("RES", "512"))

# Only non-collapsed B-side: pos, dir_dist1, dir_dist (indices 2, 3, 4 from _make_variants)
QUANT_03 = {"posA": 0.06, "normalA": 60.0, "posB": 0.18, "dirB": 8.0, "distB": 0.48}
_norm1_all = _make_variants(normal_active=False, quant=QUANT_03)
_norm_all  = _make_variants(normal_active=True,  quant=QUANT_03)
VARIANTS_03 = [v for v in _norm1_all if "__pos1" not in v[0] and "__dir1_dist1" not in v[0]] \
            + [v for v in _norm_all  if "__pos1" not in v[0] and "__dir1_dist1" not in v[0]]

for scene_file in get_scenes():
    run_baseline(
        step_name="00",
        frame_configs=[(1, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        extra_spp=[16],
        mogwai_globals=globals(),
    )

    run_variants(
        step_name="03",
        frame_configs=[(1, 1, 1), (1, 1, 16)],
        scene_file=scene_file,
        variants=VARIANTS_03,
        resX=res, resY=res,
        mogwai_globals=globals(),
    )

plot_rays_overview("03")
_HEADLESS_SCRIPT_DONE = True

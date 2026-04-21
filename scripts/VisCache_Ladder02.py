"""
VisCache_Ladder02.py — Step 02: Addressing sweep across norm-active variants.

PRESET_MINIMAL + RR_ADAPTIVE: 1 level, tiny boot, no features, adaptive pMin.
Isolates cache addressing accuracy with RR enabled. norm1 (normal collapsed)
variants are dropped — step 03+ uses only norm-active anyway, and the
fully-collapsed B variants (pos1, dir1_dist1) show their unsuitability most
clearly on multi-light scenes without norm1 clutter in the same plot.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder02.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    finalize_step, PRESET_MINIMAL, RR_ADAPTIVE, SUBFRAME_2x2

STEP = "02"
res = int(os.environ.get("RES", "512"))

# Non-collapsed qB (posB / dirB / distB) bumped coarser than QUANT_MID so each
# (A, B) cell aggregates more samples at low SPP — fewer unique entries, more
# writes per entry, lets the low-sample-count comparison settle. posA stays
# at the QUANT_MID default; only B-side is loosened.
QUANT_02 = {"posA": 0.06, "normalA": 60.0, "posB": 0.72, "dirB": 20.0, "distB": 1.0}
# All 5 B-side addressing combinations (pos1, dir1_dist1, pos, dir_dist1,
# dir_dist) under the single pos_norm A-side.
VARIANTS_02 = _make_variants(quant=QUANT_02, base=PRESET_MINIMAL)

for scene_file in get_scenes():
    run_variants(
        step_name=STEP,
        frame_configs=[(1, 0, 1, 1), (1, 0, 1, 4)],
        scene_file=scene_file,
        variants=VARIANTS_02,
        resX=res, resY=res,
        mogwai_globals=globals(),
        step_overrides={**RR_ADAPTIVE, **SUBFRAME_2x2},
    )

finalize_step(STEP)
_HEADLESS_SCRIPT_DONE = True

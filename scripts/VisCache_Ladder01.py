"""
VisCache_Ladder01.py — Cold-start tiling demo + subframe mitigation.

Single frame, cold cache. Within one frame all tiles dispatch in parallel:
cells inside a tile receive writes from many pixels but no pixel sees them
(query happens before its tile's commits land). Cells that *straddle* a tile
boundary look "trusted" because the neighbor tile already wrote — visible as
RR-saved rays clinging to tile borders.

Mitigations ablated OFF: footprint scale + warmup-write-only.
Variant: pos_norm1__pos1 only.

Subframe sweep: 1×1 (baseline, shows artifact), 2×2 (4 frames), 4×4 (16 frames).
N>1 disperses per-pixel cell writes across N² frames via Bayer interleaving,
breaking the tile-local first-writer-wins pattern.

Usage:
    Mogwai.exe --headless -s scripts/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    PRESET_MINIMAL, RR_ADAPTIVE, FOOTPRINT_OFF, \
    SUBFRAME_1x1, SUBFRAME_2x2, SUBFRAME_4x4

res = int(os.environ.get("RES", "512"))

# Coarse cells: makes tile boundaries large and obvious.
QUANT_01 = {"posA": 0.5, "normalA": 60.0, "posB": 1.0, "dirB": 5.0, "distB": 0.24}

# Pull just the first variant (pos_norm1__pos1).
BASE = _make_variants(normal_active=False, quant=QUANT_01, base=PRESET_MINIMAL)[:1]

STEP_OVERRIDES = {**RR_ADAPTIVE, **FOOTPRINT_OFF}

# Sweep (subframe, (warmupFirst, warmupRun, frames, spp)).
# frames=1 means "one logical frame" = one full Bayer cycle (N² rendered subframes).
# warmup slots [0, warmupFirst) write-only in the cycle's first subframe.
SWEEP = [
    (SUBFRAME_1x1, (0, 0, 1, 1)),   # baseline: full-frame, no warmup (shows artifact)
    (SUBFRAME_2x2, (0, 0, 1, 1)),   # 2x2, no warmup
    (SUBFRAME_2x2, (1, 0, 1, 1)),   # 2x2, +1-slot warmup
    (SUBFRAME_2x2, (2, 0, 1, 1)),   # 2x2, +half-cycle warmup
    (SUBFRAME_4x4, (0, 0, 1, 1)),   # 4x4, no warmup
    (SUBFRAME_4x4, (1, 0, 1, 1)),   # 4x4, +1-slot warmup
    (SUBFRAME_4x4, (8, 0, 1, 1)),   # 4x4, +half-cycle warmup
]

for scene_file in get_scenes():
    for i, (subframe, fc_tuple) in enumerate(SWEEP):
        variants = [(name, {**overrides, **subframe})
                    for (name, overrides) in BASE]
        run_variants(
            step_name="01",
            frame_configs=[fc_tuple],
            scene_file=scene_file,
            variants=variants,
            resX=res, resY=res,
            mogwai_globals=globals(),
            step_overrides=STEP_OVERRIDES,
            wipe_captures=(i == 0),
        )

_HEADLESS_SCRIPT_DONE = True

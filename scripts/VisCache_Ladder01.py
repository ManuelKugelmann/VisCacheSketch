"""
VisCache_Ladder01.py — Cold-start tiling demo + subframe mitigation.

Single frame, cold cache. Within one frame all tiles dispatch in parallel:
cells inside a tile receive writes from many pixels but no pixel sees them
(query happens before its tile's commits land). Cells that *straddle* a tile
boundary look "trusted" because the neighbor tile already wrote — visible as
RR-saved rays clinging to tile borders.

Mitigations ablated OFF: footprint scale + warmup-write-only.
Variant: pos_norm__pos1 only.

Subframe sweep: 1×1 (baseline, shows artifact), 2×2 (4 frames), 4×4 (16 frames).
N>1 disperses per-pixel cell writes across N² frames via Bayer interleaving,
breaking the tile-local first-writer-wins pattern.

Usage:
    Mogwai.exe --headless -s scripts/VisCache_Ladder01.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import run_variants, _make_variants, get_scenes, \
    finalize_step, PRESET_MINIMAL, RR_ADAPTIVE, FOOTPRINT_OFF, \
    SUBFRAME_1x1, SUBFRAME_2x2, SUBFRAME_4x4

STEP = "01"
res = int(os.environ.get("RES", "512"))

# Coarser cells than step 02+'s QUANT_MID (2× posA / posB / distB) — bigger
# cells aggregate more parallel writes per dispatch, making the tile-boundary
# first-writer-wins artefact more visible. Subframe sweep below ablates the
# mitigation that disperses those writes across N² frames.
QUANT_01 = {"posA": 0.12, "normalA": 60.0, "posB": 0.36, "dirB": 8.0, "distB": 0.96}

# Pull just the first variant (pos_norm__pos1).
BASE = _make_variants(quant=QUANT_01, base=PRESET_MINIMAL)[:1]

# Stock RR_ADAPTIVE + FOOTPRINT_OFF — lets RR actually bite so the subframe
# mitigation effect is visible. The subval variants below isolate the
# 100%-trace plumbing baseline, so main doesn't need inflated thresholds
# to avoid cold-start blob outliers.
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

# Subframe plumbing validation: pMin=1.0 + huge thresholds force every ray to
# trace regardless of cache state, isolating the Bayer dispatch + AccumulatePass
# subframe skip logic. Any non-zero err_blob here indicates a bug in the
# plumbing rather than a RR-skip artifact. VisCache must stay in the graph
# because the PathTracer subframe gate is keyed on VisCache presence
# (PathTracer.cpp: `mVisCacheAvailable` gates `vhfSubframeN`).
SUBVAL_OVERRIDES = {**STEP_OVERRIDES, "pMin": 2.0,
                    "enableVisCacheAdaptivePMin": False,
                    "bootThreshold": 1 << 20, "matureThreshold": 1 << 20}
SUBVAL_SWEEP = [
    (SUBFRAME_1x1, (0, 0, 1, 1)),
    (SUBFRAME_2x2, (0, 0, 1, 1)),
    (SUBFRAME_4x4, (0, 0, 1, 1)),
]

for scene_file in get_scenes():
    for i, (subframe, fc_tuple) in enumerate(SWEEP):
        variants = [(name, {**overrides, **subframe})
                    for (name, overrides) in BASE]
        run_variants(
            step_name=STEP,
            frame_configs=[fc_tuple],
            scene_file=scene_file,
            variants=variants,
            resX=res, resY=res,
            mogwai_globals=globals(),
            step_overrides=STEP_OVERRIDES,
            wipe_captures=(i == 0),
        )
    for (subframe, fc_tuple) in SUBVAL_SWEEP:
        variants = [(f"{name}_subval", {**overrides, **subframe})
                    for (name, overrides) in BASE]
        run_variants(
            step_name=STEP,
            frame_configs=[fc_tuple],
            scene_file=scene_file,
            variants=variants,
            resX=res, resY=res,
            mogwai_globals=globals(),
            step_overrides=SUBVAL_OVERRIDES,
            wipe_captures=False,
        )

finalize_step(STEP)
_HEADLESS_SCRIPT_DONE = True

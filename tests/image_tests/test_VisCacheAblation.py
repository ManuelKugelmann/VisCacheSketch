IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["viscache", "ablation"],
    "timeout": 900
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.VisCacheAblation import (
    VisCacheAblation_GI_Full,
    VisCacheAblation_GI_NoLOD,
    VisCacheAblation_GI_NoVarGate,
    VisCacheAblation_GI_NoWarp,
    VisCacheAblation_GI_NoDecay,
    VisCacheAblation_GI_NoEvict,
    VisCacheAblation_DI_NoDecay,
    VisCacheAblation_PT_NoDecay,
)
from falcor import *

# ===================================================================
# GI ablation matrix (A–E): disable one toggle at a time
# ===================================================================
m.addGraph(VisCacheAblation_GI_Full)
m.loadScene('Arcade/Arcade.pyscene')

# Baseline: all ablation toggles ON (VisCache Full)
render_frames(m, 'gi_full', frames=[1, 16, 64])

# A: No distance-gated LOD — all queries go to finest level
m.removeGraph(VisCacheAblation_GI_Full)
m.addGraph(VisCacheAblation_GI_NoLOD)
render_frames(m, 'gi_no_lod', frames=[1, 16, 64])

# B: No variance gate — always write all LOD levels
m.removeGraph(VisCacheAblation_GI_NoLOD)
m.addGraph(VisCacheAblation_GI_NoVarGate)
render_frames(m, 'gi_no_vargate', frames=[1, 16, 64])

# C: No warp reduction — no WaveMatch coalescing (perf-only)
m.removeGraph(VisCacheAblation_GI_NoVarGate)
m.addGraph(VisCacheAblation_GI_NoWarp)
render_frames(m, 'gi_no_warp', frames=[1, 16, 64])

# D: No decay — stale entries never evicted
m.removeGraph(VisCacheAblation_GI_NoWarp)
m.addGraph(VisCacheAblation_GI_NoDecay)
render_frames(m, 'gi_no_decay', frames=[1, 16, 64])

# E: No pressure eviction — hash collisions not resolved
m.removeGraph(VisCacheAblation_GI_NoDecay)
m.addGraph(VisCacheAblation_GI_NoEvict)
render_frames(m, 'gi_no_evict', frames=[1, 16, 64])

# ===================================================================
# DI/PT spot-checks: decay ablation (most impactful across passes)
# ===================================================================
m.removeGraph(VisCacheAblation_GI_NoEvict)
m.addGraph(VisCacheAblation_DI_NoDecay)
render_frames(m, 'di_no_decay', frames=[1, 16, 64])

m.removeGraph(VisCacheAblation_DI_NoDecay)
m.addGraph(VisCacheAblation_PT_NoDecay)
render_frames(m, 'pt_no_decay', frames=[1, 16, 64])

exit()

IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRPT import (ReSTIRPT_Vanilla, ReSTIRPT_CVRRRRevalidation,
                              ReSTIRPT_VisCacheRevalidation, ReSTIRPT_VisCacheLightSelection,
                              ReSTIRPT_VisCacheFull,
                              ReSTIRPT1_Vanilla, ReSTIRPT1_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR PT — vanilla baseline (multi-bounce, no VisCache)
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRPT_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — local CV+RRR (reservoir-local mu, no hash table)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_Vanilla)
m.addGraph(ReSTIRPT_CVRRRRevalidation)
render_frames(m, 'cvrrr_revalidation', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — VisCache CV+RRR revalidation (S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_CVRRRRevalidation)
m.addGraph(ReSTIRPT_VisCacheRevalidation)
render_frames(m, 'viscache_revalidation', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — VisCache light pre-selection only (S11.1, no S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_VisCacheRevalidation)
m.addGraph(ReSTIRPT_VisCacheLightSelection)
render_frames(m, 'viscache_light_selection', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — VisCache full (S11.1 + S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_VisCacheLightSelection)
m.addGraph(ReSTIRPT_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — subsumes ReSTIR GI tests.
# Single-bounce vanilla + full VisCache to verify GI-equivalent path.
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_VisCacheFull)
m.addGraph(ReSTIRPT1_Vanilla)
render_frames(m, 'pt1_vanilla', frames=[1, 16, 64])

m.removeGraph(ReSTIRPT1_Vanilla)
m.addGraph(ReSTIRPT1_VisCacheFull)
render_frames(m, 'pt1_viscache_full', frames=[1, 16, 64])

exit()

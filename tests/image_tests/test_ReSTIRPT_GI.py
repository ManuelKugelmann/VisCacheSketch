IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRPT import (ReSTIRPT1_Vanilla, ReSTIRPT1_CVRRRRevalidation,
                              ReSTIRPT1_VisCacheRevalidation, ReSTIRPT1_VisCacheLightSelection,
                              ReSTIRPT1_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — vanilla baseline
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRPT1_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — local CV+RRR (reservoir-local mu, no hash table)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_Vanilla)
m.addGraph(ReSTIRPT1_CVRRRRevalidation)
render_frames(m, 'cvrrr_revalidation', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — VisCache CV+RRR revalidation
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_CVRRRRevalidation)
m.addGraph(ReSTIRPT1_VisCacheRevalidation)
render_frames(m, 'viscache_revalidation', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — VisCache light pre-selection only
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_VisCacheRevalidation)
m.addGraph(ReSTIRPT1_VisCacheLightSelection)
render_frames(m, 'viscache_light_selection', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxSurfaceBounces=1 — VisCache full (revalidation + light selection)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_VisCacheLightSelection)
m.addGraph(ReSTIRPT1_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

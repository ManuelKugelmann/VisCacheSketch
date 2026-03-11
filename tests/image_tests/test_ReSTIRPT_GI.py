IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRPT import (ReSTIRPT1_Vanilla, ReSTIRPT1_CVRRRLocal,
                              ReSTIRPT1_VisCacheReval, ReSTIRPT1_VisCacheLightSel,
                              ReSTIRPT1_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR PT maxBounces=1 — vanilla baseline
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRPT1_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxBounces=1 — local CV+RRR (reservoir-local mu, no hash table)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_Vanilla)
m.addGraph(ReSTIRPT1_CVRRRLocal)
render_frames(m, 'cvrrr_local', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxBounces=1 — VisCache CV+RRR revalidation
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_CVRRRLocal)
m.addGraph(ReSTIRPT1_VisCacheReval)
render_frames(m, 'viscache_reval', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxBounces=1 — VisCache light pre-selection only
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_VisCacheReval)
m.addGraph(ReSTIRPT1_VisCacheLightSel)
render_frames(m, 'viscache_lightsel', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT maxBounces=1 — VisCache full (revalidation + light selection)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT1_VisCacheLightSel)
m.addGraph(ReSTIRPT1_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRDI import (ReSTIRDI_Vanilla, ReSTIRDI_VisCacheReval,
                              ReSTIRDI_VisCacheLightSel, ReSTIRDI_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR DI — vanilla baseline (no VisCache)
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRDI_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR DI — VisCache CV+RRR shadow ray gating only (S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRDI_Vanilla)
m.addGraph(ReSTIRDI_VisCacheReval)
render_frames(m, 'viscache_reval', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR DI — VisCache light pre-selection only (S11.1, no S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRDI_VisCacheReval)
m.addGraph(ReSTIRDI_VisCacheLightSel)
render_frames(m, 'viscache_lightsel', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR DI — VisCache revalidation + light selection (S11.1 + S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRDI_VisCacheLightSel)
m.addGraph(ReSTIRDI_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

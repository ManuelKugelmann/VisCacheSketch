IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRGI import (ReSTIRGI_Vanilla, ReSTIRGI_CVRRRLocal,
                              ReSTIRGI_VisCacheReval, ReSTIRGI_VisCacheLightSel,
                              ReSTIRGI_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR GI — vanilla baseline (unconditional shadow rays)
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRGI_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR GI — local CV+RRR (reservoir-local mu, no hash table)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRGI_Vanilla)
m.addGraph(ReSTIRGI_CVRRRLocal)
render_frames(m, 'cvrrr_local', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR GI — VisCache CV+RRR revalidation (S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRGI_CVRRRLocal)
m.addGraph(ReSTIRGI_VisCacheReval)
render_frames(m, 'viscache_reval', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR GI — VisCache light pre-selection only (S11.1, no S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRGI_VisCacheReval)
m.addGraph(ReSTIRGI_VisCacheLightSel)
render_frames(m, 'viscache_lightsel', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR GI — VisCache full (S11.1 + S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRGI_VisCacheLightSel)
m.addGraph(ReSTIRGI_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

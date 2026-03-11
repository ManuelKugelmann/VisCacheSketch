IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRPT import (ReSTIRPT_GI_Vanilla, ReSTIRPT_GI_CVRRRLocal,
                              ReSTIRPT_GI_VisCacheReval, ReSTIRPT_GI_VisCacheLightSel,
                              ReSTIRPT_GI_VisCacheFull)
from falcor import *

# ---------------------------------------------------------------------------
# ReSTIR PT (single-bounce GI) — vanilla baseline (unconditional shadow rays)
# ---------------------------------------------------------------------------
m.addGraph(ReSTIRPT_GI_Vanilla)
m.loadScene('Arcade/Arcade.pyscene')
render_frames(m, 'vanilla', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT (single-bounce GI) — local CV+RRR (reservoir-local mu, no hash table)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_GI_Vanilla)
m.addGraph(ReSTIRPT_GI_CVRRRLocal)
render_frames(m, 'cvrrr_local', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT (single-bounce GI) — VisCache CV+RRR revalidation (S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_GI_CVRRRLocal)
m.addGraph(ReSTIRPT_GI_VisCacheReval)
render_frames(m, 'viscache_reval', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT (single-bounce GI) — VisCache light pre-selection only (S11.1, no S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_GI_VisCacheReval)
m.addGraph(ReSTIRPT_GI_VisCacheLightSel)
render_frames(m, 'viscache_lightsel', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT (single-bounce GI) — VisCache full (S11.1 + S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_GI_VisCacheLightSel)
m.addGraph(ReSTIRPT_GI_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

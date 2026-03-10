IMAGE_TEST = {
    "device_types": ["d3d12", "vulkan"],
    "tags": ["restir", "viscache"],
    "timeout": 600
}

import sys
sys.path.append('..')
from helpers import render_frames
from graphs.ReSTIRPT import (ReSTIRPT_Vanilla, ReSTIRPT_CVRRRLocal,
                              ReSTIRPT_VisCacheReval, ReSTIRPT_VisCacheFull)
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
m.addGraph(ReSTIRPT_CVRRRLocal)
render_frames(m, 'cvrrr_local', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — VisCache CV+RRR revalidation (S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_CVRRRLocal)
m.addGraph(ReSTIRPT_VisCacheReval)
render_frames(m, 'viscache_reval', frames=[1, 16, 64])

# ---------------------------------------------------------------------------
# ReSTIR PT — VisCache full (S11.1 + S11.3)
# ---------------------------------------------------------------------------
m.removeGraph(ReSTIRPT_VisCacheReval)
m.addGraph(ReSTIRPT_VisCacheFull)
render_frames(m, 'viscache_full', frames=[1, 16, 64])

exit()

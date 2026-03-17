"""
MinimalPathTracer_Graph.py  —  Simple Mogwai render graph using Falcor's MinimalPathTracer.

VBuffer → MinimalPathTracer → AccumulatePass → ToneMapper.
Optionally adds VisCache for shadow gating (§11.2) when viscache=True.

Good for quick visual checks, scene validation, and learning Falcor basics.

Usage:
    Mogwai.exe --script scripts/MinimalPathTracer_Graph.py --scene CornellBox.pyscene
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

# Import Falcor builtins so this module works both when exec'd by Mogwai
# (where globals already has them) and when imported by VisCache wrappers.
try:
    from falcor import *
except ImportError:
    pass


def render_graph_MinimalPathTracer(viscache=False):
    """Build a MinimalPathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
    """
    name = "MinimalPathTracer_VisCache" if viscache else "MinimalPathTracer"
    g = RenderGraph(name)

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc = createPass("VisCachePass", VISCACHE_DEFAULTS)
        g.addPass(vc, "VisCache")

    # Minimal path tracer (Falcor built-in)
    pt = createPass("MinimalPathTracer", {
        "maxBounces": 3,
    })
    g.addPass(pt, "MinimalPathTracer")

    # Accumulate samples over frames for progressive rendering
    accum = createPass("AccumulatePass", {
        "enabled":       True,
        "precisionMode": "Single",
    })
    g.addPass(accum, "AccumulatePass")

    # Tone mapper
    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    # Edges
    g.addEdge("VBufferRT.vbuffer",        "MinimalPathTracer.vbuffer")
    g.addEdge("VBufferRT.viewW",          "MinimalPathTracer.viewW")
    g.addEdge("MinimalPathTracer.color",  "AccumulatePass.input")
    g.addEdge("AccumulatePass.output",    "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_MinimalPathTracer())

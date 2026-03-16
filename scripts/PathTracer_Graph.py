"""
PathTracer_Graph.py  —  Vanilla Falcor PathTracer render graph.

Full-featured path tracer with accumulation and tone mapping.
VBuffer → PathTracer → AccumulatePass → ToneMapper.
Optionally adds VisCache for shadow gating (§11.2) when viscache=True.

Usage:
    Mogwai.exe --script scripts/PathTracer_Graph.py --scene VeachAjar.pyscene
"""

from viscache_defaults import VISCACHE_DEFAULTS


def render_graph_PathTracer(viscache=False):
    """Build a PathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
    """
    name = "PathTracer_VisCache" if viscache else "PathTracer"
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

    # Falcor PathTracer (full-featured: NEE, MIS, Russian roulette, volumes)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    1,
        "maxSurfaceBounces":  3,
        "colorFormat":        "LogLuvHDR",
    })
    g.addPass(pt, "PathTracer")

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
    g.addEdge("VBufferRT.vbuffer",   "PathTracer.vbuffer")
    g.addEdge("VBufferRT.viewW",     "PathTracer.viewW")
    g.addEdge("PathTracer.color",    "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    return g


# ---------------------------------------------------------------------------
# Load graph
# ---------------------------------------------------------------------------
m.addGraph(render_graph_PathTracer())

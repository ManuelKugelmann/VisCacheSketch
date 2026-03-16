"""
MinimalPathTracer_Graph.py  —  Simple Mogwai render graph using Falcor's MinimalPathTracer.

A lightweight alternative to the full VisCache pipeline. No VisCache, no ReSTIR PT,
no denoiser — just VBuffer → MinimalPathTracer → AccumulatePass → ToneMapper.

Good for quick visual checks, scene validation, and learning Falcor basics.

Usage:
    Mogwai.exe --script scripts/MinimalPathTracer_Graph.py --scene CornellBox.pyscene
"""


def render_graph_MinimalPathTracer():
    """Build a simple MinimalPathTracer render graph."""
    g = RenderGraph("MinimalPathTracer")

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

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
# Load graph
# ---------------------------------------------------------------------------
m.addGraph(render_graph_MinimalPathTracer())

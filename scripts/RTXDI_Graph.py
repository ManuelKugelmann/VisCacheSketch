"""
RTXDI_Graph.py  —  RTXDI (ReSTIR DI) direct lighting render graph.

Direct illumination only via spatiotemporal resampling.
No VisCache, no path tracing — just GBuffer → RTXDIPass → ToneMapper.

Usage:
    Mogwai.exe --script scripts/RTXDI_Graph.py --scene VeachAjar.pyscene
"""


def render_graph_RTXDI():
    """Build an RTXDI (ReSTIR DI) render graph."""
    g = RenderGraph("RTXDI")

    # G-Buffer
    gbuf = createPass("GBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          "Back",
    })
    g.addPass(gbuf, "GBufferRT")

    # RTXDI — direct illumination with spatiotemporal resampling
    rtxdi = createPass("RTXDIPass", {
        "options": {
            "mode":                       "SpatiotemporalResampling",
            "localLightCandidateCount":    8,
            "infiniteLightCandidateCount": 1,
        },
    })
    g.addPass(rtxdi, "RTXDIPass")

    # Tone mapper
    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    # Edges
    g.addEdge("GBufferRT.vbuffer", "RTXDIPass.vbuffer")
    g.addEdge("GBufferRT.mvec",    "RTXDIPass.mvec")
    g.addEdge("RTXDIPass.color",   "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("RTXDIPass.color")   # linear HDR for analysis

    return g


# ---------------------------------------------------------------------------
# Load graph
# ---------------------------------------------------------------------------
m.addGraph(render_graph_RTXDI())

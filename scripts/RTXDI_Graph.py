"""
RTXDI_Graph.py  —  RTXDI (ReSTIR DI) direct lighting render graph.

Direct illumination only via spatiotemporal resampling.
GBuffer → RTXDIPass → ToneMapper.
Optionally adds VisCache for visibility-weighted light selection (§11.1) when viscache=True.

Usage:
    Mogwai.exe --script scripts/RTXDI_Graph.py --scene VeachAjar.pyscene
"""

# Shared VisCache pass parameters (same defaults as VisCache_Graph.py)
_VISCACHE_DEFAULTS = {
    "tableCapacity":   1 << 22,
    "bootThreshold":   32,
    "varThreshold":    0.10,
    "pMin":            0.05,
    "fireflyBudget":   0.05,
    "decayPeriod":     300,
    "decayPeriodMax":  600,
    "numLevels":       3,
    "cellCoarse":      10.0,
    "cellFine":        0.16,
    "enableVisCacheRevalidation":   True,
    "enableVisCacheLightSelection": True,
    "enableVisCacheWarpReduction":  True,
    "enableVisCacheVarianceGate":   True,
    "enableVisCacheDecay":          True,
    "enableVisCachePressureEvict":  True,
}


def render_graph_RTXDI(viscache=False):
    """Build an RTXDI (ReSTIR DI) render graph.

    Args:
        viscache: If True, add VisCache pass for light selection (§11.1).
    """
    name = "RTXDI_VisCache" if viscache else "RTXDI"
    g = RenderGraph(name)

    # G-Buffer
    gbuf = createPass("GBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          "Back",
    })
    g.addPass(gbuf, "GBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc = createPass("VisCachePass", _VISCACHE_DEFAULTS)
        g.addPass(vc, "VisCache")

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

"""
RTXDI_Graph.py  —  RTXDI (ReSTIR DI) direct lighting render graph.

Direct illumination only via spatiotemporal resampling.
GBuffer → RTXDIPass → ToneMapper.
Optionally adds VisCache for visibility-weighted light selection (§11.1) when viscache=True.

Usage:
    Mogwai.exe --script scripts/RTXDI_Graph.py --scene VeachAjar.pyscene
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

try:
    from falcor import *
except ImportError:
    pass


def render_graph_RTXDI(viscache=False, biasCorrection="Basic"):
    """Build an RTXDI (ReSTIR DI) render graph.

    Args:
        viscache: If True, add VisCache pass for light selection (§11.1).
        biasCorrection: RTXDI's BiasCorrection mode — one of "Off", "Basic"
                        (default; uses stored V on reuse, biased), "Pairwise",
                        "RayTraced" (re-traces V during MIS normalization,
                        unbiased). Default "Basic" matches RTXDI's own default
                        and matches what our restir_2d/3d implementation does.
    """
    name = "RTXDI_VisCache" if viscache else "RTXDI"
    if biasCorrection != "Basic":
        name += f"_{biasCorrection}"
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
        vc = createPass("VisCachePass", VISCACHE_DEFAULTS)
        g.addPass(vc, "VisCache")

    # RTXDI — direct illumination with spatiotemporal resampling
    rtxdi = createPass("RTXDIPass", {
        "options": {
            "mode":                       "SpatiotemporalResampling",
            "localLightCandidateCount":    8,
            "infiniteLightCandidateCount": 1,
            "biasCorrection":             biasCorrection,
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
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_RTXDI())

"""
ReSTIRPT_Graph.py  —  Vanilla ReSTIR PT render graph (no VisCache).

GBuffer → RTXDIPass (direct) → ReSTIRPTPass (indirect) → ToneMapper.
Same pipeline structure as VisCache_Graph.py but without the VisCache pass.

Usage:
    Mogwai.exe --script scripts/ReSTIRPT_Graph.py --scene VeachAjar.pyscene
"""


def render_graph_ReSTIRPT():
    """Build a vanilla ReSTIR PT render graph (no VisCache)."""
    g = RenderGraph("ReSTIRPT")

    # G-Buffer
    gbuf = createPass("GBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          "Back",
    })
    g.addPass(gbuf, "GBufferRT")

    # RTXDI — direct lighting
    rtxdi = createPass("RTXDIPass", {
        "options": {
            "mode":                       "NoResampling",
            "localLightCandidateCount":    8,
            "infiniteLightCandidateCount": 1,
        },
    })
    g.addPass(rtxdi, "RTXDIPass")

    # ReSTIR PT — indirect lighting via path reuse
    restirpt = createPass("ReSTIRPTPass", {
        "maxSurfaceBounces":       1,
        "spatialNeighborCount":    5,
        "spatialReuseRadius":      30,
        "candidateSamples":        1,
    })
    g.addPass(restirpt, "ReSTIRPTPass")

    # NRD denoiser (optional)
    _have_nrd = False
    try:
        nrd = createPass("NRDPass", {
            "method":          "RelaxDiffuseSpecular",
            "worldSpaceMotion": True,
        })
        g.addPass(nrd, "NRDPass")
        _have_nrd = True
    except Exception:
        print("[ReSTIRPT] WARNING: NRDPass plugin not available — outputting raw noisy radiance.")

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

    g.addEdge("RTXDIPass.color",   "ReSTIRPTPass.directLighting")
    g.addEdge("GBufferRT.vbuffer", "ReSTIRPTPass.vbuffer")
    g.addEdge("GBufferRT.mvec",    "ReSTIRPTPass.motionVectors")

    if _have_nrd:
        g.addEdge("ReSTIRPTPass.nrdDiffuseRadianceHitDist",
                  "NRDPass.diffuseRadianceHitDist")
        g.addEdge("ReSTIRPTPass.nrdSpecularRadianceHitDist",
                  "NRDPass.specularRadianceHitDist")
        g.addEdge("GBufferRT.linearZ",                  "NRDPass.viewZ")
        g.addEdge("GBufferRT.normWRoughnessMaterialID", "NRDPass.normWRoughnessMaterialID")
        g.addEdge("GBufferRT.mvec",                     "NRDPass.mvec")
        g.addEdge("NRDPass.filteredDiffuseRadianceHitDist", "ToneMapper.src")
    else:
        g.addEdge("ReSTIRPTPass.color", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPTPass.color")
    g.markOutput("ReSTIRPTPass.debug")

    return g


# ---------------------------------------------------------------------------
# Load graph
# ---------------------------------------------------------------------------
m.addGraph(render_graph_ReSTIRPT())

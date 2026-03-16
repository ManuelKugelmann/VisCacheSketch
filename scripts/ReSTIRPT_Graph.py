"""
ReSTIRPT_Graph.py  —  ReSTIR PT render graph, with optional VisCache.

Vanilla:   GBuffer → RTXDIPass (direct) → ReSTIRPTPass (indirect) → NRD → ToneMapper
VisCache:  GBuffer → VisCache → RTXDIPass → PathTracer (shadow gating §11.2)
                                           → ReSTIRPTPass → NRD → ToneMapper

Usage:
    Mogwai.exe --script scripts/ReSTIRPT_Graph.py --scene VeachAjar.pyscene
"""

# ---------------------------------------------------------------------------
# VisCache defaults & ablation presets (paper §15)
# ---------------------------------------------------------------------------

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

ABLATIONS = {
    "full":         {},                                          # All features on — paper result
    "minus_var":    {"enableVisCacheVarianceGate": False},       # -B: no variance-gated write depth
    "minus_warp":   {"enableVisCacheWarpReduction": False},      # -C: no warp reduction (per-lane atomics)
    "minus_decay":  {"enableVisCacheDecay": False},              # -D: no inline CAS decay
    "minus_evict":  {"enableVisCachePressureEvict": False},      # -E: no pressure-scaled eviction
    "single_level": {"numLevels": 1},                            # Single-level (N=1) vs. multilevel
}


def render_graph_ReSTIRPT(viscache=False, ablation=None):
    """Build a ReSTIR PT render graph.

    Args:
        viscache: If True, add VisCache pass + PathTracer for shadow gating.
        ablation: Dict of VisCachePass overrides, or a key into ABLATIONS.
                  Only used when viscache=True.
    """
    if ablation is None:
        ablation = {}
    elif isinstance(ablation, str):
        ablation = ABLATIONS[ablation]

    name = "ReSTIRPT_VisCache" if viscache else "ReSTIRPT"
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
        vc_params = dict(VISCACHE_DEFAULTS)
        vc_params.update(ablation)
        vc = createPass("VisCachePass", vc_params)
        g.addPass(vc, "VisCache")

    # RTXDI — direct lighting (visibility-weighted selection when VisCache present, §11.1)
    rtxdi = createPass("RTXDIPass", {
        "options": {
            "mode":                       "NoResampling",
            "localLightCandidateCount":    8,
            "infiniteLightCandidateCount": 1,
        },
    })
    g.addPass(rtxdi, "RTXDIPass")

    # PathTracer for shadow gating (only with VisCache, §11.2)
    if viscache:
        pt = createPass("PathTracer", {
            "samplesPerPixel":    1,
            "maxSurfaceBounces":  3,
            "colorFormat":        "LogLuvHDR",
        })
        g.addPass(pt, "PathTracer")

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

    # -----------------------------------------------------------------------
    # Edges
    # -----------------------------------------------------------------------
    # GBuffer → RTXDIPass (direct illumination)
    g.addEdge("GBufferRT.vbuffer", "RTXDIPass.vbuffer")
    g.addEdge("GBufferRT.mvec",    "RTXDIPass.mvec")

    # PathTracer shadow gating (VisCache only, §11.2)
    if viscache:
        g.addEdge("GBufferRT.vbuffer", "PathTracer.vbuffer")
        g.addEdge("GBufferRT.viewW",   "PathTracer.viewW")

    # RTXDI direct lighting → ReSTIR PT
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
    g.markOutput("ReSTIRPTPass.color")   # raw noisy radiance (linear HDR) for MSE/FLIP
    g.markOutput("ReSTIRPTPass.debug")   # optional per-pixel debug visualisation

    return g


# ---------------------------------------------------------------------------
# Load graph
# ---------------------------------------------------------------------------
m.addGraph(render_graph_ReSTIRPT())

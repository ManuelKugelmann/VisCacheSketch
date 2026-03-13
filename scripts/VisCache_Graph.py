"""
VisCache_Graph.py  —  Mogwai render graph for VisCache (Visibility Cache)
Run from Mogwai: File > Load Script, or pass as --script argument.

Usage:
    Mogwai.exe --script scripts/VisCache_Graph.py --scene BistroInterior.pyscene

Ablation configs are at the bottom — uncomment to switch.
"""

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def set_ablation(visCache, cfg):
    """Apply an ablation configuration dict to the VisCache pass."""
    for k, v in cfg.items():
        setattr(visCache, k, v)


# ---------------------------------------------------------------------------
# Ablation config presets (paper §15)
# Uncomment exactly one before loading.
# ---------------------------------------------------------------------------

ABLATION_FULL = {}  # All features on — paper result

ABLATION_MINUS_B = {   # Disable variance-gated write depth
    "enableVisCacheVarianceGate": False,
}
ABLATION_MINUS_C = {   # Disable warp reduction (per-lane atomics)
    "enableVisCacheWarpReduction": False,
}
ABLATION_MINUS_D = {   # Disable inline CAS decay
    "enableVisCacheDecay": False,
}
ABLATION_MINUS_E = {   # Disable pressure-scaled eviction
    "enableVisCachePressureEvict": False,
}
ABLATION_SINGLE_LEVEL = {   # Single-level (N=1) vs. multilevel comparison
    "numLevels": 1,
}

ACTIVE_ABLATION = ABLATION_FULL   # <-- CHANGE THIS LINE


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def render_graph_VisCache():
    g = RenderGraph("VisCache")

    # G-Buffer
    gbuf = createPass("GBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          "Back",
    })
    g.addPass(gbuf, "GBufferRT")

    # Visibility Cache
    # Owns the hash table; exposes it via InternalDictionary.
    visCache = createPass("VisCachePass", {
        "tableCapacity":   1 << 22,   # 4M entries = 32 MB
        "bootThreshold":   32,
        "varThreshold":    0.10,
        "pMin":            0.05,
        "fireflyBudget":   0.05,
        "decayPeriod":     300,       # auto-tuned by PI controller
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
    })
    set_ablation(visCache, ACTIVE_ABLATION)
    g.addPass(visCache, "VisCache")

    # RTXDI — direct lighting with optional visibility-weighted selection (§11.1)
    # Mode enum: NoResampling | SpatialResampling | TemporalResampling | SpatiotemporalResampling
    rtxdi = createPass("RTXDIPass", {
        "options": {
            "mode":                       "NoResampling",
            "localLightCandidateCount":    8,
            "infiniteLightCandidateCount": 1,
        },
        # VisCache integration is automatic via InternalDictionary (§11.1)
    })
    g.addPass(rtxdi, "RTXDIPass")

    # Path tracer with CV+RRR shadow gating on direct hits (§11.2)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    1,
        "maxSurfaceBounces":  3,
        "colorFormat":        "LogLuvHDR",
        # VisCache integration is automatic via InternalDictionary (§11.2)
    })
    g.addPass(pt, "PathTracer")

    # ReSTIR PT maxBounces=1 with CV+RRR revalidation (§9.3 / §10)
    # Single-bounce: equivalent to ReSTIR GI but with hybrid shift for specular.
    # Source: DQLin/ReSTIR_PT ported to Falcor 8.0
    restirpt = createPass("ReSTIRPTPass", {
        "maxBounces":              1,
        "numSpatialNeighbors":     5,
        "spatialRadius":           30,
        "numInitialSamples":       1,
        "useVisCacheRevalidation":    True,
        "contribThreshold":        0.01,
        "revalidationPMin":        0.05,
    })
    g.addPass(restirpt, "ReSTIRPTPass")

    # NRD denoiser
    nrd = createPass("NRDPass", {
        "method":          "RelaxDiffuseSpecular",
        "worldSpaceMotion": True,
    })
    g.addPass(nrd, "NRDPass")

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
    # GBuffer → PathTracer (shadow gating via VisCache dictionary, §11.2)
    g.addEdge("GBufferRT.vbuffer",                   "PathTracer.vbuffer")
    g.addEdge("GBufferRT.viewW",                     "PathTracer.viewW")

    # GBuffer → RTXDIPass (direct illumination, §11.1)
    g.addEdge("GBufferRT.vbuffer",                   "RTXDIPass.vbuffer")
    g.addEdge("GBufferRT.mvec",                      "RTXDIPass.mvec")

    # RTXDIPass direct lighting → ReSTIR PT as input; PathTracer color as fallback
    g.addEdge("RTXDIPass.color",                     "ReSTIRPTPass.directLighting")
    g.addEdge("GBufferRT.vbuffer",                   "ReSTIRPTPass.vbuffer")
    g.addEdge("GBufferRT.mvec",                      "ReSTIRPTPass.motionVectors")

    # ReSTIR PT NRD outputs → NRD denoiser
    g.addEdge("ReSTIRPTPass.nrdDiffuseRadianceHitDist",
              "NRDPass.diffuseRadianceHitDist")
    g.addEdge("ReSTIRPTPass.nrdSpecularRadianceHitDist",
              "NRDPass.specularRadianceHitDist")
    g.addEdge("GBufferRT.linearZ",                   "NRDPass.viewZ")
    g.addEdge("GBufferRT.normWRoughnessMaterialID",  "NRDPass.normWRoughnessMaterialID")
    g.addEdge("GBufferRT.mvec",                      "NRDPass.mvec")

    # NRD → ToneMapper
    g.addEdge("NRDPass.filteredDiffuseRadianceHitDist",
              "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    # Secondary outputs for analysis
    g.markOutput("ReSTIRPTPass.debug")   # optional per-pixel debug visualisation

    return g


# ---------------------------------------------------------------------------
# Load graph + scene
# ---------------------------------------------------------------------------
m.addGraph(render_graph_VisCache())

# Default scene — override via command line --scene argument
# m.loadScene("BistroInterior.pyscene")
# m.loadScene("Arcade.pyscene")

# Capture settings (uncomment for automated batch capture)
# m.frameCapture.outputDir = "captures/"
# m.frameCapture.baseFilename = "viscache_full"

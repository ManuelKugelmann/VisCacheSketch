"""
VisCache_Graph.py  —  Mogwai render graph for VisCache (Visibility Cache)
Run from Mogwai: File > Load Script, or pass as --script argument.

Usage:
    Mogwai.exe --script scripts/VisCache_Graph.py --scene Bistro_Interior.pyscene

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

ABLATION_MINUS_A = {   # Disable distance-gated LOD
    "enableDistanceLOD": False,
}
ABLATION_MINUS_B = {   # Disable variance-gated write depth
    "enableVarianceGate": False,
}
ABLATION_MINUS_C = {   # Disable warp reduction (per-lane atomics)
    "enableWarpReduction": False,
}
ABLATION_MINUS_D = {   # Disable inline CAS decay
    "enableDecay": False,
}
ABLATION_MINUS_E = {   # Disable pressure-scaled eviction
    "enablePressureEvict": False,
}
ABLATION_FINEST_ONLY = {   # Multilevel vs. finest-level-only comparison
    "minLevel": 2,
    "maxLevel": 2,
}
ABLATION_COARSEST_ONLY = {
    "minLevel": 0,
    "maxLevel": 0,
}

ACTIVE_ABLATION = ABLATION_FULL   # <-- CHANGE THIS LINE


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def render_graph_VisCache():
    g = RenderGraph("VisCache")

    # G-Buffer
    gbuf = createPass("GBufferRT", {
        "samplePattern": SamplePattern.Stratified,
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          CullMode.CullBack,
    })
    g.addPass(gbuf, "GBufferRT")

    # Visibility Cache
    # Owns the hash table; exposes it via InternalDictionary.
    visCache = createPass("VisCache", {
        "tableCapacity":   1 << 22,   # 4M entries = 32 MB
        "bootThreshold":   32,
        "varThreshold":    0.10,
        "pMin":            0.05,
        "fireflyBudget":   0.05,
        "decayPeriod":     300,       # auto-tuned by PI controller
        "decayPeriodMax":  600,
        "minLevel":        0,
        "maxLevel":        2,
        "enableGIRevalidation": True,
        "enableLightSelection": True,
        "enableWarpReduction":  True,
        "enableVarianceGate":   True,
        "enableDistanceLOD":    True,
        "enableDecay":          True,
        "enablePressureEvict":  True,
    })
    set_ablation(visCache, ACTIVE_ABLATION)
    g.addPass(visCache, "VisCache")

    # RTXDI — direct lighting with optional visibility-weighted selection (§11.1)
    rtxdi = createPass("RTXDIPass", {
        "options": RTXDIOptions(
            mode                  = RTXDIMode.LocalLightRIS,
            numPrimaryLocalLightCandidates = 8,
            numPrimaryInfiniteLightCandidates = 1,
        ),
        "useVisCacheForSelection": True,   # §11.1 — replace V=1 with cached mu
        "explorationFraction":    0.10,   # epsilon-greedy; §11.1 "1/M budget"
    })
    g.addPass(rtxdi, "RTXDIPass")

    # Path tracer with CV+RRR shadow gating on direct hits (§11.2)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    1,
        "maxBounces":         3,
        "useVisCache":   True,
        "colorFormat":        ColorFormat.LogLuvHDR,
    })
    g.addPass(pt, "PathTracer")

    # ReSTIR GI with CV+RRR revalidation (§11.3 / §12)
    # Source: DQLin/ReSTIR_PT ported to Falcor 8.0
    restirgi = createPass("ReSTIRGIPass", {
        "numSpatialNeighbors":     5,
        "spatialRadius":           30,
        "numInitialSamples":       1,
        "useVisCacheRevalidation":    True,
        "contribThreshold":        0.01,
        "revalidationPMin":        0.05,
    })
    g.addPass(restirgi, "ReSTIRGIPass")

    # NRD denoiser
    nrd = createPass("NRDPass", {
        "method":          NRDMethod.RELAX_DIFFUSE_SPECULAR,
        "worldSpaceMotion": True,
    })
    g.addPass(nrd, "NRDPass")

    # Tone mapper
    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      ToneMapOp.Aces,
    })
    g.addPass(tone, "ToneMapper")

    # -----------------------------------------------------------------------
    # Edges
    # -----------------------------------------------------------------------
    g.addEdge("GBufferRT.vbuffer",                   "PathTracer.vbuffer")
    g.addEdge("GBufferRT.viewW",                     "PathTracer.viewW")
    g.addEdge("GBufferRT.vbuffer",                   "RTXDIPass.vbuffer")
    g.addEdge("GBufferRT.linearZ",                   "RTXDIPass.linearZ")
    g.addEdge("GBufferRT.mvec",                      "RTXDIPass.mvec")
    g.addEdge("RTXDIPass.color",                     "PathTracer.directLighting")
    g.addEdge("PathTracer.color",                    "ReSTIRGIPass.color")
    g.addEdge("GBufferRT.vbuffer",                   "ReSTIRGIPass.vbuffer")
    g.addEdge("GBufferRT.mvec",                      "ReSTIRGIPass.mvec")
    g.addEdge("ReSTIRGIPass.color",                  "NRDPass.diffuseRadianceHitDist")
    g.addEdge("ReSTIRGIPass.specularColor",          "NRDPass.specularRadianceHitDist")
    g.addEdge("GBufferRT.linearZ",                   "NRDPass.viewZ")
    g.addEdge("GBufferRT.normW",                     "NRDPass.normalRoughness")
    g.addEdge("GBufferRT.mvec",                      "NRDPass.mvec")
    g.addEdge("NRDPass.filteredDiffuseRadianceHitDist",
              "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    # Secondary outputs for analysis
    g.markOutput("VisCache.hitRate")    # scalar stats texture (if implemented)
    g.markOutput("ReSTIRGIPass.debugVis")   # optional per-pixel V visualisation

    return g


# ---------------------------------------------------------------------------
# Load graph + scene
# ---------------------------------------------------------------------------
m.addGraph(render_graph_VisCache())

# Default scene — override via command line --scene argument
# m.loadScene("Bistro_Interior.pyscene")
# m.loadScene("Arcade.pyscene")

# Capture settings (uncomment for automated batch capture)
# m.frameCapture.outputDir = "captures/"
# m.frameCapture.baseFilename = "viscache_full"

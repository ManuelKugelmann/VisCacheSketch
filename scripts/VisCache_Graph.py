"""
VisCache_Graph.py  —  Mogwai render graph for VisCache (Visibility Cache)
Run from Mogwai: File > Load Script, or pass as --script argument.

Usage:
    Mogwai.exe --script scripts/VisCache_Graph.py --scene BistroInterior.pyscene

Ablation presets can be selected here (ACTIVE_ABLATION) or steered from
test scripts by importing and passing a config dict to render_graph_VisCache():

    from VisCache_Graph import ABLATIONS, render_graph_VisCache
    g = render_graph_VisCache(ablation=ABLATIONS["minus_decay"])
"""

# ---------------------------------------------------------------------------
# Ablation config presets (paper §15)
# ---------------------------------------------------------------------------

ABLATIONS = {
    "full":         {},                                          # All features on — paper result
    "minus_var":    {"enableVisCacheVarianceGate": False},       # -B: no variance-gated write depth
    "minus_warp":   {"enableVisCacheWarpReduction": False},      # -C: no warp reduction (per-lane atomics)
    "minus_decay":  {"enableVisCacheDecay": False},              # -D: no inline CAS decay
    "minus_evict":  {"enableVisCachePressureEvict": False},      # -E: no pressure-scaled eviction
    "single_level": {"numLevels": 1},                            # Single-level (N=1) vs. multilevel
}

# Back-compat aliases
ABLATION_FULL         = ABLATIONS["full"]
ABLATION_MINUS_B      = ABLATIONS["minus_var"]
ABLATION_MINUS_C      = ABLATIONS["minus_warp"]
ABLATION_MINUS_D      = ABLATIONS["minus_decay"]
ABLATION_MINUS_E      = ABLATIONS["minus_evict"]
ABLATION_SINGLE_LEVEL = ABLATIONS["single_level"]

ACTIVE_ABLATION = ABLATION_FULL   # <-- default when run directly


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def render_graph_VisCache(ablation=None):
    """Build the VisCache render graph.

    Args:
        ablation: Dict of VisCachePass overrides, or a key into ABLATIONS.
                  Defaults to ACTIVE_ABLATION when run directly.
    """
    if ablation is None:
        ablation = ACTIVE_ABLATION
    elif isinstance(ablation, str):
        ablation = ABLATIONS[ablation]

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
    vc_params = {
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
        "enableDiagnostics":            True,
    }
    vc_params.update(ablation)
    visCache = createPass("VisCachePass", vc_params)
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

    # ReSTIR PT maxSurfaceBounces=1 with CV+RRR revalidation (§9.3 / §10)
    # Single-bounce: equivalent to ReSTIR GI but with hybrid shift for specular.
    # Source: DQLin/ReSTIR_PT ported to Falcor 8.0
    # VisCache integration (contribThreshold, pMin) is automatic via
    # InternalDictionary — those params live on VisCachePass, not here.
    restirpt = createPass("ReSTIRPTPass", {
        "maxSurfaceBounces":       1,
        "spatialNeighborCount":    5,
        "spatialReuseRadius":      30,
        "candidateSamples":        1,
    })
    g.addPass(restirpt, "ReSTIRPTPass")

    # NRD denoiser (optional — unavailable on Linux / builds without D3D12+NRD).
    # Raw noisy radiance is always available via ReSTIRPTPass.color output.
    _have_nrd = False
    try:
        nrd = createPass("NRDPass", {
            "method":          "RelaxDiffuseSpecular",
            "worldSpaceMotion": True,
        })
        g.addPass(nrd, "NRDPass")
        _have_nrd = True
    except Exception:
        print("[VisCache] WARNING: NRDPass plugin not available — outputting raw noisy radiance."
              " Build with D3D12 + packman NRD package to enable denoising.")

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

    if _have_nrd:
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
    else:
        # Fallback: wire ReSTIR PT color directly to ToneMapper
        g.addEdge("ReSTIRPTPass.color",              "ToneMapper.src")

    g.markOutput("ToneMapper.dst")

    # Secondary outputs for analysis
    g.markOutput("ReSTIRPTPass.color")   # raw noisy radiance (linear HDR) for MSE/FLIP
    g.markOutput("ReSTIRPTPass.debug")   # optional per-pixel debug visualisation

    # -----------------------------------------------------------------------
    # VisCache diagnostic heatmaps
    # Connect vcDiag and vcDiagError to ColorMapPass for false-color output.
    #
    # vcDiag channels (select in ColorMapPass UI):
    #   R = cached mu       (visibility prediction [0,1])
    #   G = variance         (cache uncertainty [0,0.25])
    #   B = LOD level+1    (0=miss, 1=L0, 2=L1, ...)
    #   A = ray saved        (1=skipped, 0=traced)
    #
    # vcDiagError channel R = |mu - V| (prediction accuracy)
    #
    # vcDiagComposite = pre-normalized RGB composite (no ColorMapPass needed):
    #   R = variance*4 [0,1], G = maturity (N/bootThreshold), B = level/numLevels
    # -----------------------------------------------------------------------

    # Heatmap: cached mu / variance / level / raySaved (pick channel in UI)
    heatDiag = createPass("ColorMapPass", {
        "colorMap": "Viridis",
        "channel":  0,           # R = cached mu (change to 1/2/3 for var/level/saved)
        "autoRange": True,
    })
    g.addPass(heatDiag, "HeatmapDiag")
    g.addEdge("VisCache.vcDiag", "HeatmapDiag.input")
    g.markOutput("HeatmapDiag.output")

    # Heatmap: prediction error |mu - V|
    heatErr = createPass("ColorMapPass", {
        "colorMap": "Inferno",
        "channel":  0,
        "autoRange": True,
    })
    g.addPass(heatErr, "HeatmapError")
    g.addEdge("VisCache.vcDiagError", "HeatmapError.input")
    g.markOutput("HeatmapError.output")

    # Composite heatmap: R=mu, G=level, B=N — pre-normalized, no ColorMapPass needed
    g.markOutput("VisCache.vcDiagComposite")

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

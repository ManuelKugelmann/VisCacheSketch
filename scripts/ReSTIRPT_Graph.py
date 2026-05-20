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

try:
    from falcor import *
except ImportError:
    pass

ABLATIONS = {
    "full":         {},                                          # All features on — paper result
    "minus_var":    {"enableVisCacheVarianceGate": False},       # -B: no variance-gated write depth
    "minus_warp":   {"enableVisCacheWarpReduction": False},      # -C: no warp reduction (per-lane atomics)
    "minus_decay":  {"enableVisCacheDecay": False},              # -D: no inline CAS decay
    "minus_evict":  {"enableVisCachePressureEvict": False},      # -E: no pressure-scaled eviction
    "minus_jitter": {"jitterFilter": 0.0, "jitterCell": 0.0},  # -F: no jitter
    "single_level": {"numLevels": 1},                            # Single-level (N=1) vs. multilevel
}


def render_graph_ReSTIRPT(viscache=False, ablation=None, maxBounces=1,
                          shadowGateBounces=3, samplesPerPixel=1,
                          spatialNeighborCount=3, spatialReuseRadius=20,
                          candidateSamples=1, useRTXDIDirect=True,
                          useDirectLighting=True, pathSamplingMode="ReSTIR",
                          disableDirectIllumination=True, fireflyClampK=1e9,
                          restirptAddrMode=0, restirptPoolAddrMode=0,
                          restirptPoolFootprintPx=16,
                          visibilityCheck=None, lightSelection=None):
    # restirptAddrMode (R-axis: reservoir storage):
    #   0 = R2d — DQLIN baseline (2D pixel reservoir only)
    #   1 = R3d — pure 3D reservoir at pixel footprint
    # restirptPoolAddrMode (P-axis: NEE light-sample pool, RTXDI-style):
    #   0 = Pno — no presample pool
    #   1 = P2d — 2D screen-tile pool (RTXDI-tile semantics)
    #   2 = P3d — 3D world-cell pool at footprint
    # restirptPoolFootprintPx: tile / cell side length in pixels (default 16).
    # pathSamplingMode (string): "ReSTIR" (default), "PathReuse" (Bekaert),
    # or "PathTracing" — use "PathTracing" to bypass ReSTIR resampling and
    # validate the basic PT setup independently.
    #
    # disableDirectIllumination: ReSTIRPTPass.h default is true — primary-hit
    # direct light is SKIPPED, expecting RTXDI to provide it via the
    # directLighting input texture. Set to false for standalone use.
    """Build a ReSTIR PT render graph.

    Args:
        viscache: If True, add VisCache pass + PathTracer for shadow gating.
        ablation: Dict of VisCachePass overrides, or a key into ABLATIONS.
                  Only used when viscache=True.
        maxBounces: ReSTIRPTPass.maxSurfaceBounces (path length in bounces).
        shadowGateBounces: PathTracer.maxSurfaceBounces for §11.2 shadow gating
            (only used when viscache=True). Independent from ReSTIRPT bounces.
        samplesPerPixel: ReSTIRPTPass samples per pixel.
        spatialNeighborCount, spatialReuseRadius, candidateSamples: ReSTIRPT
            tuning knobs (defaults match prior config).
    """
    if ablation is None:
        ablation = {}
    elif isinstance(ablation, str):
        ablation = ABLATIONS[ablation]

    name = "ReSTIRPT_VisCache" if viscache else "ReSTIRPT"
    g = RenderGraph(name)

    # G-Buffer — VBufferRT (lighter than GBufferRT) is enough for ReSTIRPT;
    # but the existing wiring uses GBufferRT for compatibility with NRD edges.
    gbuf = createPass("GBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   1,
        "forceCullMode": False,
        "cull":          "Back",
    })
    g.addPass(gbuf, "GBufferRT")

    # Visibility Cache (optional) — hash table + params via InternalDictionary.
    # Diagnostics are written inline by downstream RT passes (PixelStats pattern).
    if viscache:
        vc_params = dict(VISCACHE_DEFAULTS)
        vc_params.update(ablation)
        if visibilityCheck is not None:
            vc_params["enableVisCacheVisibilityCheck"] = bool(visibilityCheck)
        if lightSelection is not None:
            vc_params["enableVisCacheLightSelection"] = bool(lightSelection)
        vc = createPass("VisCachePass", vc_params)
        g.addPass(vc, "VisCache")

    # RTXDI — direct lighting (visibility-weighted selection when VisCache present, §11.1)
    # Optional: skip RTXDI entirely when comparing pure ReSTIRPT (which can do its
    # own NEE direct sampling). Eliminates direct-light double-counting risk.
    if useRTXDIDirect:
        rtxdi = createPass("RTXDIPass", {
            "options": {
                "mode":                       "NoResampling",
                "localLightCandidateCount":    8,
                "infiniteLightCandidateCount": 1,
            },
        })
        g.addPass(rtxdi, "RTXDIPass")

    # PathTracerX for shadow gating (only with VisCache, §11.2).
    # Phase 3: upstream PathTracer is vanilla; VisCache integration lives in PathTracerX.
    if viscache:
        pt = createPass("PathTracerX", {
            "samplesPerPixel":    1,
            "maxSurfaceBounces":  shadowGateBounces,
            "colorFormat":        "LogLuvHDR",
        })
        g.addPass(pt, "PathTracer")

    # ReSTIR PT — indirect lighting via path reuse. useDirectLighting controls
    # whether ReSTIRPT integrates its directLighting input (when wired from
    # RTXDI) into the final radiance. Set False for pure-ReSTIRPT comparisons
    # where ReSTIRPT does its own NEE direct sampling.
    restirpt = createPass("ReSTIRPTPass", {
        "samplesPerPixel":         samplesPerPixel,
        "maxSurfaceBounces":       maxBounces,
        "spatialNeighborCount":    spatialNeighborCount,
        "spatialReuseRadius":      spatialReuseRadius,
        "candidateSamples":        candidateSamples,
        "useDirectLighting":       useDirectLighting,
        "pathSamplingMode":        pathSamplingMode,
        "disableDirectIllumination": disableDirectIllumination,
        "fireflyClampK":           fireflyClampK,
        "restirptAddrMode":        restirptAddrMode,
        "restirptPoolAddrMode":    restirptPoolAddrMode,
        "restirptPoolFootprintPx": restirptPoolFootprintPx,
    })
    g.addPass(restirpt, "ReSTIRPTPass")

    # NRD denoiser previously included as a downstream consumer of
    # ReSTIRPTPass's nrdDiffuse/nrdSpecular outputs. Removed 2026-05-09:
    # leaving NRDPass in the graph (even with its filtered output not
    # routed to AccumulatePass) corrupted ReSTIRPTPass.color on
    # BistroInterior — ladder run produced 459 inf pixels at SPP=16
    # while the AB harness (no NRD in graph) produced max=1529 on the
    # same code with the same fireflyClampK=100. Suspect Falcor buffer-
    # aliasing or NRD's own writes touching shared scratch state. Drop
    # NRD entirely from the ladder graph; if anyone needs denoising for
    # visualization they can build a separate graph with it.
    _have_nrd = False

    # AccumulatePass — average raw ReSTIRPT color across frames so the captured
    # EXR is comparable to vanilla PathTracer's accumulated output. Without this
    # the ReSTIRPT capture is single-frame raw and shows fireflies / non-finite
    # pixels that vanilla's frame-averaged capture suppresses.
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

    # -----------------------------------------------------------------------
    # Edges
    # -----------------------------------------------------------------------
    # GBuffer → RTXDIPass (direct illumination, when wired)
    if useRTXDIDirect:
        g.addEdge("GBufferRT.vbuffer", "RTXDIPass.vbuffer")
        g.addEdge("GBufferRT.mvec",    "RTXDIPass.mvec")

    # PathTracer shadow gating (VisCache only, §11.2)
    if viscache:
        g.addEdge("GBufferRT.vbuffer", "PathTracer.vbuffer")
        g.addEdge("GBufferRT.viewW",   "PathTracer.viewW")

    # RTXDI direct lighting → ReSTIR PT (only when both RTXDI AND
    # ReSTIRPT.useDirectLighting are enabled; otherwise leave the input
    # unbound and let ReSTIRPT compute its own NEE).
    if useRTXDIDirect and useDirectLighting:
        g.addEdge("RTXDIPass.color", "ReSTIRPTPass.directLighting")
    g.addEdge("GBufferRT.vbuffer", "ReSTIRPTPass.vbuffer")
    g.addEdge("GBufferRT.mvec",    "ReSTIRPTPass.motionVectors")

    # AccumulatePass ALWAYS receives raw ReSTIRPTPass.color so the captured
    # AccumulatePass.output EXR is apples-to-apples comparable to vanilla
    # PathTracer's accumulated raw color. Routing NRD's filteredDiffuse
    # into the accumulator (prior behaviour) was a +27× err% inflation
    # bug on the RPT_ZOO ladder — NRD only emits diffuse, dropping all
    # specular/glossy contribution; vanilla GT is unfiltered raw, so the
    # variant capture and GT lived in different signal spaces.
    g.addEdge("ReSTIRPTPass.color", "AccumulatePass.input")
    if _have_nrd:
        g.addEdge("ReSTIRPTPass.nrdDiffuseRadianceHitDist",
                  "NRDPass.diffuseRadianceHitDist")
        g.addEdge("ReSTIRPTPass.nrdSpecularRadianceHitDist",
                  "NRDPass.specularRadianceHitDist")
        g.addEdge("GBufferRT.linearZ",                  "NRDPass.viewZ")
        g.addEdge("GBufferRT.normWRoughnessMaterialID", "NRDPass.normWRoughnessMaterialID")
        g.addEdge("GBufferRT.mvec",                     "NRDPass.mvec")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")   # frame-averaged HDR (apples-to-apples vs vanilla)
    g.markOutput("ReSTIRPTPass.color")      # single-frame raw noisy radiance
    g.markOutput("ReSTIRPTPass.debug")      # optional per-pixel debug visualisation

    # -------------------------------------------------------------------
    # VisCache diagnostic heatmaps (only when viscache=True).
    # Written INLINE by the renderer (PixelStats pattern) into textures
    # owned by VisCache. ColorMapPass heatmaps show previous-frame data
    # (no ordering edge from renderer to heatmaps); raw composites are
    # captured at end of frame and show current-frame data.
    # -------------------------------------------------------------------
    if viscache:
        # RGBA diagnostics — A channel carries data (count, samplesRaw, coldmiss)
        g.markOutput("VisCache.vcAccumMeanVarMatCount", TextureChannelFlags.RGBA)
        g.markOutput("VisCache.vcFrameMeanVarMatSamplesRaw", TextureChannelFlags.RGBA)
        g.markOutput("VisCache.vcFrameLevelProbesSamplesCold", TextureChannelFlags.RGBA)
        g.markOutput("VisCache.vcFrameHashAHashBHashABRays", TextureChannelFlags.RGBA)
        g.markOutput("VisCache.vcAccumRaysNoiseErrorCold", TextureChannelFlags.RGBA)

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_ReSTIRPT())

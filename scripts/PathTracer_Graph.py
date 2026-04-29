"""
PathTracer_Graph.py  —  Vanilla Falcor PathTracer render graph.

Full-featured path tracer with accumulation and tone mapping.
VBuffer → PathTracer → AccumulatePass → ToneMapper.
Optionally adds VisCache for shadow gating (§11.2) when viscache=True.

Usage:
    Mogwai.exe --script scripts/PathTracer_Graph.py --scene VeachAjar.pyscene
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

try:
    from falcor import *
except ImportError:
    pass


def render_graph_PathTracer(viscache=False, maxBounces=3, samplesPerPixel=1, useJitter=True,
                            wsReservoirs=False, wsLevelOffset=1, wsReservoirCapacity=1 << 18,
                            wsMCap=30.0, wsSpatialNeighbours=4, wsLightMuMin=0.01):
    """Build a PathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
        useJitter: If False, pin samples to pixel center (no subpixel jitter).
        wsReservoirs: If True, enable §9.4 world-space ReSTIR DI reservoirs
            (requires viscache=True since reservoirs ride VisCache's posA cascade).
        wsLevelOffset: # cascade levels coarser than the finest visibility level
            for reservoir cell selection (default 1 = one step coarser).
    """
    name = "PathTracer_VisCache" if viscache else "PathTracer"
    if wsReservoirs:
        name += "_WSReSTIR"
    g = RenderGraph(name)
    if wsReservoirs and not viscache:
        # WS reservoirs are exported by the VisCache pass; can't run without it.
        viscache = True

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc_props = {**VISCACHE_DEFAULTS, "spp": samplesPerPixel}
        if wsReservoirs:
            vc_props.update({
                "enableWSReservoirs":   True,
                "wsLevelOffset":        wsLevelOffset,
                "wsReservoirCapacity":  wsReservoirCapacity,
                "wsMCap":               wsMCap,
                "wsSpatialNeighbours":  wsSpatialNeighbours,
                "wsLightMuMin":         wsLightMuMin,
            })
        vc = createPass("VisCachePass", vc_props)
        g.addPass(vc, "VisCache")

    # Falcor PathTracer (full-featured: NEE, MIS, Russian roulette, volumes)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    samplesPerPixel,
        "maxSurfaceBounces":  maxBounces,
        "colorFormat":        "LogLuvHDR",
    })
    g.addPass(pt, "PathTracer")

    # Accumulate samples over frames for progressive rendering. PathTracer internally
    # loops N² Bayer subframes per execute() call, so AccumulatePass sees one fully
    # composed dense frame per renderFrame — no subframe awareness needed here.
    accum_props = {
        "enabled":       True,
        "precisionMode": "Single",
    }
    accum = createPass("AccumulatePass", accum_props)
    g.addPass(accum, "AccumulatePass")

    # Tone mapper
    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    # Edges
    g.addEdge("VBufferRT.vbuffer",   "PathTracer.vbuffer")
    g.addEdge("VBufferRT.viewW",     "PathTracer.viewW")
    g.addEdge("PathTracer.color",    "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")  # pre-tonemapper HDR (captured as EXR)

    # -------------------------------------------------------------------
    # VisCache diagnostic heatmaps (only when viscache=True)
    # -------------------------------------------------------------------
    # Diagnostic heatmaps are written INLINE by PathTracer (PixelStats pattern)
    # into textures owned by the VisCache pass. The ColorMapPass must execute
    # AFTER PathTracer finishes, but there's no data edge from PathTracer to
    # the diagnostic textures (they flow via InternalDictionary). We enforce
    # ordering by routing the diagnostic textures through AccumulatePass first
    # (which already depends on PathTracer.color).
    # -------------------------------------------------------------------
    if viscache:
        # Mark diagnostic outputs (captured at end of frame, after all passes)
        g.markOutput("VisCache.vcAccumMeanVarMatCount", TextureChannelFlags.RGBA)   # R=variance*4, G=maturity, B=mean, A=count
        g.markOutput("VisCache.vcFrameMeanVarMatSamplesRaw", TextureChannelFlags.RGBA)  # R=variance*4, G=maturity, B=mean, A=samplesRaw
        g.markOutput("VisCache.vcFrameLevelProbesSamplesCold", TextureChannelFlags.RGBA)  # R=level, G=probeSteps, B=samples, A=coldmiss
        g.markOutput("VisCache.vcFrameHashAHashBHashABRays", TextureChannelFlags.RGBA)  # R=qAHash, G=qBHash, B=combinedHash, A=raysTraced
        g.markOutput("VisCache.vcAccumRaysNoiseErrorCold", TextureChannelFlags.RGBA)  # R=raysTraced, G=renderNoise, B=renderError, A=coldmiss

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_PathTracer())

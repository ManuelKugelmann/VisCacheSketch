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


def render_graph_PathTracer(viscache=False, maxBounces=3, samplesPerPixel=1, useJitter=True):
    """Build a PathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
        useJitter: If False, pin samples to pixel center (no subpixel jitter).
    """
    name = "PathTracer_VisCache" if viscache else "PathTracer"
    g = RenderGraph(name)

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc = createPass("VisCachePass", VISCACHE_DEFAULTS)
        g.addPass(vc, "VisCache")

    # Falcor PathTracer (full-featured: NEE, MIS, Russian roulette, volumes)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    samplesPerPixel,
        "maxSurfaceBounces":  maxBounces,
        "colorFormat":        "LogLuvHDR",
    })
    g.addPass(pt, "PathTracer")

    # Accumulate samples over frames for progressive rendering
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
        g.markOutput("VisCache.vcFrameHashAHashBHashABRays", TextureChannelFlags.RGBA)  # R=posAHash, G=posBHash, B=combinedHash, A=raysTraced
        g.markOutput("VisCache.vcAccumRaysNoiseErrorCold", TextureChannelFlags.RGBA)  # R=raysTraced, G=renderNoise, B=renderError, A=coldmiss

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_PathTracer())

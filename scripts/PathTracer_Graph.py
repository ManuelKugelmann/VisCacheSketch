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


def render_graph_PathTracer(viscache=False):
    """Build a PathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
    """
    name = "PathTracer_VisCache" if viscache else "PathTracer"
    g = RenderGraph(name)

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc = createPass("VisCachePass", VISCACHE_DEFAULTS)
        g.addPass(vc, "VisCache")

    # Falcor PathTracer (full-featured: NEE, MIS, Russian roulette, volumes)
    pt = createPass("PathTracer", {
        "samplesPerPixel":    1,
        "maxSurfaceBounces":  3,
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
        # Mark raw var/maturity heatmaps as outputs (captured at end of frame, after all passes)
        g.markOutput("VisCache.vcVarMaturityLevel")
        g.markOutput("VisCache.vcVarMaturityMu")

        # Heatmaps: connect VisCache outputs to ColorMapPass.
        # NOTE: These show previous-frame data because the render graph executes
        # VisCache → ColorMapPass → PathTracer (no ordering edge from PT to heatmaps).
        # After warmup the cache is stable so this is visually correct.
        # TODO: Add a dedicated VisCacheDiagResolve pass that runs after PathTracer
        #       to produce same-frame heatmaps.
        heatErr = createPass("ColorMapPass", {
            "colorMap": "Inferno",
            "channel":  0,
            "autoRange": True,
        })
        g.addPass(heatErr, "HeatmapError")
        g.addEdge("VisCache.vcDiagError", "HeatmapError.input")
        g.markOutput("HeatmapError.output")

        heatRayPct = createPass("ColorMapPass", {
            "colorMap": "Viridis",
            "channel":  0,
            "autoRange": False,
            "minValue":  0.0,
            "maxValue":  1.0,
        })
        g.addPass(heatRayPct, "HeatmapRaySavedPct")
        g.addEdge("VisCache.vcRaySavedRatio", "HeatmapRaySavedPct.input")
        g.markOutput("HeatmapRaySavedPct.output")

        heatNoise = createPass("ColorMapPass", {
            "colorMap": "Inferno",
            "channel":  0,
            "autoRange": True,
        })
        g.addPass(heatNoise, "HeatmapNoise")
        g.addEdge("VisCache.vcNoise", "HeatmapNoise.input")
        g.markOutput("HeatmapNoise.output")

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_PathTracer())

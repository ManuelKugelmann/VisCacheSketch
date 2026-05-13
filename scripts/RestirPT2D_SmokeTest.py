"""
RestirPT2D_SmokeTest.py — graph for restirpt_2d validation.

Renders with `useRestirPT=True` and exposes BOTH the pre-tonemapper HDR
(AccumulatePass.output) and post-tonemapper LDR (ToneMapper.dst) for EXR
capture so quality can be compared against vanilla / restirpt_dqlin.

Usage (headless, capture):
    .scripts/mogwai-headless.sh 'RestirPT2D_SmokeTest.py' Sponza 16

Use `restirpt=False` env-var override (or pass to render_graph_RestirPT2DSmoke)
to render the same graph with vanilla PathTracer for A/B comparison.
"""

try:
    from falcor import *
except ImportError:
    pass


def render_graph_RestirPT2DSmoke(restirpt=True, samplesPerPixel=1, maxBounces=3):
    name = "RestirPT2D_Smoke" if restirpt else "Vanilla_PathTracer"
    g = RenderGraph(name)

    vbuf = createPass("VBufferRT", {"samplePattern": "Stratified", "sampleCount": 16})
    g.addPass(vbuf, "VBufferRT")

    # PathTracerX carries the `useRestirPT` toggle (and all VisCache-era extensions).
    # Phase 3: upstream PathTracer reverted to vanilla; this script needs the fork.
    pt = createPass("PathTracerX", {
        "samplesPerPixel":    samplesPerPixel,
        "maxSurfaceBounces":  maxBounces,
        "colorFormat":        "LogLuvHDR",
        "useRestirPT":        restirpt,
    })
    g.addPass(pt, "PathTracer")

    accum = createPass("AccumulatePass", {"enabled": True, "precisionMode": "Single"})
    g.addPass(accum, "AccumulatePass")

    tone = createPass("ToneMapper", {"autoExposure": False, "exposureValue": 0.0, "operator": "Aces"})
    g.addPass(tone, "ToneMapper")

    g.addEdge("VBufferRT.vbuffer",     "PathTracer.vbuffer")
    g.addEdge("VBufferRT.viewW",       "PathTracer.viewW")
    g.addEdge("PathTracer.color",      "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")   # pre-tonemapper HDR for EXR comparison

    return g


if 'm' in globals():
    m.addGraph(render_graph_RestirPT2DSmoke())

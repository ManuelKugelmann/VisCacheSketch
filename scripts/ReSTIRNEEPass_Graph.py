"""
ReSTIRNEEPass_Graph.py — every-vertex K-RIS NEE on a clean PathTracerX base.

VBuffer → ReSTIRNEEPass → AccumulatePass → ToneMapper.

The K knob (numNEECandidates) defaults to 16. Set K=1 to fall through to
byte-for-byte vanilla NEE (useful as a sanity baseline).

Usage:
    Mogwai.exe --script scripts/ReSTIRNEEPass_Graph.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from falcor import *
except ImportError:
    pass


def render_graph_ReSTIRNEEPass(maxBounces=3, samplesPerPixel=1, useJitter=True,
                               numNEECandidates=16, emissiveSampler=None):
    g = RenderGraph("ReSTIRNEEPass")

    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    pt_props = {
        "samplesPerPixel":   samplesPerPixel,
        "maxSurfaceBounces": maxBounces,
        "colorFormat":       "LogLuvHDR",
        "numNEECandidates":  numNEECandidates,
    }
    if emissiveSampler is not None:
        pt_props["emissiveSampler"] = emissiveSampler
    pt = createPass("ReSTIRNEEPass", pt_props)
    g.addPass(pt, "ReSTIRNEE")

    accum = createPass("AccumulatePass", {"enabled": True, "precisionMode": "Single"})
    g.addPass(accum, "AccumulatePass")

    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    g.addEdge("VBufferRT.vbuffer",   "ReSTIRNEE.vbuffer")
    g.addEdge("VBufferRT.viewW",     "ReSTIRNEE.viewW")
    g.addEdge("ReSTIRNEE.color",     "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")
    return g


if 'm' in globals():
    m.addGraph(render_graph_ReSTIRNEEPass())

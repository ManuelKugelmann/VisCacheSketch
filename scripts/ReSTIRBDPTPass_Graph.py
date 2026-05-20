"""
ReSTIRBDPTPass_Graph.py — Standalone ReSTIR BDPT smoke graph.

Mirrors Shmaug's upstream ReSTIRBDPT.py: VBufferRT → ReSTIRBDPT →
Accumulate → ToneMapper. Used to validate the Falcor 7→8 port.

The plugin DLL is ReSTIRBDPTPass.dll but the registered pass name is
"ReSTIRBDPT" (matches FALCOR_PLUGIN_CLASS in ReSTIRBDPT.h).

Usage:
    Mogwai.exe scripts/ReSTIRBDPTPass_Graph.py
    .scripts/mogwai-headless.sh scripts/ReSTIRBDPTPass_Graph.py CornellBox 1
"""

try:
    from falcor import *
except ImportError:
    pass


def render_graph_ReSTIRBDPTPass():
    g = RenderGraph("ReSTIRBDPTPass")

    bdpt = createPass("ReSTIRBDPT", {})
    g.addPass(bdpt, "ReSTIRBDPT")

    vbuffer = createPass("VBufferRT", {
        'adjustShadingNormals': False,
        'samplePattern': 'Center',
        'sampleCount': 1,
        'useAlphaTest': True,
    })
    g.addPass(vbuffer, "VBufferRT")

    accum = createPass("AccumulatePass", {'enabled': False, 'precisionMode': 'Single'})
    g.addPass(accum, "AccumulatePass")

    tm = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(tm, "ToneMapper")

    g.addEdge("VBufferRT.vbuffer", "ReSTIRBDPT.vbuffer")
    g.addEdge("VBufferRT.viewW",   "ReSTIRBDPT.viewW")
    g.addEdge("VBufferRT.mvec",    "ReSTIRBDPT.mvec")
    g.addEdge("ReSTIRBDPT.color",  "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    return g


if 'm' in globals():
    m.addGraph(render_graph_ReSTIRBDPTPass())

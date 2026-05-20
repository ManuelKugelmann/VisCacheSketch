"""
BDPTPass_Graph.py — Vanilla bidirectional path tracer baseline.

Mirrors Shmaug's upstream ReSTIRBDPT.py topology but instantiates the
separate `BDPT` plugin (vanilla bidirectional path tracer, extracted
from ReSTIRBDPTPass). This is the BDPT analogue of Falcor's built-in
PathTracer — the deterministic baseline against which ReSTIRBDPTPass
will be measured.

The BDPT plugin hard-pins useBPT=True, useResampling=False, no
temporal/caustic reservoirs — so this graph runs the pure BDPT
estimator: light subpaths + camera subpaths + MIS-weighted connections.

Usage:
    Mogwai.exe scripts/BDPTPass_Graph.py
    .scripts/mogwai-headless.sh '*BDPTPass_Graph*' CornellBox_1AreaLight.pyscene 1
"""

try:
    from falcor import *
except ImportError:
    pass


def render_graph_BDPTPass():
    g = RenderGraph("BDPTPass")

    bdpt = createPass("BDPT", {})
    g.addPass(bdpt, "BDPT")

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

    g.addEdge("VBufferRT.vbuffer", "BDPT.vbuffer")
    g.addEdge("VBufferRT.viewW",   "BDPT.viewW")
    g.addEdge("VBufferRT.mvec",    "BDPT.mvec")
    g.addEdge("BDPT.color",        "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    return g


if 'm' in globals():
    m.addGraph(render_graph_BDPTPass())

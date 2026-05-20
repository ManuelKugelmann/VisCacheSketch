"""
ReSTIRBDPTPass_Resampling_Graph.py — Full ReSTIR-BDPT mode (debugging).

Enables the ReSTIR resampling layer that currently crashes during
first dispatch. Used to drive root-causing of the GPUHashMap reflection
or per-pixel-reservoir buffer wiring under Falcor 8.
"""

try:
    from falcor import *
except ImportError:
    pass


def render_graph_ReSTIRBDPTPass_Resampling():
    g = RenderGraph("ReSTIRBDPTPass_Resampling")

    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': False,
        'useCausticReservoirs': False,
        'useCausticShift': False,
    })
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
    m.addGraph(render_graph_ReSTIRBDPTPass_Resampling())

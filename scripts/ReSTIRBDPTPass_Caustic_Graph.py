"""
ReSTIRBDPTPass_Caustic_Graph.py — Enable caustic-reservoir feature.

Tests `useCausticReservoirs=True` (the second-most-disabled ReSTIR-BDPT feature
besides the shift-to-pixel-center we've ruled out). Independent of the
ResolveLightTraceReservoirs reflection bug, so should work if the caustic
path types don't trip a different reflection issue.
"""
try:
    from falcor import *
except ImportError:
    pass

def render_graph():
    g = RenderGraph("ReSTIRBDPTPass_Caustic")

    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': True,
        'useCausticReservoirs': True,
        'useCausticShift': True,
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
    m.addGraph(render_graph())

"""
ReSTIRBDPTPass_Spatial_Graph.py — Test spatial reuse with no temporal.

Validates whether `spatialReusePasses>0` (SpatialReuse.cs.slang) crashes
the same way as TemporalReuse (both reach ShiftPath through the call
graph). Predicted: same crash family.
"""
try:
    from falcor import *
except ImportError:
    pass

def render_graph():
    g = RenderGraph("ReSTIRBDPTPass_Spatial")

    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': False,
        'useCausticReservoirs': False,
        'useCausticShift': False,
        'spatialReusePasses': 1,         # NEW: enable one spatial reuse pass
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

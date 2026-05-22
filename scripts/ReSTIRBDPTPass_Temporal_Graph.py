"""
ReSTIRBDPTPass_Temporal_Graph.py — ReSTIR-BDPT with temporal reuse ON.

Used to track task #12: re-enable useTemporalReuse (Slang trip family of task #10).
Currently expected to FAIL on dispatch until the warmup-helper fix is applied
to TemporalReuse.cs.slang's entry. PASS = task #12 complete.
"""
from falcor import *

def render_graph_ReSTIRBDPTPass_Temporal():
    g = RenderGraph("ReSTIRBDPTPass_Temporal")

    bdpt = createPass("ReSTIRBDPT", {
        'useBPT': True,
        'useResampling': True,
        'useTemporalResampling': True,
        'unbiasedTemporalReuse': True,
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
    m.addGraph(render_graph_ReSTIRBDPTPass_Temporal())

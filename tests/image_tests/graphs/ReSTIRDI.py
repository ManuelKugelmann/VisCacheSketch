from falcor import *

def render_graph_ReSTIRDI_Vanilla():
    """ReSTIR DI — vanilla (no VisCache). Baseline identical to RTXDIPass."""
    g = RenderGraph("ReSTIRDI_Vanilla")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("ReSTIRDIPass", {
        'enableVisCacheRevalidation': False,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.motionVectors")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def render_graph_ReSTIRDI_VisCacheReval():
    """ReSTIR DI — VisCache CV+RRR shadow ray gating (S11.3)."""
    g = RenderGraph("ReSTIRDI_VisCacheReval")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("ReSTIRDIPass", {
        'enableVisCacheRevalidation': True,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.motionVectors")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def render_graph_ReSTIRDI_VisCacheFull():
    """ReSTIR DI — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRDI_VisCacheFull")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("ReSTIRDIPass", {
        'enableVisCacheRevalidation': True,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.motionVectors")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


ReSTIRDI_Vanilla = render_graph_ReSTIRDI_Vanilla()
ReSTIRDI_VisCacheReval = render_graph_ReSTIRDI_VisCacheReval()
ReSTIRDI_VisCacheFull = render_graph_ReSTIRDI_VisCacheFull()
try: m.addGraph(ReSTIRDI_Vanilla)
except NameError: None

from falcor import *

def render_graph_ReSTIRDI_Vanilla():
    """ReSTIR DI — vanilla (no VisCache). Baseline identical to RTXDIPass."""
    g = RenderGraph("ReSTIRDI_Vanilla")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    # RTXDIPass only accepts "options"; VisCache integration is via InternalDictionary
    ReSTIRDI = createPass("RTXDIPass")
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.mvec")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def render_graph_ReSTIRDI_VisCacheRevalidation():
    """ReSTIR DI — VisCache CV+RRR shadow ray gating (S11.3)."""
    g = RenderGraph("ReSTIRDI_VisCacheRevalidation")
    VisCache = createPass("VisCachePass", {
        'enableVisCacheVisibilityCheck': True,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("RTXDIPass")
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.mvec")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def render_graph_ReSTIRDI_VisCacheLightSelection():
    """ReSTIR DI — VisCache light pre-selection only (S11.1, no S11.3)."""
    g = RenderGraph("ReSTIRDI_VisCacheLightSelection")
    VisCache = createPass("VisCachePass", {
        'enableVisCacheVisibilityCheck': False,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("RTXDIPass")
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.mvec")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def render_graph_ReSTIRDI_VisCacheFull():
    """ReSTIR DI — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRDI_VisCacheFull")
    VisCache = createPass("VisCachePass", {
        'enableVisCacheVisibilityCheck': True,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("RTXDIPass")
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.mvec")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


ReSTIRDI_Vanilla = render_graph_ReSTIRDI_Vanilla()
ReSTIRDI_VisCacheRevalidation = render_graph_ReSTIRDI_VisCacheRevalidation()
ReSTIRDI_VisCacheLightSelection = render_graph_ReSTIRDI_VisCacheLightSelection()
ReSTIRDI_VisCacheFull = render_graph_ReSTIRDI_VisCacheFull()
try: m.addGraph(ReSTIRDI_Vanilla)
except NameError: None

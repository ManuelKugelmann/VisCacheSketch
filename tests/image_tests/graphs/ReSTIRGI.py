from falcor import *

def render_graph_ReSTIRGI_Vanilla():
    """ReSTIR GI — vanilla (unconditional shadow rays, no VisCache)."""
    g = RenderGraph("ReSTIRGI_Vanilla")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRGI = createPass("ReSTIRGIPass", {
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRGI, "ReSTIRGI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRGI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRGI.motionVectors")
    g.addEdge("ReSTIRGI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRGI.color")
    return g


def render_graph_ReSTIRGI_CVRRRLocal():
    """ReSTIR GI — local CV+RRR (reservoir-local mu, no hash table)."""
    g = RenderGraph("ReSTIRGI_CVRRRLocal")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRGI = createPass("ReSTIRGIPass", {
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': True,
        'enableVisCacheLightSelection': False,
        'visCacheContribThreshold': 0.01,
        'visCachePMin': 0.05,
    })
    g.addPass(ReSTIRGI, "ReSTIRGI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRGI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRGI.motionVectors")
    g.addEdge("ReSTIRGI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRGI.color")
    return g


def render_graph_ReSTIRGI_VisCacheReval():
    """ReSTIR GI — VisCache CV+RRR revalidation (S11.3)."""
    g = RenderGraph("ReSTIRGI_VisCacheReval")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRGI = createPass("ReSTIRGIPass", {
        'enableVisCacheRevalidation': True,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRGI, "ReSTIRGI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRGI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRGI.motionVectors")
    g.addEdge("ReSTIRGI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRGI.color")
    return g


def render_graph_ReSTIRGI_VisCacheLightSel():
    """ReSTIR GI — VisCache light pre-selection only (S11.1, no S11.3)."""
    g = RenderGraph("ReSTIRGI_VisCacheLightSel")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRGI = createPass("ReSTIRGIPass", {
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(ReSTIRGI, "ReSTIRGI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRGI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRGI.motionVectors")
    g.addEdge("ReSTIRGI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRGI.color")
    return g


def render_graph_ReSTIRGI_VisCacheFull():
    """ReSTIR GI — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRGI_VisCacheFull")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRGI = createPass("ReSTIRGIPass", {
        'enableVisCacheRevalidation': True,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(ReSTIRGI, "ReSTIRGI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRGI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRGI.motionVectors")
    g.addEdge("ReSTIRGI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRGI.color")
    return g


ReSTIRGI_Vanilla = render_graph_ReSTIRGI_Vanilla()
ReSTIRGI_CVRRRLocal = render_graph_ReSTIRGI_CVRRRLocal()
ReSTIRGI_VisCacheReval = render_graph_ReSTIRGI_VisCacheReval()
ReSTIRGI_VisCacheLightSel = render_graph_ReSTIRGI_VisCacheLightSel()
ReSTIRGI_VisCacheFull = render_graph_ReSTIRGI_VisCacheFull()
try: m.addGraph(ReSTIRGI_Vanilla)
except NameError: None

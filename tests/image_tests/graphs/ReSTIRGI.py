from falcor import *

def render_graph_ReSTIRPT_Vanilla():
    """ReSTIR PT (single-bounce) — vanilla (unconditional shadow rays, no VisCache)."""
    g = RenderGraph("ReSTIRPT_Vanilla")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


def render_graph_ReSTIRPT_CVRRRLocal():
    """ReSTIR PT (single-bounce) — local CV+RRR (reservoir-local mu, no hash table)."""
    g = RenderGraph("ReSTIRPT_CVRRRLocal")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': True,
        'enableVisCacheLightSelection': False,
        'visCacheContribThreshold': 0.01,
        'visCachePMin': 0.05,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


def render_graph_ReSTIRPT_VisCacheReval():
    """ReSTIR PT (single-bounce) — VisCache CV+RRR revalidation (S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheReval")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableVisCacheRevalidation': True,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': False,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


def render_graph_ReSTIRPT_VisCacheLightSel():
    """ReSTIR PT (single-bounce) — VisCache light pre-selection only (S11.1, no S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheLightSel")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


def render_graph_ReSTIRPT_VisCacheFull():
    """ReSTIR PT (single-bounce) — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheFull")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableVisCacheRevalidation': True,
        'enableCVRRRRevalidation': False,
        'enableVisCacheLightSelection': True,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")
    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


ReSTIRPT_Vanilla = render_graph_ReSTIRPT_Vanilla()
ReSTIRPT_CVRRRLocal = render_graph_ReSTIRPT_CVRRRLocal()
ReSTIRPT_VisCacheReval = render_graph_ReSTIRPT_VisCacheReval()
ReSTIRPT_VisCacheLightSel = render_graph_ReSTIRPT_VisCacheLightSel()
ReSTIRPT_VisCacheFull = render_graph_ReSTIRPT_VisCacheFull()
try: m.addGraph(ReSTIRPT_Vanilla)
except NameError: None

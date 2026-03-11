from falcor import *

def render_graph_ReSTIRPT_Vanilla():
    """ReSTIR PT — vanilla multi-bounce (no VisCache)."""
    g = RenderGraph("ReSTIRPT_Vanilla")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
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
    """ReSTIR PT — local CV+RRR (reservoir-local mu, no hash table)."""
    g = RenderGraph("ReSTIRPT_CVRRRLocal")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
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
    """ReSTIR PT — VisCache CV+RRR revalidation (S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheReval")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
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
    """ReSTIR PT — VisCache light pre-selection only (S11.1, no S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheLightSel")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
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
    """ReSTIR PT — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRPT_VisCacheFull")
    VisCache = createPass("VisCachePass")
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
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


# ---------------------------------------------------------------------------
# Single-bounce (maxBounces=1) — subsumes ReSTIR GI tests.
# ReSTIR PT at maxBounces=1 produces the same estimator as ReSTIR GI but
# with the hybrid shift (reconnection + random replay) that also handles
# specular first bounces.
# ---------------------------------------------------------------------------

def render_graph_ReSTIRPT1_Vanilla():
    """ReSTIR PT maxBounces=1 — vanilla (no VisCache)."""
    g = RenderGraph("ReSTIRPT1_Vanilla")
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


def render_graph_ReSTIRPT1_VisCacheFull():
    """ReSTIR PT maxBounces=1 — VisCache revalidation + light selection."""
    g = RenderGraph("ReSTIRPT1_VisCacheFull")
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


# Multi-bounce (maxBounces=4)
ReSTIRPT_Vanilla = render_graph_ReSTIRPT_Vanilla()
ReSTIRPT_CVRRRLocal = render_graph_ReSTIRPT_CVRRRLocal()
ReSTIRPT_VisCacheReval = render_graph_ReSTIRPT_VisCacheReval()
ReSTIRPT_VisCacheLightSel = render_graph_ReSTIRPT_VisCacheLightSel()
ReSTIRPT_VisCacheFull = render_graph_ReSTIRPT_VisCacheFull()

# Single-bounce (maxBounces=1) — replaces former ReSTIR GI tests
ReSTIRPT1_Vanilla = render_graph_ReSTIRPT1_Vanilla()
ReSTIRPT1_VisCacheFull = render_graph_ReSTIRPT1_VisCacheFull()

try: m.addGraph(ReSTIRPT_Vanilla)
except NameError: None

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
# Single-bounce GI variants (maxBounces=1, equivalent to ReSTIR GI)
# ---------------------------------------------------------------------------

def render_graph_ReSTIRPT_GI_Vanilla():
    """ReSTIR PT (single-bounce GI) — vanilla (unconditional shadow rays, no VisCache)."""
    g = RenderGraph("ReSTIRPT_GI_Vanilla")
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


def render_graph_ReSTIRPT_GI_CVRRRLocal():
    """ReSTIR PT (single-bounce GI) — local CV+RRR (reservoir-local mu, no hash table)."""
    g = RenderGraph("ReSTIRPT_GI_CVRRRLocal")
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


def render_graph_ReSTIRPT_GI_VisCacheReval():
    """ReSTIR PT (single-bounce GI) — VisCache CV+RRR revalidation (S11.3)."""
    g = RenderGraph("ReSTIRPT_GI_VisCacheReval")
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


def render_graph_ReSTIRPT_GI_VisCacheLightSel():
    """ReSTIR PT (single-bounce GI) — VisCache light pre-selection only (S11.1, no S11.3)."""
    g = RenderGraph("ReSTIRPT_GI_VisCacheLightSel")
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


def render_graph_ReSTIRPT_GI_VisCacheFull():
    """ReSTIR PT (single-bounce GI) — VisCache revalidation + light selection (S11.1 + S11.3)."""
    g = RenderGraph("ReSTIRPT_GI_VisCacheFull")
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


# ---------------------------------------------------------------------------
# Multi-bounce PT graph instances
# ---------------------------------------------------------------------------
ReSTIRPT_Vanilla = render_graph_ReSTIRPT_Vanilla()
ReSTIRPT_CVRRRLocal = render_graph_ReSTIRPT_CVRRRLocal()
ReSTIRPT_VisCacheReval = render_graph_ReSTIRPT_VisCacheReval()
ReSTIRPT_VisCacheLightSel = render_graph_ReSTIRPT_VisCacheLightSel()
ReSTIRPT_VisCacheFull = render_graph_ReSTIRPT_VisCacheFull()

# ---------------------------------------------------------------------------
# Single-bounce GI graph instances
# ---------------------------------------------------------------------------
ReSTIRPT_GI_Vanilla = render_graph_ReSTIRPT_GI_Vanilla()
ReSTIRPT_GI_CVRRRLocal = render_graph_ReSTIRPT_GI_CVRRRLocal()
ReSTIRPT_GI_VisCacheReval = render_graph_ReSTIRPT_GI_VisCacheReval()
ReSTIRPT_GI_VisCacheLightSel = render_graph_ReSTIRPT_GI_VisCacheLightSel()
ReSTIRPT_GI_VisCacheFull = render_graph_ReSTIRPT_GI_VisCacheFull()

try: m.addGraph(ReSTIRPT_Vanilla)
except NameError: None

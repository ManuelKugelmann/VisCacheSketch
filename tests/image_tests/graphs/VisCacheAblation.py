from falcor import *

# ---------------------------------------------------------------------------
# Default VisCache params (all ablation toggles ON)
# ---------------------------------------------------------------------------
_VC_DEFAULTS = {
    'enableDistanceLOD':   True,
    'enableVarianceGate':  True,
    'enableWarpReduction': True,
    'enableDecay':         True,
    'enablePressureEvict': True,
}


def _make_viscache(overrides={}):
    """Create a VisCachePass with default params + overrides."""
    params = dict(_VC_DEFAULTS, **overrides)
    return createPass("VisCachePass", params)


def _make_gi_graph(name, vc_overrides={}):
    """ReSTIR GI full VisCache graph with VisCache ablation overrides."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
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


def _make_di_graph(name, vc_overrides={}):
    """ReSTIR DI full VisCache graph with VisCache ablation overrides."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
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


def _make_pt_graph(name, vc_overrides={}):
    """ReSTIR PT full VisCache graph with VisCache ablation overrides."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
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
# Ablation A–E: GI (primary ablation pass — tests all toggles)
# ---------------------------------------------------------------------------
VisCacheAblation_GI_Full     = _make_gi_graph("VisCacheAblation_GI_Full")
VisCacheAblation_GI_NoLOD    = _make_gi_graph("VisCacheAblation_GI_NoLOD",    {'enableDistanceLOD': False})
VisCacheAblation_GI_NoVarGate= _make_gi_graph("VisCacheAblation_GI_NoVarGate",{'enableVarianceGate': False})
VisCacheAblation_GI_NoWarp   = _make_gi_graph("VisCacheAblation_GI_NoWarp",   {'enableWarpReduction': False})
VisCacheAblation_GI_NoDecay  = _make_gi_graph("VisCacheAblation_GI_NoDecay",  {'enableDecay': False})
VisCacheAblation_GI_NoEvict  = _make_gi_graph("VisCacheAblation_GI_NoEvict",  {'enablePressureEvict': False})

# ---------------------------------------------------------------------------
# Decay ablation spot-checks: DI and PT (most decay-sensitive)
# ---------------------------------------------------------------------------
VisCacheAblation_DI_NoDecay = _make_di_graph("VisCacheAblation_DI_NoDecay", {'enableDecay': False})
VisCacheAblation_PT_NoDecay = _make_pt_graph("VisCacheAblation_PT_NoDecay", {'enableDecay': False})

try: m.addGraph(VisCacheAblation_GI_Full)
except NameError: None

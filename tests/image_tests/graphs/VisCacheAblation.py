from falcor import *

# ---------------------------------------------------------------------------
# Default VisCache params (all features + ablation toggles ON)
# Feature flags are set here on VisCache and forwarded via dictionary to
# downstream passes — no need to duplicate on each ReSTIR pass.
# ---------------------------------------------------------------------------
_VC_DEFAULTS = {
    'enableVisCacheRevalidation':    True,
    'enableVisCacheLightSelection':  True,
    'enableVisCacheVarianceGate':    True,
    'enableVisCacheWarpReduction':   True,
    'enableVisCacheDecay':           True,
    'enableVisCachePressureEvict':   True,
}


def _make_viscache(overrides={}):
    """Create a VisCachePass with default params + overrides."""
    params = dict(_VC_DEFAULTS, **overrides)
    return createPass("VisCachePass", params)


def _make_gi_graph(name, vc_overrides={}):
    """Single-bounce ReSTIR PT graph (subsumes ReSTIR GI) — feature flags come from VisCache via dict."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 1,
        'enableCVRRRRevalidation': False,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    # VisCache is dictionary-only (no graph inputs/outputs)
    g.addEdge("VBuffer.vbuffer", "ReSTIRPT.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRPT.motionVectors")
    g.addEdge("ReSTIRPT.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRPT.color")
    return g


def _make_di_graph(name, vc_overrides={}):
    """ReSTIR DI graph — feature flags come from VisCache via dict."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRDI = createPass("RTXDIPass")
    g.addPass(ReSTIRDI, "ReSTIRDI")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    # VisCache is dictionary-only (no graph inputs/outputs)
    g.addEdge("VBuffer.vbuffer", "ReSTIRDI.vbuffer")
    g.addEdge("VBuffer.mvec", "ReSTIRDI.mvec")
    g.addEdge("ReSTIRDI.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("ReSTIRDI.color")
    return g


def _make_pt_graph(name, vc_overrides={}):
    """ReSTIR PT graph — feature flags come from VisCache via dict."""
    g = RenderGraph(name)
    VisCache = _make_viscache(vc_overrides)
    g.addPass(VisCache, "VisCache")
    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")
    ReSTIRPT = createPass("ReSTIRPTPass", {
        'maxBounces': 4,
        'enableCVRRRRevalidation': False,
    })
    g.addPass(ReSTIRPT, "ReSTIRPT")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    # VisCache is dictionary-only (no graph inputs/outputs)
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
VisCacheAblation_GI_SingleLvl= _make_gi_graph("VisCacheAblation_GI_SingleLvl",{'numLevels': 1})
VisCacheAblation_GI_NoVarGate= _make_gi_graph("VisCacheAblation_GI_NoVarGate",{'enableVisCacheVarianceGate': False})
VisCacheAblation_GI_NoWarp   = _make_gi_graph("VisCacheAblation_GI_NoWarp",   {'enableVisCacheWarpReduction': False})
VisCacheAblation_GI_NoDecay  = _make_gi_graph("VisCacheAblation_GI_NoDecay",  {'enableVisCacheDecay': False})
VisCacheAblation_GI_NoEvict  = _make_gi_graph("VisCacheAblation_GI_NoEvict",  {'enableVisCachePressureEvict': False})

# ---------------------------------------------------------------------------
# Decay ablation spot-checks: DI and PT (most decay-sensitive)
# ---------------------------------------------------------------------------
VisCacheAblation_DI_NoDecay = _make_di_graph("VisCacheAblation_DI_NoDecay", {'enableVisCacheDecay': False})
VisCacheAblation_PT_NoDecay = _make_pt_graph("VisCacheAblation_PT_NoDecay", {'enableVisCacheDecay': False})

try: m.addGraph(VisCacheAblation_GI_Full)
except NameError: None

"""
VisCache_Baselines.py  —  Automated baseline capture script
Runs all ReSTIR variant baselines (DI/PT1/PT × Vanilla/LocalCVRRR/VisCache).

Usage:
    Mogwai.exe --headless --script scripts/VisCache_Baselines.py --scene Bistro_Interior.pyscene

Outputs to: captures/baselines/<pass>_<config>/frame_NNNN.exr
Each config captures kWarmupFrames then kCaptureFrames EXR frames.
"""

import os

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 16    # frames to capture per config
kCaptureDir    = "captures/baselines"

# ---------------------------------------------------------------------------
# VisCache defaults (all features on)
# ---------------------------------------------------------------------------
_VC_DEFAULTS = {
    'enableVisCacheRevalidation':    True,
    'enableVisCacheLightSelection':  True,
    'enableVisCacheVarianceGate':    True,
    'enableVisCacheWarpReduction':   True,
    'enableVisCacheDecay':           True,
    'enableVisCachePressureEvict':   True,
}

# ---------------------------------------------------------------------------
# Baseline configurations
# Each entry: (name, pass_type, needs_viscache, pass_overrides, vc_overrides)
# ---------------------------------------------------------------------------
BASELINE_CONFIGS = [
    # --- ReSTIR PT maxBounces=1 (subsumes ReSTIR GI) ---
    ("GI_Vanilla", "ReSTIRPTPass", False, {
        'maxBounces': 1,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation':    False,
        'enableVisCacheLightSelection': False,
    }, {}),
    ("GI_CVRRRRevalidation", "ReSTIRPTPass", False, {
        'maxBounces': 1,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation':    True,
        'enableVisCacheLightSelection': False,
        'visCacheContribThreshold':   0.01,
        'visCachePMin':               0.05,
    }, {}),
    ("GI_VisCacheRevalidation", "ReSTIRPTPass", True, {
        'maxBounces': 1,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': False,
    }),
    ("GI_VisCacheLightSelection", "ReSTIRPTPass", True, {
        'maxBounces': 1,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   False,
        'enableVisCacheLightSelection': True,
    }),
    ("GI_VisCacheFull", "ReSTIRPTPass", True, {
        'maxBounces': 1,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': True,
    }),

    # --- ReSTIR DI ---
    ("DI_Vanilla", "ReSTIRDIPass", False, {
        'enableVisCacheRevalidation':   False,
        'enableVisCacheLightSelection': False,
    }, {}),
    ("DI_VisCacheRevalidation", "ReSTIRDIPass", True, {}, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': False,
    }),
    ("DI_VisCacheLightSelection", "ReSTIRDIPass", True, {}, {
        'enableVisCacheRevalidation':   False,
        'enableVisCacheLightSelection': True,
    }),
    ("DI_VisCacheFull", "ReSTIRDIPass", True, {}, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': True,
    }),

    # --- ReSTIR PT ---
    ("PT_Vanilla", "ReSTIRPTPass", False, {
        'maxBounces': 4,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation':    False,
        'enableVisCacheLightSelection': False,
    }, {}),
    ("PT_CVRRRRevalidation", "ReSTIRPTPass", False, {
        'maxBounces': 4,
        'enableVisCacheRevalidation': False,
        'enableCVRRRRevalidation':    True,
        'enableVisCacheLightSelection': False,
        'visCacheContribThreshold':   0.01,
        'visCachePMin':               0.05,
    }, {}),
    ("PT_VisCacheRevalidation", "ReSTIRPTPass", True, {
        'maxBounces': 4,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': False,
    }),
    ("PT_VisCacheLightSelection", "ReSTIRPTPass", True, {
        'maxBounces': 4,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   False,
        'enableVisCacheLightSelection': True,
    }),
    ("PT_VisCacheFull", "ReSTIRPTPass", True, {
        'maxBounces': 4,
        'enableCVRRRRevalidation': False,
    }, {
        'enableVisCacheRevalidation':   True,
        'enableVisCacheLightSelection': True,
    }),
]


def build_graph(name, pass_type, needs_viscache, pass_overrides, vc_overrides):
    """Build a render graph for one baseline configuration."""
    g = RenderGraph(name)

    VBuffer = createPass("VBufferRT")
    g.addPass(VBuffer, "VBuffer")

    if needs_viscache:
        vc_params = dict(_VC_DEFAULTS, **vc_overrides)
        VisCache = createPass("VisCachePass", vc_params)
        g.addPass(VisCache, "VisCache")
        g.addEdge("VBuffer.vbuffer", "VisCache.vbuffer")

    Pass = createPass(pass_type, pass_overrides)
    g.addPass(Pass, "MainPass")

    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0})
    g.addPass(ToneMapper, "ToneMapper")

    g.addEdge("VBuffer.vbuffer", "MainPass.vbuffer")
    g.addEdge("VBuffer.mvec", "MainPass.motionVectors")
    g.addEdge("MainPass.color", "ToneMapper.src")
    g.markOutput("ToneMapper.dst")
    g.markOutput("MainPass.color")
    return g


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
for (name, pass_type, needs_vc, pass_ov, vc_ov) in BASELINE_CONFIGS:
    print(f"[Baselines] Running: {name}")

    g = build_graph(name, pass_type, needs_vc, pass_ov, vc_ov)
    m.addGraph(g)

    outdir = os.path.join(kCaptureDir, name)
    os.makedirs(outdir, exist_ok=True)
    m.frameCapture.outputDir    = outdir
    m.frameCapture.baseFilename = name

    # Warm up
    for _ in range(kWarmupFrames):
        renderFrame()

    # Capture
    for i in range(kCaptureFrames):
        m.frameCapture.capture()
        renderFrame()

    m.removeGraph(g)
    print(f"[Baselines] {name} done — {kCaptureFrames} frames saved to {outdir}")

print("[Baselines] All baseline configs complete.")

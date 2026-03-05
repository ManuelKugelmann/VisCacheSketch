"""
VisCache_Ablation.py  —  Automated ablation capture script
Runs all ablation configurations and captures reference frames.

Usage:
    Mogwai.exe --script scripts/VisCache_Ablation.py --scene Bistro_Interior.pyscene

Outputs to: captures/ablation/<config_name>/frame_NNNN.exr
Each config captures kWarmupFrames then kCaptureFrames EXR frames.
"""

import os

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 16    # frames to capture per config
kCaptureDir    = "captures/ablation"

ABLATION_CONFIGS = [
    ("full",         {}),
    ("minus_A",      {"enableDistanceLOD":   False}),
    ("minus_B",      {"enableVarianceGate":  False}),
    ("minus_C",      {"enableWarpReduction": False}),
    ("minus_D",      {"enableDecay":         False}),
    ("minus_E",      {"enablePressureEvict": False}),
    ("minus_AB",     {"enableDistanceLOD":   False, "enableVarianceGate": False}),
    ("finest_only",  {"minLevel": 2, "maxLevel": 2}),
    ("coarsest_only",{"minLevel": 0, "maxLevel": 0}),
    ("no_cache",     {"enableGIRevalidation": False, "enableLightSelection": False}),
]


def build_base_graph():
    """Construct and return the base render graph (VisCache + all passes)."""
    # Import VisCache_Graph without re-adding to Mogwai
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "VisCache_Graph",
        os.path.join(os.path.dirname(__file__), "VisCache_Graph.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_graph_VisCache()


def apply_ablation(graph, config_dict):
    visCache = graph.getPass("VisCache")
    # Reset to full config first
    for attr in ["enableDistanceLOD", "enableVarianceGate", "enableWarpReduction",
                 "enableDecay", "enablePressureEvict", "enableGIRevalidation",
                 "enableLightSelection"]:
        setattr(visCache, attr, True)
    visCache.minLevel = 0
    visCache.maxLevel = 2
    # Apply delta
    for k, v in config_dict.items():
        setattr(visCache, k, v)


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
g = build_base_graph()
m.addGraph(g)

for (name, cfg) in ABLATION_CONFIGS:
    print(f"[VisCache Ablation] Running config: {name}")
    apply_ablation(g, cfg)

    outdir = os.path.join(kCaptureDir, name)
    os.makedirs(outdir, exist_ok=True)
    m.frameCapture.outputDir     = outdir
    m.frameCapture.baseFilename  = name

    # Warm up
    for _ in range(kWarmupFrames):
        renderFrame()

    # Capture
    for i in range(kCaptureFrames):
        m.frameCapture.capture()
        renderFrame()

    print(f"[VisCache Ablation] {name} done — {kCaptureFrames} frames saved to {outdir}")

print("[VisCache Ablation] All configs complete.")

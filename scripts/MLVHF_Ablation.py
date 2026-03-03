"""
MLVHF_Ablation.py  —  Automated ablation capture script
Runs all ablation configurations and captures reference frames.

Usage:
    Mogwai.exe --script scripts/MLVHF_Ablation.py --scene Bistro_Interior.pyscene

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
    """Construct and return the base render graph (VisHashFilter + all passes)."""
    # Import MLVHF_Graph without re-adding to Mogwai
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "MLVHF_Graph",
        os.path.join(os.path.dirname(__file__), "MLVHF_Graph.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_graph_MLVHF()


def apply_ablation(graph, config_dict):
    vhf = graph.getPass("VisHashFilter")
    # Reset to full config first
    for attr in ["enableDistanceLOD", "enableVarianceGate", "enableWarpReduction",
                 "enableDecay", "enablePressureEvict", "enableGIRevalidation",
                 "enableLightSelection"]:
        setattr(vhf, attr, True)
    vhf.minLevel = 0
    vhf.maxLevel = 2
    # Apply delta
    for k, v in config_dict.items():
        setattr(vhf, k, v)


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
g = build_base_graph()
m.addGraph(g)

for (name, cfg) in ABLATION_CONFIGS:
    print(f"[MLVHF Ablation] Running config: {name}")
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

    print(f"[MLVHF Ablation] {name} done — {kCaptureFrames} frames saved to {outdir}")

print("[MLVHF Ablation] All configs complete.")

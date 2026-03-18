"""
VisCache_Ablation.py  —  Automated ablation capture script
Runs all ablation configurations and captures reference frames.

Usage:
    Mogwai.exe --script scripts/VisCache_Ablation.py --scene BistroInterior.pyscene

Outputs to: captures/ablation/<config_name>/frame_NNNN.exr
Each config captures kWarmupFrames then kCaptureFrames EXR frames.
"""

import os
import json

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 16    # frames to capture per config
kCaptureDir    = "captures/ablation"

ABLATION_CONFIGS = [
    ("full",         {}),
    ("minus_B",      {"enableVisCacheVarianceGate":  False}),
    ("minus_C",      {"enableVisCacheWarpReduction": False}),
    ("minus_D",      {"enableVisCacheDecay":         False}),
    ("minus_E",      {"enableVisCachePressureEvict": False}),
    ("minus_F",      {"enableVisCacheJitter":        False}),
    ("single_level", {"numLevels": 1}),
    ("no_cache",     {"enableVisCacheVisibilityCheck": False, "enableVisCacheLightSelection": False}),
]

# Load render_graph_ReSTIRPT into this namespace
_graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ReSTIRPT_Graph.py")
with open(_graph_path, "r") as _f:
    exec(compile(_f.read(), _graph_path, "exec"))

# ---------------------------------------------------------------------------
# Main capture loop — fresh graph per config (properties set at construction)
# ---------------------------------------------------------------------------
stats_log = []

for (name, cfg) in ABLATION_CONFIGS:
    print(f"[VisCache Ablation] Running config: {name}")

    g = render_graph_ReSTIRPT(viscache=True, ablation=cfg)
    m.addGraph(g)

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
    stats_log.append({"config": name})
    m.removeGraph(g)

# Write stats JSON
stats_path = os.path.join(kCaptureDir, "stats.json")
with open(stats_path, "w") as f:
    json.dump(stats_log, f, indent=2)
print(f"[VisCache Ablation] Stats written to {stats_path}")
print("[VisCache Ablation] All configs complete.")

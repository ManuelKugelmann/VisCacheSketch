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
    ("single_level", {"numLevels": 1}),
    ("no_cache",     {"enableVisCacheRevalidation": False, "enableVisCacheLightSelection": False}),
]


def build_base_graph():
    """Construct and return the base render graph (VisCache + all passes)."""
    # Import ReSTIRPT_Graph without re-adding to Mogwai
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "ReSTIRPT_Graph",
        os.path.join(os.path.dirname(__file__), "ReSTIRPT_Graph.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_graph_ReSTIRPT(viscache=True)


def apply_ablation(graph, config_dict):
    visCache = graph.getPass("VisCache")
    # Reset to full config first
    for attr in ["enableVisCacheVarianceGate",
                 "enableVisCacheWarpReduction", "enableVisCacheDecay",
                 "enableVisCachePressureEvict", "enableVisCacheRevalidation",
                 "enableVisCacheLightSelection"]:
        setattr(visCache, attr, True)
    visCache.numLevels = 3
    visCache.resetAccum = True  # clear per-pixel accumulators for new config
    # Apply delta
    for k, v in config_dict.items():
        setattr(visCache, k, v)


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
g = build_base_graph()
m.addGraph(g)
stats_log = []

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

    # Read back stats
    vc = g.getPass("VisCache")
    ray_pct  = getattr(vc, "raySavings", 0.0) * 100.0
    hit_pct  = getattr(vc, "hitRate", 0.0) * 100.0
    evict_rt = getattr(vc, "evictRate", 0.0)
    print(f"[VisCache Ablation] {name} done — {kCaptureFrames} frames saved to {outdir}")
    print(f"[VisCache Ablation]   rays saved: {ray_pct:.1f}%  hit rate: {hit_pct:.1f}%  evict rate: {evict_rt:.3f}")

    stats_log.append({
        "config":      name,
        "raySavedPct": round(ray_pct, 2),
        "hitRatePct":  round(hit_pct, 2),
        "evictRate":   round(evict_rt, 4),
    })

# Write stats JSON
stats_path = os.path.join(kCaptureDir, "stats.json")
with open(stats_path, "w") as f:
    json.dump(stats_log, f, indent=2)
print(f"[VisCache Ablation] Stats written to {stats_path}")

print("[VisCache Ablation] All configs complete.")

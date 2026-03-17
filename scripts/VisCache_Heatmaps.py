"""
VisCache_Heatmaps.py  —  Automated heatmap capture for paper figures

Captures false-color heatmap images for each diagnostic mode, optionally
crossed with ablation configs for side-by-side comparison figures.

Usage:
    Mogwai.exe --script scripts/VisCache_Heatmaps.py --scene BistroInterior.pyscene

Outputs:
    captures/heatmaps/<ablation>/<mode>/frame_NNNN.exr

Each (ablation, mode) pair: warm up kWarmupFrames, then capture kCaptureFrames.
The ColorMapPass channel is switched automatically per mode.
"""

import os
import json

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 4     # frames to capture per config
kCaptureDir    = "captures/heatmaps"

# Heatmap modes: (name, diagMode uint, colormap source, channel)
#   diagMode matches VisCache::DiagMode enum
#   source: "diag" = vcDiag (RGBA), "error" = vcDiagError (R),
#           "composite" = vcDiagComposite (pre-normalized RGB, no ColorMapPass)
HEATMAP_MODES = [
    ("ray_saved_pct",    1, "ray_pct",    -1),  # per-pixel accumulated ray savings %
    ("noise",            1, "noise",      -1),  # per-pixel noise estimate (variance EMA)
    ("prediction_error", 5, "error",       0),  # |mu - V|
    ("composite_level",  1, "composite",  -1),  # RGB = var/maturity/level
    ("composite_mu",     1, "composite2", -1),  # RGB = var/maturity/mu
]

# Ablation configs to cross with heatmap modes.
# Set to [("full", {})] for just the default config.
ABLATION_CONFIGS = [
    ("full",     {}),
    ("no_cache", {"enableVisCacheRevalidation": False, "enableVisCacheLightSelection": False}),
]


def build_base_graph():
    """Construct the base render graph via ReSTIRPT_Graph(viscache=True)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ReSTIRPT_Graph",
        os.path.join(os.path.dirname(__file__), "ReSTIRPT_Graph.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_graph_ReSTIRPT(viscache=True)


def reset_viscache(graph):
    """Reset VisCache to full-feature defaults."""
    vc = graph.getPass("VisCache")
    for attr in ["enableVisCacheVarianceGate", "enableVisCacheWarpReduction",
                 "enableVisCacheDecay", "enableVisCachePressureEvict",
                 "enableVisCacheRevalidation", "enableVisCacheLightSelection"]:
        setattr(vc, attr, True)
    vc.numLevels = 3


def apply_ablation(graph, config_dict):
    """Apply ablation delta on top of full defaults."""
    reset_viscache(graph)
    vc = graph.getPass("VisCache")
    vc.resetAccum = True  # clear per-pixel accumulators for new config
    for k, v in config_dict.items():
        setattr(vc, k, v)


def set_heatmap_mode(graph, diag_mode, source, channel):
    """Configure VisCache diagnostics and ColorMapPass channel."""
    vc = graph.getPass("VisCache")
    vc.diagMode = diag_mode
    vc.enableDiagnostics = (diag_mode != 0)

    if source == "error":
        hm = graph.getPass("HeatmapError")
        hm.channel = channel
    # ray_pct, noise, composite sources are direct outputs — no ColorMapPass config needed


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
g = build_base_graph()
m.addGraph(g)

total = len(ABLATION_CONFIGS) * len(HEATMAP_MODES)
current = 0
stats_log = []  # collected per-config stats for JSON export

for (abl_name, abl_cfg) in ABLATION_CONFIGS:
    apply_ablation(g, abl_cfg)

    for (mode_name, diag_mode, source, channel) in HEATMAP_MODES:
        current += 1
        tag = f"{abl_name}/{mode_name}"
        print(f"[VisCache Heatmaps] ({current}/{total}) {tag}")

        set_heatmap_mode(g, diag_mode, source, channel)

        outdir = os.path.join(kCaptureDir, abl_name, mode_name)
        os.makedirs(outdir, exist_ok=True)
        m.frameCapture.outputDir    = outdir
        m.frameCapture.baseFilename = f"{abl_name}_{mode_name}"

        # Warm up (cache convergence)
        for _ in range(kWarmupFrames):
            renderFrame()

        # Capture
        for _ in range(kCaptureFrames):
            m.frameCapture.capture()
            renderFrame()

        # Read back stats from VisCache (updated every 16 frames, ~4-frame delay)
        vc = g.getPass("VisCache")
        ray_pct  = getattr(vc, "raySavings", 0.0) * 100.0
        hit_pct  = getattr(vc, "hitRate", 0.0) * 100.0
        evict_rt = getattr(vc, "evictRate", 0.0)
        print(f"[VisCache Heatmaps]   -> {kCaptureFrames} frames saved to {outdir}")
        print(f"[VisCache Heatmaps]      rays saved: {ray_pct:.1f}%  hit rate: {hit_pct:.1f}%  evict rate: {evict_rt:.3f}")

        stats_log.append({
            "ablation":    abl_name,
            "mode":        mode_name,
            "raySavedPct": round(ray_pct, 2),
            "hitRatePct":  round(hit_pct, 2),
            "evictRate":   round(evict_rt, 4),
        })

# Write stats JSON alongside captures
stats_path = os.path.join(kCaptureDir, "stats.json")
with open(stats_path, "w") as f:
    json.dump(stats_log, f, indent=2)
print(f"[VisCache Heatmaps] Stats written to {stats_path}")

# Reset to normal rendering
vc = g.getPass("VisCache")
vc.diagMode = 0
vc.enableDiagnostics = False

print(f"[VisCache Heatmaps] All {total} configs complete.")

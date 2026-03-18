"""
VisCache_Heatmaps.py  —  Automated heatmap capture for paper figures

Captures false-color heatmap images for each diagnostic mode, optionally
crossed with ablation configs for side-by-side comparison figures.

Usage:
    Mogwai.exe --script scripts/VisCache_Heatmaps.py --scene BistroInterior.pyscene

Outputs:
    captures/heatmaps/<ablation>/<mode>/frame_NNNN.exr

Each (ablation, mode) pair: warm up kWarmupFrames, then capture kCaptureFrames.
"""

import os
import json

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 4     # frames to capture per config
kCaptureDir    = "captures/heatmaps"

# Heatmap modes: (name, diagMode uint, colormap source, channel)
HEATMAP_MODES = [
    ("ray_saved_pct",    1, "ray_pct",    -1),
    ("noise",            1, "noise",      -1),
    ("prediction_error", 5, "error",       0),
    ("composite_level",  1, "composite",  -1),
    ("composite_mu",     1, "composite2", -1),
]

# Ablation configs to cross with heatmap modes.
ABLATION_CONFIGS = [
    ("full",     {}),
    ("no_cache", {"enableVisCacheVisibilityCheck": False, "enableVisCacheLightSelection": False}),
]

# Load render_graph_ReSTIRPT into this namespace
_graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ReSTIRPT_Graph.py")
with open(_graph_path, "r") as _f:
    exec(compile(_f.read(), _graph_path, "exec"))

# ---------------------------------------------------------------------------
# Main capture loop — fresh graph per (ablation, mode) pair
# ---------------------------------------------------------------------------
total = len(ABLATION_CONFIGS) * len(HEATMAP_MODES)
current = 0
stats_log = []

for (abl_name, abl_cfg) in ABLATION_CONFIGS:
    for (mode_name, diag_mode, source, channel) in HEATMAP_MODES:
        current += 1
        tag = f"{abl_name}/{mode_name}"
        print(f"[VisCache Heatmaps] ({current}/{total}) {tag}")

        # Build fresh graph with ablation + diagnostics enabled at construction
        vc_overrides = dict(abl_cfg)
        vc_overrides["enableDiagnostics"] = (diag_mode != 0)
        vc_overrides["diagMode"] = diag_mode
        g = render_graph_ReSTIRPT(viscache=True, ablation=vc_overrides)
        m.addGraph(g)

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

        print(f"[VisCache Heatmaps]   -> {kCaptureFrames} frames saved to {outdir}")
        stats_log.append({"ablation": abl_name, "mode": mode_name})
        m.removeGraph(g)

# Write stats JSON alongside captures
stats_path = os.path.join(kCaptureDir, "stats.json")
with open(stats_path, "w") as f:
    json.dump(stats_log, f, indent=2)
print(f"[VisCache Heatmaps] Stats written to {stats_path}")
print(f"[VisCache Heatmaps] All {total} configs complete.")

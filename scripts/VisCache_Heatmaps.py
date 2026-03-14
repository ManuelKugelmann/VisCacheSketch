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

kWarmupFrames  = 200   # frames before capture — allow cache to warm
kCaptureFrames = 4     # frames to capture per config
kCaptureDir    = "captures/heatmaps"

# Heatmap modes: (name, diagMode uint, colormap source, channel)
#   diagMode matches VisCache::DiagMode enum
#   source: "diag" = vcDiag (RGBA), "error" = vcDiagError (R),
#           "composite" = vcDiagComposite (pre-normalized RGB, no ColorMapPass)
HEATMAP_MODES = [
    ("cached_mu",        1, "diag",       0),   # R = visibility prediction [0,1]
    ("variance",         2, "diag",       1),   # G = cache uncertainty [0,0.25]
    ("lod_level",        3, "diag",       2),   # B = LOD level+1 (0=miss)
    ("rays_saved",       4, "diag",       3),   # A = 1=skipped, 0=traced
    ("prediction_error", 5, "error",      0),   # R = |mu - V|
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
    """Construct the base render graph via VisCache_Graph."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "VisCache_Graph",
        os.path.join(os.path.dirname(__file__), "VisCache_Graph.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_graph_VisCache()


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
    for k, v in config_dict.items():
        setattr(vc, k, v)


def set_heatmap_mode(graph, diag_mode, source, channel):
    """Configure VisCache diagnostics and ColorMapPass channel."""
    vc = graph.getPass("VisCache")
    vc.diagMode = diag_mode
    vc.enableDiagnostics = (diag_mode != 0)

    # Set the appropriate ColorMapPass channel (composite is direct RGB, no ColorMapPass)
    if source == "diag":
        hm = graph.getPass("HeatmapDiag")
        hm.channel = channel
    elif source == "error":
        hm = graph.getPass("HeatmapError")
        hm.channel = channel
    # "composite" needs no ColorMapPass — vcDiagComposite is already pre-normalized RGB


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------
g = build_base_graph()
m.addGraph(g)

total = len(ABLATION_CONFIGS) * len(HEATMAP_MODES)
current = 0

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

        print(f"[VisCache Heatmaps]   -> {kCaptureFrames} frames saved to {outdir}")

# Reset to normal rendering
vc = g.getPass("VisCache")
vc.diagMode = 0
vc.enableDiagnostics = False

print(f"[VisCache Heatmaps] All {total} configs complete.")

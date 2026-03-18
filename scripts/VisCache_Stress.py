"""
VisCache_Stress.py  —  Disocclusion stress test.
Fast camera flythrough to measure cold-start recovery.

Usage:
    Mogwai.exe --headless --script scripts/VisCache_Stress.py --scene BistroInterior.pyscene

Outputs to: captures/stress/<config>/frame_NNNN.exr
Captures every frame (no warmup) to track convergence from cold start.

Metrics to extract from captured sequence:
  - Frames to 80% cache hit rate post-disocclusion
  - Variance spike duration (frames with MSE > 2x steady-state)
  - Peak shadow ray ratio during cold-start period
"""

import os
import math

kFlythroughFrames = 300   # total frames for flythrough
kCaptureDir       = "captures/stress"

# Camera keyframes: positions for a room traversal
CAMERA_WAYPOINTS = [
    (0.0,  1.6,  0.0,   5.0,  1.6,  0.0),
    (5.0,  1.6,  0.0,   5.0,  1.6, -5.0),
    (5.0,  1.6, -5.0,   0.0,  1.6, -5.0),
    (0.0,  1.6, -5.0,   0.0,  1.6,  0.0),
]


def lerp(a, b, t):
    return a + (b - a) * t


def get_camera_at_frame(frame, total_frames):
    """Interpolate camera position/target along waypoints."""
    num_segments = len(CAMERA_WAYPOINTS)
    t_global = frame / total_frames * num_segments
    segment = min(int(t_global), num_segments - 1)
    t_local = t_global - segment

    wp = CAMERA_WAYPOINTS[segment]
    wp_next = CAMERA_WAYPOINTS[segment + 1] if segment + 1 < num_segments else wp

    pos = (lerp(wp[0], wp_next[0], t_local),
           lerp(wp[1], wp_next[1], t_local),
           lerp(wp[2], wp_next[2], t_local))
    tgt = (lerp(wp[3], wp_next[3], t_local),
           lerp(wp[4], wp_next[4], t_local),
           lerp(wp[5], wp_next[5], t_local))
    return pos, tgt


# Load render_graph_ReSTIRPT into this namespace
_graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ReSTIRPT_Graph.py")
with open(_graph_path, "r") as _f:
    exec(compile(_f.read(), _graph_path, "exec"))

# ---------------------------------------------------------------------------
# Stress test configs — fresh graph per config
# ---------------------------------------------------------------------------
CONFIGS = [
    ("full_viscache", {}),
    ("no_cache",      {"enableVisCacheVisibilityCheck": False, "enableVisCacheLightSelection": False}),
]

for (name, overrides) in CONFIGS:
    print(f"[Stress] Running flythrough: {name}")

    g = render_graph_ReSTIRPT(viscache=True, ablation=overrides)
    m.addGraph(g)

    outdir = os.path.join(kCaptureDir, name)
    os.makedirs(outdir, exist_ok=True)
    m.frameCapture.outputDir    = outdir
    m.frameCapture.baseFilename = name

    # Warmup frame to compile the graph before capture
    renderFrame()

    for frame in range(kFlythroughFrames):
        pos, tgt = get_camera_at_frame(frame, kFlythroughFrames)
        try:
            cam = m.scene.camera
            cam.position = float3(*pos)
            cam.target   = float3(*tgt)
        except Exception:
            pass

        m.frameCapture.capture()
        renderFrame()

    m.removeGraph(g)
    print(f"[Stress] {name} done — {kFlythroughFrames} frames saved to {outdir}")

print("[Stress] All stress test configs complete.")

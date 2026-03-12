"""
VisCache_Stress.py  —  Disocclusion stress test.
Fast camera flythrough to measure cold-start recovery.

Usage:
    Mogwai.exe --headless --script scripts/VisCache_Stress.py --scene Bistro_Interior.pyscene

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
# These are relative — actual positions depend on scene scale.
# The flythrough moves the camera linearly between waypoints.
CAMERA_WAYPOINTS = [
    # (position_x, position_y, position_z, target_x, target_y, target_z)
    (0.0,  1.6,  0.0,   5.0,  1.6,  0.0),   # start: looking forward
    (5.0,  1.6,  0.0,   5.0,  1.6, -5.0),   # turn corner
    (5.0,  1.6, -5.0,   0.0,  1.6, -5.0),   # look across room
    (0.0,  1.6, -5.0,   0.0,  1.6,  0.0),   # return to start area
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
    if segment + 1 < num_segments:
        wp_next = CAMERA_WAYPOINTS[segment + 1]
    else:
        wp_next = CAMERA_WAYPOINTS[segment]

    pos = (lerp(wp[0], wp_next[0], t_local),
           lerp(wp[1], wp_next[1], t_local),
           lerp(wp[2], wp_next[2], t_local))
    tgt = (lerp(wp[3], wp_next[3], t_local),
           lerp(wp[4], wp_next[4], t_local),
           lerp(wp[5], wp_next[5], t_local))
    return pos, tgt


# ---------------------------------------------------------------------------
# Build graph: full VisCache + ReSTIR PT (same as VisCache_Graph baseline)
# ---------------------------------------------------------------------------
import importlib.util, sys

spec = importlib.util.spec_from_file_location(
    "VisCache_Graph",
    os.path.join(os.path.dirname(__file__), "VisCache_Graph.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
g = mod.render_graph_VisCache()
m.addGraph(g)

# ---------------------------------------------------------------------------
# Capture: every frame, with camera animation
# ---------------------------------------------------------------------------
CONFIGS = [
    ("full_viscache", {}),
    ("no_cache",      {"enableVisCacheRevalidation": False, "enableVisCacheLightSelection": False}),
]

for (name, overrides) in CONFIGS:
    print(f"[Stress] Running flythrough: {name}")

    # Apply config
    visCache = g.getPass("VisCache")
    # Reset to full
    for attr in ["enableVisCacheVarianceGate",
                 "enableVisCacheWarpReduction", "enableVisCacheDecay",
                 "enableVisCachePressureEvict", "enableVisCacheRevalidation",
                 "enableVisCacheLightSelection"]:
        setattr(visCache, attr, True)
    visCache.numLevels = 3
    for k, v in overrides.items():
        setattr(visCache, k, v)

    outdir = os.path.join(kCaptureDir, name)
    os.makedirs(outdir, exist_ok=True)
    m.frameCapture.outputDir    = outdir
    m.frameCapture.baseFilename = name

    for frame in range(kFlythroughFrames):
        # Animate camera
        pos, tgt = get_camera_at_frame(frame, kFlythroughFrames)
        try:
            cam = m.scene.camera
            cam.position = float3(*pos)
            cam.target   = float3(*tgt)
        except Exception:
            pass  # Scene may not have a controllable camera

        m.frameCapture.capture()
        renderFrame()

    print(f"[Stress] {name} done — {kFlythroughFrames} frames saved to {outdir}")

print("[Stress] All stress test configs complete.")

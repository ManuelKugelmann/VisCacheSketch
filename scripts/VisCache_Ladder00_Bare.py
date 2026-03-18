"""
VisCache_Ladder00_Bare.py — Step 0: Bare minimum cache.

1 level, no jitter, pMin=1.0 (always trace, never skip rays),
no variance gate, no decay, no eviction.
Tests: hash insert + lookup + diagnostic write at the simplest setting.

Expected output: blocky grid on vcVarMaturityLevel, uniform mu per cell,
full coverage (every NEE pixel should have data).
"""
import os, sys, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer

kWarmupFrames = 64
kCaptureDir   = "captures/ladder/00_bare"

# Override defaults for bare minimum config
overrides = {
    "numLevels": 1,
    "pMin": 1.0,             # always trace — no RR skipping
    "enableVisCacheJitter": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}

# Apply overrides
saved = {}
for k, v in overrides.items():
    if k in VISCACHE_DEFAULTS:
        saved[k] = VISCACHE_DEFAULTS[k]
    VISCACHE_DEFAULTS[k] = v

g = render_graph_PathTracer(viscache=True)

# Restore defaults
for k, v in saved.items():
    VISCACHE_DEFAULTS[k] = v
for k in overrides:
    if k not in saved and k in VISCACHE_DEFAULTS:
        del VISCACHE_DEFAULTS[k]

m.addGraph(g)

scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")
m.loadScene(scene_file)

os.makedirs(kCaptureDir, exist_ok=True)
fc.outputDir = kCaptureDir
fc.baseFilename = "bare"

print(f"[ladder-00] Scene: {scene_file}")
print(f"[ladder-00] Config: 1 level, no jitter, pMin=1.0, all ablations OFF")
print(f"[ladder-00] Warmup: {kWarmupFrames} frames")

for _ in range(kWarmupFrames):
    m.renderFrame()

fc.capture()
m.renderFrame()

print(f"[ladder-00] Captured to {kCaptureDir}/")

# Convert EXR to PNG
import glob
for exr in glob.glob(os.path.join(kCaptureDir, "*.exr")):
    png = exr.replace(".exr", ".png")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", exr, "-pix_fmt", "rgb24", png],
                       capture_output=True, timeout=10)
        print(f"[ladder-00] Converted {os.path.basename(png)}")
    except Exception:
        pass

exit()

"""
VisCache_Debug.py — Debug capture script for VisCache diagnostics.

Captures rendered image + diagnostic heatmaps with jitter DISABLED
so cache cell structure is clearly visible in the output.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Debug.py

Outputs to: captures/debug/
"""
import os

kWarmupFrames = 64
kCaptureDir   = "captures/debug"

# Load render_graph_PathTracer into this namespace
_graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PathTracer_Graph.py")
with open(_graph_path, "r") as _f:
    exec(compile(_f.read(), _graph_path, "exec"))

# Build PathTracer graph with VisCache, jitter disabled to show cell structure.
# Import VISCACHE_DEFAULTS and override jitter before graph creation.
from viscache_defaults import VISCACHE_DEFAULTS
_savedA = VISCACHE_DEFAULTS["enableVisCacheJitterA"]
_savedB = VISCACHE_DEFAULTS["enableVisCacheJitterB"]
VISCACHE_DEFAULTS["enableVisCacheJitterA"] = False
VISCACHE_DEFAULTS["enableVisCacheJitterB"] = False
g = render_graph_PathTracer(viscache=True)
VISCACHE_DEFAULTS["enableVisCacheJitterA"] = _savedA
VISCACHE_DEFAULTS["enableVisCacheJitterB"] = _savedB

m.addGraph(g)

# Load scene
scene_file = os.environ.get("SCENE_FILE", "data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene")
m.loadScene(scene_file)

# Configure capture
os.makedirs(kCaptureDir, exist_ok=True)
fc.outputDir = kCaptureDir
fc.baseFilename = "debug_nojitter"

print(f"[debug] Scene: {scene_file}")
print(f"[debug] Jitter: OFF (showing cell structure)")
print(f"[debug] Warmup: {kWarmupFrames} frames")

# Warmup
for _ in range(kWarmupFrames):
    m.renderFrame()

# Capture all marked graph outputs.
fc.outputDir = kCaptureDir
fc.baseFilename = "debug_nojitter"
fc.capture()
m.renderFrame()

print(f"[debug] Captured to {kCaptureDir}/")

# Convert EXR composites to PNG via ffmpeg if available
import subprocess, glob
for exr in glob.glob(os.path.join(kCaptureDir, "*.exr")):
    png = exr.replace(".exr", ".png")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", exr, "-pix_fmt", "rgb24", png],
                       capture_output=True, timeout=10)
        print(f"[debug] Converted {os.path.basename(exr)} -> .png")
    except Exception:
        print(f"[debug] ffmpeg not available, skipping EXR->PNG conversion")
        break

exit()

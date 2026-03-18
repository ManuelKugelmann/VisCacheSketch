"""
capture_gallery.py — Capture a test image from a graph script after N warmup frames.

Usage:
    set GRAPH_SCRIPT=scripts/VisCache/ReSTIRPT_Graph.py
    set GALLERY_DIR=C:/Projects/VisCacheSketch/.tests
    set SCENE_FILE=data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene
    set WARMUP_FRAMES=64
    Mogwai.exe --headless -s scripts/VisCache/capture_gallery.py

Env vars:
    GRAPH_SCRIPT    — graph script to load (required)
    GALLERY_DIR     — output directory for images (required)
    SCENE_FILE      — scene to load (required)
    WARMUP_FRAMES   — frames to render before capture (default: 64)
    CAPTURE_NAME    — base filename for the capture (auto-derived if unset)

NOTE: The scene MUST be loaded inside this script via m.loadScene(), not via
Mogwai's -S flag. Mogwai loads -S AFTER the -s script finishes, but this
script renders frames during execution — so -S would be too late.

For VisCache variants, all marked graph outputs are captured — this includes
diagnostic heatmaps (prediction error, ray savings, noise, composites).
"""
import os, sys

graph_script = os.environ.get("GRAPH_SCRIPT")
gallery_dir = os.environ.get("GALLERY_DIR")
scene_file = os.environ.get("SCENE_FILE")
warmup = int(os.environ.get("WARMUP_FRAMES", "64"))

if not graph_script:
    print("[capture] ERROR: GRAPH_SCRIPT env var not set")
    exit()
if not gallery_dir:
    print("[capture] ERROR: GALLERY_DIR env var not set")
    exit()
if not scene_file:
    print("[capture] ERROR: SCENE_FILE env var not set")
    exit()

# Derive capture name from script filename: ReSTIRPT_VisCache_Graph.py -> ReSTIRPT_VisCache
capture_name = os.environ.get("CAPTURE_NAME", "")
if not capture_name:
    base = os.path.splitext(os.path.basename(graph_script))[0]
    capture_name = base.replace("_Graph", "")

is_viscache = "VisCache" in capture_name

print(f"[capture] Graph: {graph_script}")
print(f"[capture] Scene: {scene_file}")
print(f"[capture] Output: {gallery_dir}/{capture_name}.*")
print(f"[capture] Warmup: {warmup} frames")
if is_viscache:
    print(f"[capture] VisCache variant — diagnostics + heatmaps will be captured")

# Load the graph script (adds graph to Mogwai via m.addGraph())
with open(graph_script, "r") as f:
    exec(f.read())

# Load scene — must happen AFTER graph is added, BEFORE rendering
m.loadScene(scene_file)

# Configure frame capture (fc = Mogwai's FrameCapture extension)
# fc.capture() captures ALL marked graph outputs — for VisCache variants this
# includes HeatmapError, HeatmapRaySavedPct, HeatmapNoise, and composites.
os.makedirs(gallery_dir, exist_ok=True)
fc.outputDir = gallery_dir
fc.baseFilename = capture_name

# Warmup: render frames to let accumulation converge
for i in range(warmup):
    m.renderFrame()

# Capture the final frame (all marked outputs)
fc.capture()
m.renderFrame()  # flush capture

outputs = [capture_name]
if is_viscache:
    outputs += [
        f"{capture_name}.HeatmapError",
        f"{capture_name}.HeatmapRaySavedPct",
        f"{capture_name}.HeatmapNoise",
        f"{capture_name}.vcVarMaturityLevel",
        f"{capture_name}.vcVarMaturityMu",
    ]
print(f"[capture] Done — captured {len(outputs)} output(s) to {gallery_dir}/")
for o in outputs:
    print(f"[capture]   {o}")
exit()

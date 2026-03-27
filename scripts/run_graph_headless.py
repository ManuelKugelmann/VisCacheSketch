"""
run_graph_headless.py — Generic headless test: load a graph script, render N frames, exit.

Usage:
    set GRAPH_SCRIPT=scripts/VisCache/MinimalPathTracer_Graph.py
    set SCENE_FILE=CornellBox_1AreaLight.pyscene
    Mogwai.exe --headless -s scripts/VisCache/run_graph_headless.py

NOTE: The scene MUST be loaded inside this script via m.loadScene(), not via
Mogwai's --scene flag. Mogwai loads --scene AFTER the script finishes, but this
script renders frames during execution — so --scene would be too late.
"""
import os, sys

project_root = os.environ.get("PROJECT_ROOT", "")

graph_script = os.environ.get("GRAPH_SCRIPT", "scripts/VisCache/MinimalPathTracer_Graph.py")
scene_file = os.environ.get("SCENE_FILE", "data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene")
num_frames = int(os.environ.get("NUM_FRAMES", "2"))

# Resolve scene: check project scenes/ directory first, then fall through to Mogwai paths
if project_root and not os.path.isabs(scene_file):
    candidate = os.path.join(project_root, "scenes", scene_file)
    if os.path.isfile(candidate):
        scene_file = candidate

print(f"[headless] Loading graph: {graph_script}")

# Execute the graph script in our current globals (which has m, RenderGraph, createPass, etc.)
# Ladder scripts call exit() when done — they handle their own scene loading and rendering.
# Simple graph scripts (e.g. PathTracer_Graph.py) just add a graph and return, so we
# load the scene and render frames for them below.
_HEADLESS_SCRIPT_DONE = False  # Ladder scripts set this to True when they handle their own rendering
with open(graph_script, "r") as f:
    exec(f.read())

if not _HEADLESS_SCRIPT_DONE:
    # Load scene — must happen AFTER graph is added, BEFORE rendering
    print(f"[headless] Loading scene: {scene_file}")
    m.loadScene(scene_file)

    print(f"[headless] Rendering {num_frames} frames...")
    for i in range(num_frames):
        m.renderFrame()

    print(f"[headless] OK — rendered {num_frames} frames.")

exit()

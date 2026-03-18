"""
run_graph_headless.py — Generic headless test: load a graph script, render N frames, exit.

Usage:
    set GRAPH_SCRIPT=scripts/VisCache/MinimalPathTracer_Graph.py
    set SCENE_FILE=data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene
    Mogwai.exe --headless -s scripts/VisCache/run_graph_headless.py

NOTE: The scene MUST be loaded inside this script via m.loadScene(), not via
Mogwai's --scene flag. Mogwai loads --scene AFTER the script finishes, but this
script renders frames during execution — so --scene would be too late.
"""
import os, sys

graph_script = os.environ.get("GRAPH_SCRIPT", "scripts/VisCache/MinimalPathTracer_Graph.py")
scene_file = os.environ.get("SCENE_FILE", "data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene")
num_frames = int(os.environ.get("NUM_FRAMES", "2"))

print(f"[headless] Loading graph: {graph_script}")

# Execute the graph script in our current globals (which has m, RenderGraph, createPass, etc.)
with open(graph_script, "r") as f:
    exec(f.read())

# Load scene — must happen AFTER graph is added, BEFORE rendering
print(f"[headless] Loading scene: {scene_file}")
m.loadScene(scene_file)

print(f"[headless] Rendering {num_frames} frames...")
for i in range(num_frames):
    m.renderFrame()

print(f"[headless] OK — rendered {num_frames} frames.")
exit()

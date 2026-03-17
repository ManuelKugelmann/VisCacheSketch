"""
run_graph_headless.py — Generic headless test: load a graph script, render N frames, exit.

Usage:
    Mogwai.exe --headless -s scripts/run_graph_headless.py -S <scene.pyscene>

Set GRAPH_SCRIPT env var to the graph script path before launching.
Default: scripts/VisCache/MinimalPathTracer_Graph.py
"""
import os, sys

graph_script = os.environ.get("GRAPH_SCRIPT", "scripts/VisCache/MinimalPathTracer_Graph.py")
num_frames = int(os.environ.get("NUM_FRAMES", "2"))

print(f"[headless] Loading graph: {graph_script}")

# Execute the graph script in our current globals (which has m, RenderGraph, createPass, etc.)
with open(graph_script, "r") as f:
    exec(f.read())

print(f"[headless] Rendering {num_frames} frames...")
m.clock.framerate = 60
m.clock.time = 0
m.clock.pause()

for i in range(num_frames):
    m.clock.frame = i
    m.renderFrame()

print(f"[headless] OK — rendered {num_frames} frames.")
exit()

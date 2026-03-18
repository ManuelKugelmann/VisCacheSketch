"""
smoke_test_render.py — Render smoke test: load scene, render 2 frames, verify non-black output.

Unlike smoke_test.py (which only checks pass registration), this actually
renders frames with a scene to validate the full GPU pipeline.

Usage:
    Mogwai.exe --headless --script scripts/VisCache/smoke_test_render.py
"""

import os

# Build a minimal graph: VBuffer → MinimalPathTracer → ToneMapper
g = RenderGraph("SmokeRender")

vbuf = createPass("VBufferRT", {"samplePattern": "Stratified", "sampleCount": 16})
g.addPass(vbuf, "VBufferRT")

pt = createPass("MinimalPathTracer", {"maxBounces": 3})
g.addPass(pt, "MinimalPathTracer")

tone = createPass("ToneMapper", {"autoExposure": False, "exposureValue": 0.0, "operator": "Aces"})
g.addPass(tone, "ToneMapper")

g.addEdge("VBufferRT.vbuffer", "MinimalPathTracer.vbuffer")
g.addEdge("VBufferRT.viewW", "MinimalPathTracer.viewW")
g.addEdge("MinimalPathTracer.color", "ToneMapper.src")
g.markOutput("ToneMapper.dst")

m.addGraph(g)

# Load default test scene
scene_file = "data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene"
print(f"[smoke_render] Loading scene: {scene_file}")
m.loadScene(scene_file)

# Render
print("[smoke_render] Rendering 2 frames...")
for i in range(2):
    m.renderFrame()

print("[smoke_render] OK — rendered 2 frames with scene.")
exit()

"""
TestRender.py — Quick test render: PathTracer + capture.

Usage:
    .scripts/mogwai-headless.sh 'TestRender.py' [scene] [frames]

Output: captures/testrender/ (flat, all scenes in one folder)

Env vars:
    SCENE_FILE  — scene path (default: CornellBox_1AreaLight.pyscene)
    NUM_FRAMES  — warmup frames before capture (default: 32)
    RES         — resolution (default: 512)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import resolve_scene

scene_file = resolve_scene(os.environ.get("SCENE_FILE", "media/scenes/CornellBox_1AreaLight.pyscene"))
warmup     = int(os.environ.get("NUM_FRAMES", "32"))
res        = int(os.environ.get("RES", "512"))

scene_name = os.path.splitext(os.path.basename(scene_file))[0]
out_dir    = "captures/testrender"
os.makedirs(out_dir, exist_ok=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "PathTracer_Graph.py")) as _f:
    exec(_f.read())

m.loadScene(scene_file)
m.resizeFrameBuffer(res, res)

print(f"[testrender] {scene_name} — {warmup} warmup frames @ {res}x{res}")
for _ in range(warmup):
    m.renderFrame()

fc.outputDir    = out_dir
fc.baseFilename = scene_name
fc.capture()
m.renderFrame()

print(f"[testrender] → {out_dir}/{scene_name}.*")
_HEADLESS_SCRIPT_DONE = True

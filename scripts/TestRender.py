"""
TestRender.py — Quick test render: PathTracer + capture, all scenes in one Mogwai session.

Usage:
    .scripts/mogwai-headless.sh 'TestRender.py'

Output: captures/testrender/ (flat, all scenes in one folder)

Env vars:
    SCENES     — comma-separated scene names (default: VeachAjar + Bistro + Sponza + CornellBox)
    NUM_FRAMES — warmup frames before capture (default: 32)
    SPP        — samples per pixel per frame (default: 1); total samples = NUM_FRAMES * SPP
    RES        — resolution (default: 512)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import resolve_scene

DEFAULT_SCENES = [
    "CornellBox_1AreaLight.pyscene",
    "VeachAjar.pyscene",
    "BistroInterior.pyscene",
    "BistroExterior.pyscene",
    "Sponza.pyscene",
]

scenes_env = os.environ.get("SCENES", "")
scene_names = [s.strip() for s in scenes_env.split(",") if s.strip()] if scenes_env else DEFAULT_SCENES

warmup = int(os.environ.get("NUM_FRAMES", "32"))
spp    = int(os.environ.get("SPP", "1"))
res    = int(os.environ.get("RES", "512"))
out_dir = "captures/testrender"
os.makedirs(out_dir, exist_ok=True)

# Build graph once — reused across all scenes
from PathTracer_Graph import render_graph_PathTracer
g = render_graph_PathTracer(samplesPerPixel=spp)
m.addGraph(g)
m.resizeFrameBuffer(res, res)

for scene_name_raw in scene_names:
    scene_file = resolve_scene(scene_name_raw)
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]

    print(f"\n[testrender] ===== {scene_name} =====")
    m.loadScene(scene_file)

    # Match ladder: prefer VisCacheDefault + freeze animation so testrender
    # output is reproducible and framing matches what ladder measures.
    scene = m.scene
    if scene is not None:
        cameras = getattr(scene, 'cameras', None) or []
        for cam in cameras:
            if getattr(cam, 'name', None) == 'VisCacheDefault':
                scene.camera = cam
                break
        scene.animated = False

    print(f"[testrender] {warmup} warmup frames x {spp} spp @ {res}x{res} ({warmup*spp} total samples)")
    for _ in range(warmup):
        m.renderFrame()

    fc.outputDir    = out_dir
    fc.baseFilename = scene_name
    fc.capture()
    m.renderFrame()

    # Document settings next to each render so the camera and light state
    # can be inspected without rerunning Mogwai.
    try:
        cam = scene.camera
        info = [
            f"scene = {scene_name}",
            f"camera.name = {getattr(cam, 'name', '?')}",
            f"camera.position = {cam.position}",
            f"camera.target   = {cam.target}",
            f"camera.up       = {cam.up}",
            f"camera.focalLength = {cam.focalLength}",
            f"resolution = {res}x{res}",
            f"warmup frames = {warmup}",
            f"spp = {spp}",
            f"animated = {getattr(scene, 'animated', '?')}",
        ]
        with open(os.path.join(out_dir, f"{scene_name}.settings.txt"), "w", encoding="utf-8") as _f:
            _f.write("\n".join(info) + "\n")
    except Exception as _e:
        print(f"[testrender] settings dump failed: {_e}")

    print(f"[testrender] → {out_dir}/{scene_name}.*")

print("\n[testrender] All scenes done.")
_HEADLESS_SCRIPT_DONE = True

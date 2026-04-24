"""Probe camera positions after TestRender.py-equivalent 32 warmup frames
so we can see where the FBX-animated camera lands at capture time. Writes
a dump file so we can copy numbers into .pyscene files.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from falcor import *
except ImportError:
    pass

from VisCache_LadderCommon import resolve_scene
from PathTracer_Graph import render_graph_PathTracer

SCENES = os.environ.get("PROBE_SCENES", "BistroInterior,BistroExterior,Sponza").split(",")
WARMUP = int(os.environ.get("WARMUP", "32"))

g = render_graph_PathTracer(samplesPerPixel=1)
m.addGraph(g)
m.resizeFrameBuffer(512, 512)

out_lines = [f"# Probed after {WARMUP} warmup frames (matches TestRender.py)"]
for scn_name in SCENES:
    scene_file = resolve_scene(scn_name + ".pyscene")
    out_lines.append(f"\n===== {scn_name} =====")
    m.loadScene(scene_file)
    for _ in range(WARMUP):
        m.renderFrame()
    scene = m.scene
    cam = scene.camera
    # Use the pybind-exposed attributes: position, target, up, focalLength
    try:
        p = cam.position
        tgt = cam.target
        up = cam.up
        fl = getattr(cam, 'focalLength', None)
        name = getattr(cam, 'name', '?')
        out_lines.append(f"active camera: {name}")
        out_lines.append(f"camera.position = {p}")
        out_lines.append(f"camera.target   = {tgt}")
        out_lines.append(f"camera.up       = {up}")
        if fl is not None:
            out_lines.append(f"camera.focalLength = {fl}")
    except Exception as e:
        out_lines.append(f"probe error: {e}")

dump = "\n".join(out_lines)
out = Path(__file__).parent.parent / "runtime" / "captures" / "testrender" / "camera_probe.txt"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(dump + "\n")
print(dump)
print(f"\n[probe] wrote {out}")

_HEADLESS_SCRIPT_DONE = True
import os as _os
_os._exit(0)

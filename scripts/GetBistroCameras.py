"""Extract FBX default camera positions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

scenes = [
    "C:/Projects/VisCacheSketch/runtime/media/Bistro/BistroInterior.pyscene",
    "C:/Projects/VisCacheSketch/runtime/media/Bistro/BistroExterior.pyscene",
]

from PathTracer_Graph import render_graph_PathTracer
g = render_graph_PathTracer()
m.addGraph(g)

for s in scenes:
    name = os.path.splitext(os.path.basename(s))[0]
    m.loadScene(s)
    m.renderFrame()
    cam = m.scene.camera
    p, t = cam.position, cam.target
    print(f"[cam] {name}: pos=({p.x:.3f},{p.y:.3f},{p.z:.3f}) tgt=({t.x:.3f},{t.y:.3f},{t.z:.3f}) fl={cam.focalLength:.1f}")

_HEADLESS_SCRIPT_DONE = True

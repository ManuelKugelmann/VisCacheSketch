"""Quality validation for EmissivePdfMipmapSampler.
Renders Cornell_3AreaLights with vanilla PathTracer at x16 spp using both
the new PdfMipmap sampler and Power for comparison. Captures EXRs for
post-process err comparison vs the existing vanilla x4096 ground truth.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py would be cleaner,
    but for a one-off: invoke directly via mogwai-headless.sh and read
    captures/pdfmipmap_test/*.exr after.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

try:
    from falcor import *
except ImportError:
    pass


CAPTURE_DIR = "captures/pdfmipmap_test"
NUM_FRAMES = 16


def _build(sampler_name):
    return render_graph_PathTracer(
        viscache=False,
        wsReservoirs=False,
        maxBounces=0,
        samplesPerPixel=1,
        useJitter=True,
        emissiveSampler=sampler_name,
    )


# RunGraphHeadless uses `_HEADLESS_SCRIPT_DONE` to skip its default render loop.
# We do our own loop here so we can swap samplers between graphs.
_HEADLESS_SCRIPT_DONE = True

scene_file = os.environ.get("SCENE_FILE", "CornellBox_3AreaLights.pyscene")
project_root = os.environ.get("PROJECT_ROOT", "")
if project_root and not os.path.isabs(scene_file):
    candidate = os.path.join(project_root, "scenes", scene_file)
    if os.path.isfile(candidate):
        scene_file = candidate

os.makedirs(CAPTURE_DIR, exist_ok=True)
fc.outputDir = CAPTURE_DIR
m.resizeFrameBuffer(512, 512)

for sampler_name in ["PdfMipmap", "Power", "LightBVH"]:
    print(f"\n[pdfmipmap] === Testing emissiveSampler={sampler_name} ===")
    g = _build(sampler_name)
    m.addGraph(g)
    m.loadScene(scene_file)
    print(f"[pdfmipmap] Rendering {NUM_FRAMES} frames...")
    for i in range(NUM_FRAMES):
        m.renderFrame()
    fc.baseFilename = f"x{NUM_FRAMES}_{sampler_name}"
    fc.capture()
    m.removeGraph(g)
    print(f"[pdfmipmap] Captured: {CAPTURE_DIR}/x{NUM_FRAMES}_{sampler_name}*.exr")

print(f"\n[pdfmipmap] Done. Compare with: viscache_exr.compute_render_error()")
exit()

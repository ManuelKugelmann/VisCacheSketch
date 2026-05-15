"""
compare_nee_quality.py — ad-hoc 3-way quality A/B between vanilla, ReSTIR DI
(without VisCache shadow CV / light-selection), and ReSTIR NEE (K=16).

Run via the mogwai-headless harness:
    .scripts/mogwai-headless.sh compare_nee_quality.py CornellBox_32PointLights.pyscene

The script takes over rendering (`_HEADLESS_SCRIPT_DONE = True`), constructs
each variant graph in turn, renders N frames at the configured SPP, captures
the AccumulatePass HDR EXR, then exits. Post-processing of the EXRs is left
to `compute_nee_quality_metrics.py` so this run stays inside Mogwai.

Output: runtime/captures/nee_quality/<scene>/{vanilla,restirdi,restirnee,gt}_*.exr
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PathTracer_Graph import render_graph_PathTracer
from ReSTIRNEEPass_Graph import render_graph_ReSTIRNEEPass

_HEADLESS_SCRIPT_DONE = True

SCENE = os.environ.get("SCENE_FILE", "CornellBox_32PointLights.pyscene")
PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "")
SPP_LOW = int(os.environ.get("SPP_LOW", "4"))
SPP_GT  = int(os.environ.get("SPP_GT",  "1024"))
FRAMES_LOW = int(os.environ.get("FRAMES_LOW", "4"))
FRAMES_GT  = int(os.environ.get("FRAMES_GT",  "16"))
MAX_BOUNCES = int(os.environ.get("MAX_BOUNCES", "3"))
NEE_K = int(os.environ.get("NEE_K", "16"))

scene_path = SCENE
if PROJECT_ROOT and not os.path.isabs(scene_path):
    candidate = os.path.join(PROJECT_ROOT, "scenes", scene_path)
    if os.path.isfile(candidate):
        scene_path = candidate

scene_name = os.path.splitext(os.path.basename(SCENE))[0]
out_dir = os.path.join("captures", "nee_quality", scene_name)
os.makedirs(out_dir, exist_ok=True)

m.loadScene(scene_path)
print(f"[compare] scene={scene_name}  out={out_dir}")

_active_graph = [None]

def _run(name, graph, frames, spp_label):
    print(f"[compare] === {name} ({spp_label}) ===")
    if _active_graph[0] is not None:
        m.removeGraph(_active_graph[0])
    m.addGraph(graph)
    _active_graph[0] = graph
    fc.outputDir = out_dir
    fc.baseFilename = f"{name}_{spp_label}"
    for _ in range(frames):
        m.renderFrame()
    fc.capture()

# 1. Vanilla low-SPP (upstream PathTracer, no VisCache)
g_vanilla = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                                    samplesPerPixel=SPP_LOW, useJitter=True,
                                    passClassName="PathTracer")
_run("vanilla", g_vanilla, FRAMES_LOW, f"x{SPP_LOW}")

# 2. Vanilla ground truth (high-SPP same path tracer)
g_gt = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                               samplesPerPixel=SPP_GT, useJitter=False,
                               passClassName="PathTracer")
_run("gt", g_gt, FRAMES_GT, f"x{SPP_GT}")

# 3. ReSTIR DI without VisCache shadow CV / light-selection. The
#    PathTracer_Graph still wires VisCache as the buffer host (reservoirs
#    live there), but its in-shader features are off.
g_rdi = render_graph_PathTracer(
    viscache=True, reservoirs=True, useReSTIRDIPass=True,
    maxBounces=MAX_BOUNCES, samplesPerPixel=SPP_LOW, useJitter=True,
    visibilityCheck=False, lightSelection=False,
)
_run("restirdi", g_rdi, FRAMES_LOW, f"x{SPP_LOW}")

# 4. ReSTIR NEE K=16 (no VisCache at all)
g_nee = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                   samplesPerPixel=SPP_LOW, useJitter=True,
                                   numNEECandidates=NEE_K)
_run("restirnee", g_nee, FRAMES_LOW, f"x{SPP_LOW}")

print("[compare] all variants captured.")
exit()

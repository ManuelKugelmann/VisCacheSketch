"""
compare_nee_normalquant.py — NEE K-slot × normalACoarse 45° vs 60°.

Targets the Cornell_32PL cross-surface contamination regime. Tighter
normal binning (45° → ~8 bins instead of 60° → ~6 bins) reduces cells
that mix samples from surfaces with different orientations.

Combined with the now-1px base footprint (kNeeCellBaseFootprintPx=1.0),
this should narrow the cell's spatial+orientation extent enough to
keep K-slot writers compatible. If the contamination is fundamental
(per-pixel visibility variation independent of normal), this won't help
— that's the empirical question.

Run:
    .scripts/mogwai-headless.sh compare_nee_normalquant.py CornellBox_32PointLights.pyscene
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
CELL_FP = int(os.environ.get("CELL_FP", "1"))

scene_path = SCENE
if PROJECT_ROOT and not os.path.isabs(scene_path):
    candidate = os.path.join(PROJECT_ROOT, "scenes", scene_path)
    if os.path.isfile(candidate):
        scene_path = candidate

scene_name = os.path.splitext(os.path.basename(SCENE))[0]
out_dir = os.path.join("captures", "nee_normalquant", scene_name)
os.makedirs(out_dir, exist_ok=True)

m.loadScene(scene_path)
print(f"[compare-nee-normalquant] scene={scene_name}  out={out_dir}")

_active_graph = [None]

def _run(name, graph, frames, spp_label):
    print(f"[compare-nee-normalquant] === {name} ({spp_label}) ===")
    if _active_graph[0] is not None:
        m.removeGraph(_active_graph[0])
    m.addGraph(graph)
    _active_graph[0] = graph
    fc.outputDir = out_dir
    fc.baseFilename = f"{name}_{spp_label}"
    for _ in range(frames):
        m.renderFrame()
    fc.capture()

# Ground truth.
g_gt = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                               samplesPerPixel=SPP_GT, useJitter=True)
_run("gt_x", g_gt, FRAMES_GT, f"x{SPP_GT}")

# Yardstick — pure K-RIS NEE, no cells.
g_yard = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                    samplesPerPixel=SPP_LOW, useJitter=True,
                                    numNEECandidates=NEE_K)
_run("nee_F16", g_yard, FRAMES_LOW, f"x{SPP_LOW}")

# Sweep: normalACoarse ∈ {60, 45} × {K=1 lo=0, K=4 lo=0, K=4 lo=1}.
# K=1 lo=0 isolates "cell reuse with tighter normal" from K-slot effects.
# K=4 lo=0/1 tests if normal-quant tightens enough for K-slot to pay off.
for nq in (60, 45):
    for K, lo in [(1, 0), (4, 0), (4, 1)]:
        g = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                       samplesPerPixel=SPP_LOW, useJitter=True,
                                       numNEECandidates=NEE_K,
                                       useNEECells=True,
                                       cellReservoirFootprintPx=CELL_FP,
                                       reservoirK=K,
                                       cellLevelOffsetWrite=lo,
                                       normalACoarse=nq)
        _run(f"nee_F16R3d_nq{nq}_K{K}lo{lo}_fp{CELL_FP}", g, FRAMES_LOW, f"x{SPP_LOW}")

print("[compare-nee-normalquant] all variants captured.")
exit()

"""
compare_nee_kslot.py — NEE K-slot × step C cascade quality A/B.

Mirrors compare_nee_quality.py's harness but focuses on K-slot variants of
ReSTIR NEE (K=1/4/8) × multi-level cascade offsets (lo=0/1/2). Captures
HDR EXRs for offline metric comparison via compute_nee_quality_metrics.py.

Run via mogwai-headless harness:
    .scripts/mogwai-headless.sh compare_nee_kslot.py CornellBox_32PointLights.pyscene
or:
    .scripts/mogwai-headless.sh compare_nee_kslot.py Sponza.pyscene

Output: runtime/captures/nee_kslot/<scene>/{nee_F16, nee_F16R3d_K{1,4,8}lo{0,1,2}}_*.exr
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
out_dir = os.path.join("captures", "nee_kslot", scene_name)
os.makedirs(out_dir, exist_ok=True)

m.loadScene(scene_path)
print(f"[compare-nee-kslot] scene={scene_name}  out={out_dir}")

_active_graph = [None]

def _run(name, graph, frames, spp_label):
    print(f"[compare-nee-kslot] === {name} ({spp_label}) ===")
    if _active_graph[0] is not None:
        m.removeGraph(_active_graph[0])
    m.addGraph(graph)
    _active_graph[0] = graph
    fc.outputDir = out_dir
    fc.baseFilename = f"{name}_{spp_label}"
    for _ in range(frames):
        m.renderFrame()
    fc.capture()

# Ground truth — vanilla PT at high SPP.
g_gt = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                               samplesPerPixel=SPP_GT, useJitter=True)
_run("gt_x", g_gt, FRAMES_GT, f"x{SPP_GT}")

# F16 pure K-RIS (no reservoir) — yardstick at low SPP.
g_nee = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                   samplesPerPixel=SPP_LOW, useJitter=True,
                                   numNEECandidates=NEE_K)
_run("nee_F16", g_nee, FRAMES_LOW, f"x{SPP_LOW}")

# F16R3d K=1 lo=0 — K-slot K=1 parity check + multi-level off (today's behaviour).
g_K1_lo0 = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                      samplesPerPixel=SPP_LOW, useJitter=True,
                                      numNEECandidates=NEE_K,
                                      useNEECells=True,
                                      cellReservoirFootprintPx=CELL_FP,
                                      reservoirK=1,
                                      cellLevelOffsetWrite=0)
_run(f"nee_F16R3d_K1lo0_fp{CELL_FP}", g_K1_lo0, FRAMES_LOW, f"x{SPP_LOW}")

# F16R3d K-slot × step C cascade. K=4/8 × lo=0/1/2.
for K in (4, 8):
    for lvlOff in (0, 1, 2):
        g = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                       samplesPerPixel=SPP_LOW, useJitter=True,
                                       numNEECandidates=NEE_K,
                                       useNEECells=True,
                                       cellReservoirFootprintPx=CELL_FP,
                                       reservoirK=K,
                                       cellLevelOffsetWrite=lvlOff)
        _run(f"nee_F16R3d_K{K}lo{lvlOff}_fp{CELL_FP}", g, FRAMES_LOW, f"x{SPP_LOW}")

print("[compare-nee-kslot] all variants captured.")
exit()

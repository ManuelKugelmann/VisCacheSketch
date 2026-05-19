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

# 1. Vanilla low-SPP (upstream PathTracer, no VisCache). Two flavours:
#    - vanilla_b1 — single-bounce baseline. Direct comparison target for
#      restirdi (DI is a primary-hit-only algorithm) and for restirnee_b1
#      (NEE-everywhere collapses to NEE-at-primary when maxBounces=1).
#    - vanilla — multi-bounce baseline at MAX_BOUNCES. Comparison target for
#      restirnee (which exercises K-RIS at every vertex through MAX_BOUNCES).
g_vanilla_b1 = render_graph_PathTracer(viscache=False, maxBounces=1,
                                       samplesPerPixel=SPP_LOW, useJitter=True,
                                       passClassName="PathTracer")
_run("vanilla_b1", g_vanilla_b1, FRAMES_LOW, f"x{SPP_LOW}")

g_vanilla = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                                    samplesPerPixel=SPP_LOW, useJitter=True,
                                    passClassName="PathTracer")
_run("vanilla", g_vanilla, FRAMES_LOW, f"x{SPP_LOW}")

# 2. Vanilla ground truth (high-SPP same path tracer)
g_gt = render_graph_PathTracer(viscache=False, maxBounces=MAX_BOUNCES,
                               samplesPerPixel=SPP_GT, useJitter=False,
                               passClassName="PathTracer")
_run("gt", g_gt, FRAMES_GT, f"x{SPP_GT}")

# 3. ReSTIR DI at maxBounces=1 — DI is a primary-hit algorithm by design
#    (K-RIS + per-pixel reservoir + temporal + spatial reuse at vertex 1
#    only; vertices 2+ would fall back to plain NEE and add no DI value).
#    Running DI at maxBounces=3 just inflates the path tracer without
#    exercising the algorithm. VisCache shadow CV / light-selection off.
g_rdi = render_graph_PathTracer(
    viscache=True, reservoirs=True, useReSTIRDIPass=True,
    maxBounces=1, samplesPerPixel=SPP_LOW, useJitter=True,
    visibilityCheck=False, lightSelection=False,
)
_run("restirdi", g_rdi, FRAMES_LOW, f"x{SPP_LOW}")

# Variant naming follows the project taxonomy:
#   F## = Fresh K-RIS candidate count (initialCandidates).
#   P## = Pool draw K (cellPoolDrawK).
#   R2d = per-pixel reservoir; R3d = world-space cell reservoir.
#   _b1 = single-bounce-only (matches DI's native primary-hit scope);
#         unsuffixed = multi-bounce at MAX_BOUNCES.
#
# Honest read on current "ReSTIR" NEE: F16 / F16_b1 are PURE K-RIS — no
# reservoir reuse, not really ReSTIR. F16R3d is genuinely ReSTIR-like
# (3D cell reservoir persists across frames AND pixels). A faithful
# ReSTIR-NEE-as-multibounce-DI would add per-vertex R2d (or hit-point
# hashed reservoir) + temporal/spatial reuse — not yet implemented.

# 4a. F16_b1 — fresh K-RIS at primary hit only, no reservoir. Algorithmically
#     pure-RIS (Talbot 2005) baseline. The gap vs restirdi exposes the value
#     of DI's reservoir-reuse machinery on top of identical K-RIS.
g_nee_b1 = render_graph_ReSTIRNEEPass(maxBounces=1,
                                      samplesPerPixel=SPP_LOW, useJitter=True,
                                      numNEECandidates=NEE_K)
_run("nee_F16_b1", g_nee_b1, FRAMES_LOW, f"x{SPP_LOW}")

# 4b. F16 multi-bounce — fresh K-RIS at every non-Delta vertex.
g_nee = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                   samplesPerPixel=SPP_LOW, useJitter=True,
                                   numNEECandidates=NEE_K)
_run("nee_F16", g_nee, FRAMES_LOW, f"x{SPP_LOW}")

# 5. F16R3d — F16 + 3D cell-reservoir reuse at every NEE call. Cell merge
#    currently uses identity-stream (DI's gCellReservoirMerge=0 mode). Full
#    Bitterli weighted merge (DI's gCellReservoirMerge=1) needs M-cap-aware
#    reservoir math to avoid cell.W positive-feedback explosion across the
#    multi-vertex writes per pixel.
g_nee_cells = render_graph_ReSTIRNEEPass(maxBounces=MAX_BOUNCES,
                                         samplesPerPixel=SPP_LOW, useJitter=True,
                                         numNEECandidates=NEE_K,
                                         useNEECells=True)
_run("nee_F16R3d", g_nee_cells, FRAMES_LOW, f"x{SPP_LOW}")

print("[compare] all variants captured.")
exit()

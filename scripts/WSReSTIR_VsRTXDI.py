"""
WSReSTIR_VsRTXDI.py — A/B captures across vanilla / WS-ReSTIR / RTXDI.

Three reference variants on the same scenes, same SPP, same accumulation
frame count. Outputs to runtime/captures/wsrestir_vs_rtxdi/<variant>/<scene>/.

Note RTXDI is direct-illumination only (its graph uses GBufferRT, not VBuffer
+ PathTracer); the comparison is honest only for direct-lit scenes (Cornell
variants without complex indirect bounces). For full-PT comparison use
vanilla vs WS-ReSTIR only.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer
from RTXDI_Graph    import render_graph_RTXDI

try:
    from falcor import *
except ImportError:
    pass

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "")
SCENES = [
    "CornellBox_1AreaLight.pyscene",
    "CornellBox_3AreaLights.pyscene",
    "CornellBox_32PointLights.pyscene",
]
VARIANTS = [
    # Direct lighting only (maxBounces=0). RTXDI is DI-only by design;
    # we restrict the path tracer to match for apples-to-apples comparison.
    ("vanilla",  lambda: render_graph_PathTracer(viscache=False, maxBounces=0)),
    ("ws_K1",    lambda: render_graph_PathTracer(
        viscache=True, wsReservoirs=True, maxBounces=0,
        wsInitialCandidates=1,
        visibilityCheck=True, lightSelection=True)),
    ("ws_K8",    lambda: render_graph_PathTracer(
        viscache=True, wsReservoirs=True, maxBounces=0,
        wsInitialCandidates=8,
        visibilityCheck=True, lightSelection=True)),
    ("ws_K32",   lambda: render_graph_PathTracer(
        viscache=True, wsReservoirs=True, maxBounces=0,
        wsInitialCandidates=32,
        visibilityCheck=True, lightSelection=True)),
    ("rtxdi",    lambda: render_graph_RTXDI(viscache=False)),
]
WARMUP_FRAMES  = 8
CAPTURE_FRAMES = 16

OUTPUT_ROOT = os.path.join(PROJECT_ROOT or ".", "runtime", "captures", "wsrestir_vs_rtxdi")
os.makedirs(OUTPUT_ROOT, exist_ok=True)

def resolve_scene(scene_name):
    if PROJECT_ROOT and not os.path.isabs(scene_name):
        candidate = os.path.join(PROJECT_ROOT, "scenes", scene_name)
        if os.path.isfile(candidate):
            return candidate
    return scene_name

for scene_name in SCENES:
    scene_path = resolve_scene(scene_name)
    scene_label = os.path.splitext(os.path.basename(scene_name))[0]
    for variant_name, build_graph in VARIANTS:
        print(f"[VsRTXDI] === {variant_name} on {scene_label} ===")
        g = build_graph()
        m.addGraph(g)
        m.loadScene(scene_path)

        outdir = os.path.join(OUTPUT_ROOT, variant_name, scene_label)
        os.makedirs(outdir, exist_ok=True)
        m.frameCapture.outputDir    = outdir
        m.frameCapture.baseFilename = f"{variant_name}_{scene_label}"

        for _ in range(WARMUP_FRAMES):
            m.renderFrame()
        for _ in range(CAPTURE_FRAMES):
            m.renderFrame()
        m.frameCapture.capture()

        print(f"[VsRTXDI] saved -> {outdir}")
        m.removeGraph(g)

print("[VsRTXDI] DONE")
_HEADLESS_SCRIPT_DONE = True

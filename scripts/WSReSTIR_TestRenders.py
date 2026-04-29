"""
WSReSTIR_TestRenders.py — A/B capture suite for §9.4 WS-ReSTIR DI.

Renders each (scene, variant) pair with a warmup + capture sequence,
saving EXR frames to runtime/captures/wsrestir_test/<variant>/<scene>/.

Variants:
  legacy : VisCache + visibility-check (§9.2) only
  ws     : VisCache + visibility-check + WS-ReSTIR (§9.4)
  full   : VisCache + visibility-check + light-selection μ (§9.1) + WS-ReSTIR (§9.4)

Run via:
  PROJECT_ROOT=C:/Projects/VisCacheSketch \
  GRAPH_SCRIPT=scripts/WSReSTIR_TestRenders.py \
  runtime/Mogwai.exe --headless -s C:/Projects/VisCacheSketch/scripts/RunGraphHeadless.py

(or use the headless wrapper with `WSReSTIR_TestRenders.py` as the pattern).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

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
    # name, kwargs to render_graph_PathTracer, viscache prop overrides
    ("legacy", dict(viscache=True, wsReservoirs=False), {
        "enableVisCacheVisibilityCheck": True,
        "enableVisCacheLightSelection":  False,
        "enableWSReservoirs":            False,
    }),
    ("ws", dict(viscache=True, wsReservoirs=True), {
        "enableVisCacheVisibilityCheck": True,
        "enableVisCacheLightSelection":  False,
        "enableWSReservoirs":            True,
    }),
    ("full", dict(viscache=True, wsReservoirs=True), {
        "enableVisCacheVisibilityCheck": True,
        "enableVisCacheLightSelection":  True,
        "enableWSReservoirs":            True,
    }),
]
WARMUP_FRAMES = 8     # let the cache + reservoirs accumulate
CAPTURE_FRAMES = 16   # frames over which we accumulate the captured EXR

OUTPUT_ROOT = os.path.join(PROJECT_ROOT or ".", "runtime", "captures", "wsrestir_test")
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
    for variant_name, graph_kwargs, vc_overrides in VARIANTS:
        print(f"[WSTest] === {variant_name} on {scene_label} ===")
        g = render_graph_PathTracer(**graph_kwargs)

        # Apply per-variant VisCache toggle overrides directly on the pass.
        if "VisCache" in g.getPasses() if hasattr(g, "getPasses") else True:
            try:
                vc_pass = g.getPass("VisCache")
                for k, v in vc_overrides.items():
                    vc_pass.setProperty(k, v)
            except Exception as e:
                print(f"[WSTest] WARN: could not override VisCache props ({e})")

        m.addGraph(g)
        m.loadScene(scene_path)

        outdir = os.path.join(OUTPUT_ROOT, variant_name, scene_label)
        os.makedirs(outdir, exist_ok=True)
        m.frameCapture.outputDir    = outdir
        m.frameCapture.baseFilename = f"{variant_name}_{scene_label}"

        # Warm up — let the AccumulatePass smooth over the first ReSTIR frames.
        for _ in range(WARMUP_FRAMES):
            m.renderFrame()

        # Single capture at the end of N accumulation frames.
        for _ in range(CAPTURE_FRAMES):
            m.renderFrame()
        m.frameCapture.capture()

        print(f"[WSTest] saved -> {outdir}")
        m.removeGraph(g)

print("[WSTest] DONE")
_HEADLESS_SCRIPT_DONE = True

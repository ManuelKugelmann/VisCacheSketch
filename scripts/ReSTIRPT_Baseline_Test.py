"""
ReSTIRPT_Baseline_Test.py — multi-bounce A/B between vanilla PathTracer and
ReSTIRPTPass on the same scenes / SPP / bounce counts.

Each Mogwai invocation processes EXACTLY ONE (variant, bounces) cell across all
SCENES, to stay under Slang's per-process permutation budget (~60). Loop the
shell over cells using restirpt_baseline_run.sh.

Env vars (all required for a single cell):
  VARIANT  : "vanilla" or "restirpt"
  BOUNCE   : integer (single value, e.g. 4)
Optional:
  SCENES   : comma-separated stems (default: CornellBox_1AreaLight + escalation list)
  SPP      : samples per pixel per frame (default 1)
  WARMUP   : warmup frames (default 8)
  CAPTURE  : accumulation frames before EXR capture (default 32)

Output: runtime/captures/restirpt_baseline/<scene>/<variant>_b<N>_x<spp>/
        with HDR EXR + LDR PNG.

Already-captured cells are skipped (idempotent re-run).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PathTracer_Graph import render_graph_PathTracer
from ReSTIRPT_Graph import render_graph_ReSTIRPT

try:
    from falcor import *
except ImportError:
    pass

PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "")

VARIANT = os.environ.get("VARIANT", "vanilla").strip().lower()
BOUNCE  = int(os.environ.get("BOUNCE", "1"))
SPP     = int(os.environ.get("SPP", "1"))
WARMUP_FRAMES   = int(os.environ.get("WARMUP", "8"))
CAPTURE_FRAMES  = int(os.environ.get("CAPTURE", "32"))

DEFAULT_SCENES = [
    "CornellBox_1AreaLight",
    "CornellBox_3AreaLights",
    "CornellBox_32PointLights",
    "VeachAjar",
    "BistroInterior",
    "BistroExterior",
    "Sponza",
]
_scene_override = os.environ.get("SCENES", "").strip()
SCENES = ([s.strip() for s in _scene_override.split(",") if s.strip()]
          if _scene_override else DEFAULT_SCENES)

OUTPUT_ROOT = os.path.join(PROJECT_ROOT or ".", "runtime", "captures", "restirpt_baseline")
os.makedirs(OUTPUT_ROOT, exist_ok=True)


def build_graph():
    if VARIANT == "vanilla":
        return render_graph_PathTracer(viscache=False, maxBounces=BOUNCE,
                                       samplesPerPixel=SPP, useJitter=True)
    if VARIANT == "restirpt":
        # Default: ReSTIRPT + RTXDI direct lighting (DQLin's reference config).
        return render_graph_ReSTIRPT(viscache=False, maxBounces=BOUNCE,
                                     samplesPerPixel=SPP)
    if VARIANT == "restirpt_no_rtxdi":
        # ReSTIRPT only, no RTXDI direct light input. ReSTIRPT does its own
        # NEE direct sampling. Diagnostic for direct-light double-counting.
        return render_graph_ReSTIRPT(viscache=False, maxBounces=BOUNCE,
                                     samplesPerPixel=SPP,
                                     useRTXDIDirect=False)
    if VARIANT == "restirpt_no_direct":
        # ReSTIRPT with directLighting disabled — measure pure indirect.
        return render_graph_ReSTIRPT(viscache=False, maxBounces=BOUNCE,
                                     samplesPerPixel=SPP,
                                     useRTXDIDirect=False,
                                     useDirectLighting=False)
    raise ValueError(f"Unknown VARIANT: {VARIANT!r}")


def resolve_scene(scene_name):
    """Find a .pyscene by stem. Prefer paths where the scene's external
    geometry assets (fbx, obj) are co-located with the .pyscene — Falcor's
    asset search starts from the .pyscene's directory, so an isolated copy in
    runtime/media/scenes/ that references "BistroInterior.fbx" relatively
    will fail to load.
    """
    rt = PROJECT_ROOT or "."
    candidates = [
        # Prefer geometry-co-located locations FIRST so relative asset paths
        # resolve. Bistro fbx lives in runtime/media/Bistro/, Sponza obj in
        # runtime/media/Sponza/, VeachAjar in runtime/data/ReSTIRPTPass/.
        os.path.join(rt, "runtime", "media", "Bistro", scene_name + ".pyscene"),
        os.path.join(rt, "runtime", "media", "Sponza", scene_name + ".pyscene"),
        os.path.join(rt, "runtime", "data", "ReSTIRPTPass", scene_name,
                     scene_name + ".pyscene"),
        # CornellBox is procedural — runtime/media/scenes/ is the right home.
        os.path.join(rt, "runtime", "media", "scenes", scene_name + ".pyscene"),
        # Project-root scenes/ as a final non-runtime fallback.
        os.path.join(rt, "scenes", scene_name + ".pyscene"),
        scene_name + ".pyscene",
        scene_name,
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return scene_name


def already_done(outdir, tag):
    """Skip if any EXR for this cell exists (idempotent)."""
    if not os.path.isdir(outdir):
        return False
    for fname in os.listdir(outdir):
        if fname.startswith(tag) and fname.endswith(".exr"):
            full = os.path.join(outdir, fname)
            if os.path.getsize(full) > 1024:
                return True
    return False


tag = f"{VARIANT}_b{BOUNCE}_x{SPP}"
print(f"[ReSTIRPT-Baseline] CELL: {tag}")
print(f"[ReSTIRPT-Baseline] SCENES: {SCENES}")
print(f"[ReSTIRPT-Baseline] frames: warmup={WARMUP_FRAMES} capture={CAPTURE_FRAMES}")

results = []
for scene_name in SCENES:
    scene_path = resolve_scene(scene_name)
    if not os.path.isfile(scene_path):
        print(f"[ReSTIRPT-Baseline] SKIP {scene_name} — no .pyscene at {scene_path}")
        results.append((scene_name, "skip-noscene"))
        continue

    outdir = os.path.join(OUTPUT_ROOT, scene_name, tag)
    if already_done(outdir, tag):
        print(f"[ReSTIRPT-Baseline] CACHED {scene_name} :: {tag}")
        results.append((scene_name, "cached"))
        continue

    os.makedirs(outdir, exist_ok=True)
    print(f"[ReSTIRPT-Baseline] === {scene_name} :: {tag} ===")

    g = build_graph()
    m.addGraph(g)
    try:
        m.loadScene(scene_path)
    except Exception as ex:
        print(f"[ReSTIRPT-Baseline] FAILED to load {scene_name}: {ex}")
        m.removeGraph(g)
        results.append((scene_name, "load-fail"))
        continue

    m.frameCapture.outputDir    = outdir
    m.frameCapture.baseFilename = tag

    for _ in range(WARMUP_FRAMES):
        m.renderFrame()
    for _ in range(CAPTURE_FRAMES):
        m.renderFrame()
    m.frameCapture.capture()

    print(f"[ReSTIRPT-Baseline] saved -> {outdir}")
    m.removeGraph(g)
    results.append((scene_name, "ok"))

print(f"\n[ReSTIRPT-Baseline] CELL {tag} summary:")
for scene_name, status in results:
    print(f"  {scene_name:<30s} {status}")

print("[ReSTIRPT-Baseline] DONE")
_HEADLESS_SCRIPT_DONE = True

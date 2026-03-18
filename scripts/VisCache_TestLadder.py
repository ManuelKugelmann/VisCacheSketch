"""
VisCache_TestLadder.py — Step-by-step feature test ladder.

Starts with the simplest possible cache (1 level, all features OFF)
and enables features one at a time. Each step captures a diagnostic
composite so we can verify correctness before adding complexity.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_TestLadder.py

Outputs to: captures/ladder/<step_name>/
"""
import os
import subprocess

kWarmupFrames  = 64
kCaptureDir    = "captures/ladder"

# Test ladder: each step adds ONE feature to the previous step.
# All steps use 1 spp PathTracer, Arcade scene.
LADDER = [
    # Step 0: Bare minimum — 1 level, large cells, everything off.
    # Expect: blocky grid, uniform mu per cell, no refinement.
    ("00_bare_1level", {
        "numLevels": 1,
        "enableVisCacheJitter": False,
        "enableVisCacheVarianceGate": False,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": False,
        "enableVisCachePressureEvict": False,
    }),

    # Step 1: Add jitter — should smooth cell boundaries.
    ("01_jitter", {
        "numLevels": 1,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": False,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": False,
        "enableVisCachePressureEvict": False,
    }),

    # Step 2: Add variance gate — should limit writes to high-variance regions.
    ("02_vargate", {
        "numLevels": 1,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": False,
        "enableVisCachePressureEvict": False,
    }),

    # Step 3: Multi-level (3 levels) — should show LOD cascade.
    ("03_3levels", {
        "numLevels": 3,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": False,
        "enableVisCachePressureEvict": False,
    }),

    # Step 4: Add decay — should prevent stale entries.
    ("04_decay", {
        "numLevels": 3,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": True,
        "enableVisCachePressureEvict": False,
    }),

    # Step 5: Add pressure eviction — should handle table pressure.
    ("05_eviction", {
        "numLevels": 3,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": False,
        "enableVisCacheDecay": True,
        "enableVisCachePressureEvict": True,
    }),

    # Step 6: Add warp reduction — performance only, same visual result.
    ("06_warpreduce", {
        "numLevels": 3,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": True,
        "enableVisCacheDecay": True,
        "enableVisCachePressureEvict": True,
    }),

    # Step 7: Full system — 8 levels, all features on.
    ("07_full_8levels", {
        "numLevels": 8,
        "enableVisCacheJitter": True,
        "enableVisCacheVarianceGate": True,
        "enableVisCacheWarpReduction": True,
        "enableVisCacheDecay": True,
        "enableVisCachePressureEvict": True,
    }),
]

# Load render_graph_PathTracer + defaults
_graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PathTracer_Graph.py")
with open(_graph_path, "r") as _f:
    exec(compile(_f.read(), _graph_path, "exec"))

from viscache_defaults import VISCACHE_DEFAULTS

scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")

for (name, overrides) in LADDER:
    print(f"\n[ladder] === {name} ===")
    for k, v in overrides.items():
        print(f"[ladder]   {k}={v}")

    # Build graph with overrides applied to defaults
    saved = {}
    for k, v in overrides.items():
        if k in VISCACHE_DEFAULTS:
            saved[k] = VISCACHE_DEFAULTS[k]
        VISCACHE_DEFAULTS[k] = v

    g = render_graph_PathTracer(viscache=True)

    # Restore defaults
    for k, v in saved.items():
        VISCACHE_DEFAULTS[k] = v
    for k in overrides:
        if k not in saved:
            del VISCACHE_DEFAULTS[k]

    m.addGraph(g)
    m.loadScene(scene_file)

    outdir = os.path.join(kCaptureDir, name)
    os.makedirs(outdir, exist_ok=True)
    fc.outputDir = outdir
    fc.baseFilename = name

    # Warmup
    for _ in range(kWarmupFrames):
        m.renderFrame()

    # Capture
    fc.capture()
    m.renderFrame()

    print(f"[ladder] Captured {name} to {outdir}/")

    # Convert EXR composites to PNG
    import glob
    for exr in glob.glob(os.path.join(outdir, "*.exr")):
        png = exr.replace(".exr", ".png")
        try:
            subprocess.run(["ffmpeg", "-y", "-i", exr, "-pix_fmt", "rgb24", png],
                           capture_output=True, timeout=10)
        except Exception:
            pass

    m.removeGraph(g)

print(f"\n[ladder] All {len(LADDER)} steps complete.")
exit()

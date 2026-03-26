"""
VisCache_Ladder00_Variants.py — Step 0: Compare addressing variants.

Naming: A__B where __ separates endpoint A from B, _ separates dimensions within.
1. pos__pos:         canonical endpoint pairs with lexicographic swap
2. pos__posB:        asymmetric (slightly different cell size, no canonicalization)
3. pos__pos1:        collapsed B → position-only via pos×pos
4. pos__dir1_dist1:  dirdist with huge scales → all dirs+dists collapse
5. pos__dir_dist1:   coarse angular bins, single dist bucket
6. pos__dir_dist:    coarse angular + coarse dist bins
"""
import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr_split import split_diag_exrs

# Test configurations: (warmup, averaging) frame counts
# Multiple runs per variant for convergence comparison
kResX = 512
kResY = 512

FRAME_CONFIGS = [
    (0, 1),      # single frame — raw first-sample snapshot
]
scene_file = os.environ.get("SCENE_FILE", "media/scenes/CornellBox.pyscene")
scene_name = os.path.splitext(os.path.basename(scene_file))[0]

# Shared base config: 1 level, no jitter, all features off, always trace
BASE = {
    "numLevels": 1,
    "cellACoarse": 0.06,
    "autoTuneCells": False,
    "bootThreshold": 4,
    "pMin": 1.0,
    "enableVisCacheJitter": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}

VARIANTS = [
    ("pos__pos", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.06,       # same as cellA → canonical
    }),
    ("pos__posB", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.061,      # slightly different → NO canonicalization (test for swap asymmetry)
    }),
    ("pos__pos1", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 10000.0,    # collapsed B → position-only via pos×pos
    }),
    ("pos__dir1_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 360.0,   # single direction bin
        "distBCoarse": 1000.0,     # single dist bucket → position-only via dirdist
    }),
    ("pos__dir_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,    # 45° angular bins
        "distBCoarse": 1000.0,     # single dist bucket
    }),
    ("pos__dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,    # 45° angular bins
        "distBCoarse": 0.24,       # 4× cellA distance bins
    }),
]

def postprocess(captureDir, prefix):
    """Split diagnostic EXRs into named viridis PNGs."""
    split_diag_exrs(captureDir, prefix, sections=["basic"])

    # Copy ToneMapper render
    import shutil
    for png in glob.glob(os.path.join(captureDir, f"*ToneMapper.dst.*")):
        shutil.copy(png, os.path.join(captureDir, f"{prefix}accum_render.png"))
        break

for (variant_name, overrides) in VARIANTS:
    for (warmup, averaging) in FRAME_CONFIGS:
        captureDir = f"captures/ladder/00/{scene_name}"
        tag = f"w{warmup}_a{averaging}"
        print(f"\n[step00] ======== {variant_name} {tag} ({scene_name}) ========")

        saved = {}
        for k, v in overrides.items():
            if k in VISCACHE_DEFAULTS:
                saved[k] = VISCACHE_DEFAULTS[k]
            VISCACHE_DEFAULTS[k] = v

        g = render_graph_PathTracer(viscache=True, maxBounces=1)

        for k, v in saved.items():
            VISCACHE_DEFAULTS[k] = v
        for k in overrides:
            if k not in saved and k in VISCACHE_DEFAULTS:
                del VISCACHE_DEFAULTS[k]

        m.addGraph(g)
        m.loadScene(scene_file)
        m.resizeFrameBuffer(kResX, kResY)

        os.makedirs(captureDir, exist_ok=True)
        fc.outputDir = captureDir
        fc.baseFilename = variant_name

        # Phase 1: warmup
        for _ in range(warmup):
            m.renderFrame()

        # Reset accum for clean averaging window
        if warmup > 0:
            g.getPass("VisCache").set_properties({"resetAccum": True})

        # Phase 2: averaging
        for _ in range(averaging):
            m.renderFrame()

        fc.capture()
        m.renderFrame()

        print(f"[step00] Captured ({tag})")
        postprocess(captureDir, f"s_{warmup}_{averaging}_{variant_name}_")

        # Delete raw EXRs
        for f in glob.glob(os.path.join(captureDir, "*.exr")):
            os.remove(f)

        m.removeGraph(g)

print(f"\n[step00] All {len(VARIANTS)} variants done.")
exit()

"""
VisCache_Ladder00_Variants.py — Step 0: Compare 4 addressing variants.

1. pos_pos_canonical: default endpoint pairs with lexicographic swap
2. pos_only:          dirdist with huge scales → all dirs+dists collapse
3. pos_dir:           dirdist with coarse angular bins, single dist bucket
4. pos_dir_dist:      dirdist with coarse angular + coarse dist bins
"""
import os, sys, subprocess, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer

# Test configurations: (warmup, averaging) frame counts
# Multiple runs per variant for convergence comparison
kResX = 512
kResY = 512

FRAME_CONFIGS = [
    (0, 1),      # single frame — raw first-sample snapshot
]
scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")
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
    ("pos_pos", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.06,       # same as cellA → canonical
    }),
    ("pos_posB", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.061,      # slightly different → NO canonicalization (test for swap asymmetry)
    }),
    ("pos_pos1", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 10000.0,    # collapsed B → position-only via pos×pos
    }),
    ("pos_dir1_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 360.0,   # single direction bin
        "distBCoarse": 1000.0,     # single dist bucket → position-only via dirdist
    }),
    ("pos_dir_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,    # 45° angular bins
        "distBCoarse": 1000.0,     # single dist bucket
    }),
    ("pos_dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,    # 45° angular bins
        "distBCoarse": 0.24,       # 4× cellA distance bins
    }),
]

def ffrun(args):
    try:
        subprocess.run(["ffmpeg", "-y"] + args, capture_output=True, timeout=10)
        return True
    except Exception:
        return False

def out(d, name, prefix=""):
    return os.path.join(d, f"{prefix}{name}.png")

def postprocess(captureDir, prefix):
    """7-column grid layout with variant prefix.
    Row 1 (accum):  1_RGB  2_var  3_mat  4_mu  5__  6__  7_render
    Row 2 (snap):   1_RGB  2_var  3_mat  4_mu  5_probe  6_count  7_level
    Row 3 (output): 1_render  2_error  3_noise  4_raysaved  5__  6__  7__
    """
    import shutil
    p = prefix
    for exr in glob.glob(os.path.join(captureDir, "*.exr")):
        base = os.path.basename(exr)
        if "vcDiag." in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "accum_1_RGB", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "accum_2_var", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "accum_3_mat", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "accum_4_mu", p)])
        elif "VarMaturityMu" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "snap_1_RGB", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_2_var", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_3_mat", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "snap_4_mu", p)])
        elif "VarMaturityLevel" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "snap_5_probe_count_level", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_6_probesteps", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_7_samplecount", p)])

    # Row 3: Mogwai outputs — rename to remove "Heatmap" and add grid numbering
    vn = prefix[:-1]  # variant name without trailing _
    renames = [
        (f"{vn}.ToneMapper.dst.",       "output_1_render"),
        (f"{vn}.Error.output.",         "output_2_error"),
        (f"{vn}.Noise.output.",         "output_3_noise"),
        (f"{vn}.RaySavedPct.output.",   "output_4_raysaved"),
    ]
    for pattern, newname in renames:
        for png in glob.glob(os.path.join(captureDir, f"*{pattern}*")):
            shutil.copy(png, out(captureDir, newname, p))
            break

    # Pad row 1 (accum 5-6) and row 3 (output 5-7) + accum 7 = render
    for png in glob.glob(os.path.join(captureDir, f"*ToneMapper.dst.*")):
        shutil.copy(png, out(captureDir, "accum_7_render", p))
        break
    for slot in ["accum_5__", "accum_6__", "output_5__", "output_6__", "output_7__"]:
        ffrun(["-f", "lavfi", "-i", f"color=black:s={kResX}x{kResY}:d=1", "-frames:v", "1",
               "-pix_fmt", "rgb24", out(captureDir, slot, p)])

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

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

kWarmupFrames = 128    # frames before accum window (cache populates, accum ignored)
kAveragingFrames = 128 # frames in accum window (clean simple average)
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
        "cellBCoarse": 0.06,       # same as cellA → canonical with fine posB
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
    """prefix = variant name, e.g. 'pos_pos_'
    Output naming: 7 images per row, snap and accum align vertically.
    Row 1 (accum): 1_RGB  2_variance  3_maturity  4_mu  5_pad  6_pad  7_render
    Row 2 (snap):  1_RGB  2_variance  3_maturity  4_mu  5_probe  6_count  7_level
    """
    p = prefix
    for exr in glob.glob(os.path.join(captureDir, "*.exr")):
        base = os.path.basename(exr)
        if "vcDiag." in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "accum_1_RGB", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "accum_2_variance", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "accum_3_maturity", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "accum_4_mu", p)])
        elif "VarMaturityMu" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "snap_1_RGB", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_2_variance", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_3_maturity", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "snap_4_mu", p)])
        elif "VarMaturityLevel" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "snap_5_probe_count_level", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_6_probesteps", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "snap_7_samplecount", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "snap_8_level", p)])
    # Copy ToneMapper render as accum row slot 7
    for png in glob.glob(os.path.join(captureDir, f"{prefix[:-1]}.ToneMapper.dst.*.png")):
        import shutil
        shutil.copy(png, out(captureDir, "accum_7_render", p))
        break
    # Pad accum slots 5-6 with empty black images (same size as render)
    for slot in ["accum_5_pad", "accum_6_pad"]:
        ffrun(["-f", "lavfi", "-i", "color=black:s=1920x1080:d=1", "-frames:v", "1",
               "-pix_fmt", "rgb24", out(captureDir, slot, p)])

for (variant_name, overrides) in VARIANTS:
    captureDir = f"captures/ladder/00/{scene_name}"
    print(f"\n[step00] ======== {variant_name} ({scene_name}) ========")

    saved = {}
    for k, v in overrides.items():
        if k in VISCACHE_DEFAULTS:
            saved[k] = VISCACHE_DEFAULTS[k]
        VISCACHE_DEFAULTS[k] = v

    g = render_graph_PathTracer(viscache=True)

    for k, v in saved.items():
        VISCACHE_DEFAULTS[k] = v
    for k in overrides:
        if k not in saved and k in VISCACHE_DEFAULTS:
            del VISCACHE_DEFAULTS[k]

    m.addGraph(g)
    m.loadScene(scene_file)

    os.makedirs(captureDir, exist_ok=True)
    fc.outputDir = captureDir
    fc.baseFilename = variant_name

    # Phase 1: warmup (cache populates, accum runs but will be reset)
    for _ in range(kWarmupFrames):
        m.renderFrame()

    # Reset accum for clean averaging window (warm cache, fresh diagnostic)
    g.getPass("VisCache").set_properties({"resetAccum": True})

    # Phase 2: averaging window (simple average from zero over warm cache)
    for _ in range(kAveragingFrames):
        m.renderFrame()

    fc.capture()
    m.renderFrame()

    total = kWarmupFrames + kAveragingFrames
    tag = f"w{kWarmupFrames}_a{kAveragingFrames}"
    print(f"[step00] Captured to {captureDir}/ ({tag})")
    postprocess(captureDir, f"{variant_name}_{tag}_")

    # Delete raw EXRs, keep heatmap PNGs from Mogwai and our named PNGs
    for f in glob.glob(os.path.join(captureDir, "*.exr")):
        os.remove(f)

    print(f"[step00] Post-processed.")
    m.removeGraph(g)

print(f"\n[step00] All {len(VARIANTS)} variants done.")
exit()

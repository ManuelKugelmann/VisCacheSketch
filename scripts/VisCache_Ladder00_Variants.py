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

kWarmupFrames = 1024
scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")
scene_name = os.path.splitext(os.path.basename(scene_file))[0]

# Shared base config: 1 level, no jitter, all features off, always trace
BASE = {
    "numLevels": 1,
    "cellCoarse": 0.06,
    "cellFine": 0.06,
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
    ("pos_pos_canonical", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "enableVisCacheAsymmetricAddr": False,
    }),
    ("pos_only", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "addrBScale": 0.1,         # <0.5 → single direction bin (all dirs collapse)
        "addrBDistScale": 1000.0,  # single dist bucket → position-only
    }),
    ("pos_dir", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "addrBScale": 2.0,         # 2 bins/axis → ~16 direction bins (coarse)
        "addrBDistScale": 1000.0,  # single dist bucket
    }),
    ("pos_dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "addrBScale": 2.0,         # coarse angular bins
        "addrBDistScale": 4.0,     # coarse dist bins
    }),
]

def ffrun(args):
    try:
        subprocess.run(["ffmpeg", "-y"] + args, capture_output=True, timeout=10)
        return True
    except Exception:
        return False

def out(d, name):
    return os.path.join(d, f"{name}.png")

def postprocess(captureDir):
    for exr in glob.glob(os.path.join(captureDir, "*.exr")):
        base = os.path.basename(exr)
        if "vcDiag." in base:
            ffrun(["-i", exr, "-vf", "extractplanes=r", "-pix_fmt", "gray", out(captureDir, "cellhash_qa")])
            ffrun(["-i", exr, "-vf", "extractplanes=g", "-pix_fmt", "gray", out(captureDir, "cellhash_qb")])
            ffrun(["-i", exr, "-vf", "extractplanes=b", "-pix_fmt", "gray", out(captureDir, "coldmiss")])
        elif "VarMaturityMu" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "quality_var_maturity_mu")])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "quality__variance")])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "quality__maturity")])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "quality__mu")])
        elif "VarMaturityLevel" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", out(captureDir, "health_probe_count_level")])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "health__probesteps")])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out(captureDir, "health__samplecount")])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out(captureDir, "health__level")])

for (variant_name, overrides) in VARIANTS:
    captureDir = f"captures/ladder/00_{variant_name}_{scene_name}"
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

    for _ in range(kWarmupFrames):
        m.renderFrame()

    fc.capture()
    m.renderFrame()

    print(f"[step00] Captured to {captureDir}/")
    postprocess(captureDir)
    print(f"[step00] Post-processed.")

    m.removeGraph(g)

print(f"\n[step00] All {len(VARIANTS)} variants done.")
exit()

"""
VisCache_Ladder00_Bare.py — Step 0: Bare minimum cache.

1 level, no jitter, pMin=1.0 (always trace, never skip rays),
no variance gate, no decay, no eviction.
Tests: hash insert + lookup + diagnostic write at the simplest setting.

Expected output: blocky grid on vcVarMaturityLevel, uniform mu per cell,
full coverage (every NEE pixel should have data).
"""
import os, sys, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer

kWarmupFrames = 1024
kCaptureDir   = "captures/ladder/00_bare"

# Override defaults for bare minimum config
overrides = {
    "numLevels": 1,
    "cellCoarse": 0.06,      # ~6cm cells — compromise between resolution and maturity
    "cellFine": 0.06,
    "autoTuneCells": False,
    "bootThreshold": 4,      # low threshold — mature quickly for visualization
    "pMin": 1.0,             # always trace — no RR skipping
    "enableVisCacheJitter": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}

# Apply overrides
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
    if k not in saved and k in VISCACHE_DEFAULTS:
        del VISCACHE_DEFAULTS[k]

m.addGraph(g)

scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")
m.loadScene(scene_file)

os.makedirs(kCaptureDir, exist_ok=True)
fc.outputDir = kCaptureDir
fc.baseFilename = "bare"

print(f"[ladder-00] Scene: {scene_file}")
print(f"[ladder-00] Config: 1 level, no jitter, pMin=1.0, all ablations OFF")
print(f"[ladder-00] Warmup: {kWarmupFrames} frames")

for _ in range(kWarmupFrames):
    m.renderFrame()

fc.capture()
m.renderFrame()

print(f"[ladder-00] Captured to {kCaptureDir}/")

# Post-process: convert EXR to named PNGs
import glob

def ffrun(args):
    try:
        subprocess.run(["ffmpeg", "-y"] + args, capture_output=True, timeout=10)
        return True
    except Exception:
        return False

def out(name):
    """Build output path from descriptive name."""
    return os.path.join(kCaptureDir, f"{name}.png")

for exr in glob.glob(os.path.join(kCaptureDir, "*.exr")):
    base = os.path.basename(exr)

    if "vcDiag." in base:
        # Cell hash debug — RGB composite only
        if ffrun(["-i", exr, "-pix_fmt", "rgb24", out("cellhash")]):
            print(f"[ladder-00] cellhash.png")

    elif "VarMaturityMu" in base:
        # Composite: R=var, G=maturity, B=mu — cache quality
        ffrun(["-i", exr, "-pix_fmt", "rgb24", out("quality_var_maturity_mu")])
        ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out("quality__variance")])
        ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out("quality__maturity")])
        ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out("quality__mu")])
        print(f"[ladder-00] quality_var_maturity_mu + splits")

    elif "VarMaturityLevel" in base:
        # Composite: R=probeSteps, G=sampleCount, B=level — hash health
        ffrun(["-i", exr, "-pix_fmt", "rgb24", out("health_probe_count_level")])
        ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", out("health__probesteps")])
        ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", out("health__samplecount")])
        ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", out("health__level")])
        print(f"[ladder-00] health_probe_count_level + splits")

print(f"[ladder-00] Post-processing done.")
exit()

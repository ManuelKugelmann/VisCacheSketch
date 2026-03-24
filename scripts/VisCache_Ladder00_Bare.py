"""
VisCache_Ladder00_Bare.py — Step 0: Bare minimum cache.

1 level, no jitter, pMin=1.0 (always trace, never skip rays),
no variance gate, no decay, no eviction.
Tests: hash insert + lookup + diagnostic write at the simplest setting.

Expected output: blocky grid on vcFrameLevelProbesSamplesCold, uniform mu per cell,
full coverage (every NEE pixel should have data).
"""
import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr_split import split_diag_exrs

kWarmupFrames = 1024
scene_file = os.environ.get("SCENE_FILE", "media/Arcade/Arcade.pyscene")
scene_name = os.path.splitext(os.path.basename(scene_file))[0]

# Override defaults for bare minimum config
overrides = {
    "numLevels": 1,
    "cellACoarse": 0.06,     # ~6cm cells — compromise between resolution and maturity
    "autoTuneCells": False,
    "bootThreshold": 4,      # low threshold — mature quickly for visualization
    "pMin": 1.0,             # always trace — no RR skipping
    "enableVisCacheJitter": False,
    "enableVisCacheDirDistAddr": False,
    "enableVisCacheVarianceGate": False,
    "enableVisCacheWarpReduction": False,
    "enableVisCacheDecay": False,
    "enableVisCachePressureEvict": False,
}
if overrides.get("enableVisCacheDirDistAddr", False):
    addr_mode = "pointXdirdist"
else:
    addr_mode = "pointXpoint"
kCaptureDir = f"captures/ladder/00_{addr_mode}_{scene_name}"

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

# Post-process: convert EXR to named viridis PNGs
split_diag_exrs(kCaptureDir, sections=["basic"])

print(f"[ladder-00] Post-processing done.")
exit()

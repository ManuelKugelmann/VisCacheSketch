"""
VisCache_LadderCommon.py — Shared infrastructure for ladder test steps.

Provides:
- VARIANTS: addressing mode configurations
- BASE: shared base config (1 level, no jitter, all features off)
- run_variants(): execute all variants × frame configs, capture + postprocess
- postprocess(): EXR → named PNG extraction with grid layout
"""
import os, sys, subprocess, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer

try:
    from falcor import *
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
kResX = 512
kResY = 512

# Shared base: 1 level, no jitter, all features off, always trace
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

# Addressing variants (1 = collapsed/single bucket)
VARIANTS = [
    ("pos_pos", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.06,
    }),
    ("pos_posB", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.061,      # slightly different → no canonicalization
    }),
    ("pos_pos1", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 10000.0,
    }),
    ("pos_dir1_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 360.0,
        "distBCoarse": 1000.0,
    }),
    ("pos_dir_dist1", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,
        "distBCoarse": 1000.0,
    }),
    ("pos_dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 45.0,
        "distBCoarse": 0.24,
    }),
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def ffrun(args):
    try:
        subprocess.run(["ffmpeg", "-y"] + args, capture_output=True, timeout=10)
        return True
    except Exception:
        return False

def _out(d, name, prefix=""):
    return os.path.join(d, f"{prefix}{name}.png")

def postprocess(captureDir, prefix):
    """Extract named PNGs from EXR composites. Grid layout:
    Row 1 (accum): var_mat_mu, var, mat, mu, pad, pad, render
    Row 2 (snap):  var_mat_mu, var, mat, mu, probe_samp_level, probesteps, samplecount
    Row 3 (output): render, error, noise, raysaved, pad, pad, pad
    """
    p = prefix
    for exr in glob.glob(os.path.join(captureDir, "*.exr")):
        base = os.path.basename(exr)
        if "vcDiag." in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", _out(captureDir, "accum_1_var_mat_mu", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "accum_2_var", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "accum_3_mat", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", _out(captureDir, "accum_4_mu", p)])
        elif "VarMaturityMu" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", _out(captureDir, "snap_1_var_mat_mu", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "snap_2_var", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "snap_3_mat", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:g=0", "-pix_fmt", "rgb24", _out(captureDir, "snap_4_mu", p)])
        elif "VarMaturityLevel" in base:
            ffrun(["-i", exr, "-pix_fmt", "rgb24", _out(captureDir, "snap_5_probe_samp_level", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=g=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "snap_6_probesteps", p)])
            ffrun(["-i", exr, "-vf", "lutrgb=r=0:b=0", "-pix_fmt", "rgb24", _out(captureDir, "snap_7_samplecount", p)])

    # Row 3: Mogwai outputs
    vn = prefix.rstrip("_").rsplit("_", 1)[0] if "_s_" in prefix else prefix.rstrip("_")
    # Find the variant's base capture name (before the frame tag)
    parts = prefix.rstrip("_").split("_")
    # The Mogwai base filename is the variant name (set as fc.baseFilename)
    for pat, name in [("ToneMapper.dst.", "output_1_render"),
                      ("Error.output.", "output_2_error"),
                      ("Noise.output.", "output_3_noise"),
                      ("RaySavedPct.output.", "output_4_raysaved")]:
        for png in glob.glob(os.path.join(captureDir, f"*{pat}*")):
            shutil.copy(png, _out(captureDir, name, p))
            break

    # Render in accum row
    for png in glob.glob(os.path.join(captureDir, f"*ToneMapper.dst.*")):
        shutil.copy(png, _out(captureDir, "accum_7_render", p))
        break

    # Padding
    for slot in ["accum_5__", "accum_6__", "output_5__", "output_6__", "output_7__"]:
        ffrun(["-f", "lavfi", "-i", f"color=black:s={kResX}x{kResY}:d=1", "-frames:v", "1",
               "-pix_fmt", "rgb24", _out(captureDir, slot, p)])

def run_variants(step_name, frame_configs, scene_file, variants=None, maxBounces=1, mogwai_globals=None):
    """Run all variants × frame configs for a ladder step.
    mogwai_globals: pass globals() from the Mogwai script to access m, fc, etc.
    """
    if variants is None:
        variants = VARIANTS
    # Get Mogwai builtins from caller's globals
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_variants needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]

    for (variant_name, overrides) in variants:
        for (warmup, averaging) in frame_configs:
            captureDir = f"captures/ladder/{step_name}/{scene_name}"
            tag = f"s_{warmup}_{averaging}"
            print(f"\n[{step_name}] ======== {variant_name} {tag} ({scene_name}) ========")

            saved = {}
            for k, v in overrides.items():
                if k in VISCACHE_DEFAULTS:
                    saved[k] = VISCACHE_DEFAULTS[k]
                VISCACHE_DEFAULTS[k] = v

            g = render_graph_PathTracer(viscache=True, maxBounces=maxBounces)

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

            # Reset accum for clean averaging
            if warmup > 0:
                g.getPass("VisCache").set_properties({"resetAccum": True})

            # Phase 2: averaging
            for _ in range(averaging):
                m.renderFrame()

            fc.capture()
            m.renderFrame()

            print(f"[{step_name}] Captured ({tag})")
            postprocess(captureDir, f"{tag}_{variant_name}_")

            # Delete raw EXRs
            for f in glob.glob(os.path.join(captureDir, "*.exr")):
                os.remove(f)

            m.removeGraph(g)

    print(f"\n[{step_name}] All done.")

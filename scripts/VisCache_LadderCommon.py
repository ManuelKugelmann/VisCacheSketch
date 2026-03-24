"""
VisCache_LadderCommon.py — Shared infrastructure for ladder test steps.

Provides:
- VARIANTS: addressing mode configurations
- BASE: shared base config (1 level, no jitter, all features off)
- run_variants(): execute all variants × frame configs, capture + postprocess
- postprocess(): EXR → named PNG extraction with grid layout
"""
import os, sys, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS
from PathTracer_Graph import render_graph_PathTracer
from viscache_exr import write_channel, load_coldmiss_mask, find_exr

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
    ("posA_posB", {
        **BASE,
        "enableVisCacheDirDistAddr": False,
        "cellBCoarse": 0.12,       # 2x posA (0.06) → no canonicalization
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
        "angularBCoarse": 5.0,
        "distBCoarse": 1000.0,
    }),
    ("pos_dir_dist", {
        **BASE,
        "enableVisCacheDirDistAddr": True,
        "angularBCoarse": 5.0,
        "distBCoarse": 0.24,
    }),
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _out(d, name, prefix=""):
    return os.path.join(d, f"{prefix}{name}.png")

def _wc(exr, ch, outpath, coldmiss=None, normalize_max=False):
    """Shorthand for write_channel with logging."""
    result = write_channel(exr, ch, outpath, coldmiss=coldmiss, normalize_max=normalize_max)
    if result:
        print(f"  [exr] {os.path.basename(result)}")
    return result

def postprocess(captureDir, prefix, variant_name, resX=kResX, resY=kResY):
    """Extract named PNGs from EXR composites and rename Mogwai outputs.
    Filters by variant_name to avoid cross-variant contamination.

    9-column grid (r<row>c<col> prefix):
    Row 1 (accum): render, raysTraced, error, maturity, mean, variance, coldmiss, posAHash, noise
    Row 2 (frame): level, raysTraced, sampleCount, maturity, mean, variance, coldmiss, posBHash, probeSteps
    """
    vn = variant_name
    o = lambda name: _out(captureDir, name, prefix)
    exrs = glob.glob(os.path.join(captureDir, f"{vn}.*.exr"))

    # Load separate coldmiss masks for accum vs frame rows
    cm_accum = load_coldmiss_mask(exrs, mode="accum")  # never-hit pixels across all frames
    cm_frame = load_coldmiss_mask(exrs, mode="frame")  # no cache entry this frame

    # --- Row 1: accumulated ---
    exr = find_exr(exrs, "AccumRaysNoiseErrorCold")
    if exr:
        _wc(exr, 0, o("r1c2_accum_raystraced"), coldmiss=cm_accum)
        _wc(exr, 2, o("r1c3_accum_error"),      coldmiss=cm_accum)
        _wc(exr, 3, o("r1c7_accum_coldmiss"))
        _wc(exr, 1, o("r1c9_accum_noise"),      coldmiss=cm_accum)
    exr = find_exr(exrs, "AccumMeanVarMatCount")
    if exr:
        _wc(exr, 1, o("r1c4_accum_maturity"),   coldmiss=cm_accum)
        _wc(exr, 2, o("r1c5_accum_mean"),       coldmiss=cm_accum)
        _wc(exr, 0, o("r1c6_accum_variance"),   coldmiss=cm_accum)
    exr = find_exr(exrs, "FrameHashAHashBHashABRays")
    if exr: _wc(exr, 0, o("r1c8_accum_posAhash"), coldmiss=cm_accum)

    # --- Row 2: per-frame ---
    exr = find_exr(exrs, "FrameHashAHashBHashABRays")
    if exr:
        _wc(exr, 3, o("r2c2_frame_raystraced"), coldmiss=cm_frame)
        _wc(exr, 1, o("r2c8_frame_posBhash"),   coldmiss=cm_frame)
    exr = find_exr(exrs, "FrameLevelProbesSamplesCold")
    if exr:
        _wc(exr, 0, o("r2c1_frame_level"),       coldmiss=cm_frame)
        _wc(exr, 2, o("r2c3_frame_samplecount"), coldmiss=cm_frame)
        _wc(exr, 3, o("r2c7_frame_coldmiss"))
        _wc(exr, 1, o("r2c9_frame_probesteps"),  coldmiss=cm_frame)
    exr = find_exr(exrs, "FrameMeanVarMatSamplesRaw")
    if exr:
        _wc(exr, 1, o("r2c4_frame_maturity"),   coldmiss=cm_frame)
        _wc(exr, 2, o("r2c5_frame_mean"),       coldmiss=cm_frame)
        _wc(exr, 0, o("r2c6_frame_variance"),   coldmiss=cm_frame)

    # --- Copy ToneMapper render to accum row ---
    for src in glob.glob(os.path.join(captureDir, f"{vn}.ToneMapper.dst.*")):
        shutil.copy2(src, o("r1c1_accum_render"))
        break

    # Delete colormap outputs (1-frame delay makes them unreliable for ladders)
    # (ColorMapPass heatmaps removed — raw RGBA channels captured directly now)

def run_variants(step_name, frame_configs, scene_file, variants=None,
                  maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None):
    """Run all variants × frame configs for a ladder step.
    mogwai_globals: pass globals() from the Mogwai script to access m, fc, etc.
    """
    if variants is None:
        variants = VARIANTS
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_variants needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    res_tag = f"{resX}x{resY}"

    for (variant_name, overrides) in variants:
        for (warmup, averaging) in frame_configs:
            captureDir = f"captures/ladder/{step_name}/{scene_name}"
            tag = f"s_{warmup}_{averaging}_{res_tag}"
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
            m.resizeFrameBuffer(resX, resY)

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
            postprocess(captureDir, f"{tag}_{variant_name}_", variant_name, resX, resY)

            # Delete raw EXRs and leftover Mogwai outputs (ignore locked files)
            for f in glob.glob(os.path.join(captureDir, f"{variant_name}.*")):
                try:
                    os.remove(f)
                except PermissionError:
                    pass

            m.removeGraph(g)

    print(f"\n[{step_name}] All done.")


def run_baseline(step_name, frame_configs, scene_file,
                 maxBounces=0, resX=kResX, resY=kResY, mogwai_globals=None):
    """Run vanilla PathTracer (no VisCache) as baseline reference.
    Captures only the tonemapped render — no diagnostics.
    """
    g_dict = mogwai_globals or {}
    m = g_dict.get('m')
    fc = g_dict.get('fc')
    if m is None or fc is None:
        raise RuntimeError("run_baseline needs mogwai_globals=globals() from a Mogwai script")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    res_tag = f"{resX}x{resY}"

    for (warmup, averaging) in frame_configs:
        captureDir = f"captures/ladder/{step_name}/{scene_name}"
        tag = f"s_{warmup}_{averaging}_{res_tag}"
        print(f"\n[{step_name}] ======== vanilla_baseline {tag} ({scene_name}) ========")

        g = render_graph_PathTracer(viscache=False, maxBounces=maxBounces)
        m.addGraph(g)
        m.loadScene(scene_file)
        m.resizeFrameBuffer(resX, resY)

        os.makedirs(captureDir, exist_ok=True)
        fc.outputDir = captureDir
        fc.baseFilename = "vanilla"

        for _ in range(warmup):
            m.renderFrame()
        for _ in range(averaging):
            m.renderFrame()

        fc.capture()
        m.renderFrame()

        print(f"[{step_name}] Captured ({tag})")

        # Rename render to grid naming
        for src in glob.glob(os.path.join(captureDir, "vanilla.ToneMapper.dst.*")):
            shutil.copy2(src, _out(captureDir, "r1c1_accum_render", f"{tag}_vanilla_"))
            break

        # Cleanup leftover Mogwai outputs
        for f in glob.glob(os.path.join(captureDir, "vanilla.*")):
            try:
                os.remove(f)
            except PermissionError:
                pass

        m.removeGraph(g)

    print(f"\n[{step_name}] All done.")

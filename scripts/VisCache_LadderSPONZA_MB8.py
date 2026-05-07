"""
VisCache_LadderSPONZA_MB8.py — Sponza b=8/b=16 multibounce asymptote.

SPONZA_MB showed rays-savings INCREASE with bounce depth: b=0=−68pp,
b=1=−72pp, b=4=−74pp. Does the trend continue past b=4 or saturate?

Sweep: Sponza × b ∈ {8, 16} at x4 with the canonical:
  cell4×4 + bayer2×2 + ct=8 + stderr=0.10 + pm=0.02
  (stderr=0.10 supersedes vt=0.001 per ALL_STDERR.)

Auto-renders missing vanilla_b{8,16}_x4096 GTs. Each GT is ~12 min on
Sponza, but they cache once for future multibounce sweeps.

3 captures (vanilla_b8_x4 if missing, vanilla_b16_x4 if missing,
viscache_canonical_b{8,16}_x4) plus 2 GT renders ≈ 30-40 min.

Pass criterion: rays_traced_pct continues to drop monotonically with
b past b=4, OR plateaus at the firefly floor — either is informative.
The metric trade (perceptual win vs linear-space loss) should hold the
same per-bounce shape from SPONZA_MB.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_MB8 -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor, kResX, kResY,
    run_baseline,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "SPONZA_MB8"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

# Canonical with stderr=0.10 replacing vt=0.001 per ALL_STDERR validation.
CANONICAL_VC = {
    "bootThreshold":                  8,
    "matureThreshold":                32,
    "varThreshold":                   0.10,    # legacy fallback (stderr takes precedence)
    "stderrThreshold":                0.10,    # canonical
    "pMin":                           0.02,
    "bayerN":                         2,
    "forceDescendFootprintPx":        16,
    "bootThresholdFactorFootprintPx": 0.0,
    "cascadeWindowForward":           12,
    "enableHierarchicalConsistency":  False,
    "hierarchicalMuTolerance":        0.20,
    "accelDecayDisagreeThresh":       0.0,
    "numLevels":                      8,
    "autoTuneCells":                  True,
    "enableVisCacheAdaptivePMin":     True,
    "enableVisCacheVarianceGate":     True,
    "enableVisCacheDecay":            True,
}

MB_VALUES = [8, 16]


def _gt(scene_name, variant_tag="vanilla"):
    src_dir = f"captures/ladder/00/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_{variant_tag}_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, variant_tag)
    return gt_hdr, floor


for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    for mb in MB_VALUES:
        run_baseline(
            step_name="00", frame_configs=[(0, 0, 1)],
            scene_file=scene_file, resX=res, resY=res,
            maxBounces=mb, gt_spp=4096, extra_spp=[4],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
        )

    for mb in MB_VALUES:
        gt_var = f"vanilla_b{mb}"
        gt_hdr, floor = _gt(scene_name, gt_var)
        if gt_hdr is None:
            print(f"[SPONZA_MB8] {scene_name} {gt_var} GT missing — skip mb={mb}")
            continue

        def _build(spp, mb=mb):
            return render_graph_PathTracer(
                viscache=True, maxBounces=mb,
                samplesPerPixel=spp, useJitter=True,
                extraVCProps=CANONICAL_VC,
            )

        tag = f"viscache_canonical_b{mb}"
        _run_baseline_variant(
            STEP, [(0, 0, 1)], scene_file, tag,
            _build, "AccumulatePass.output",
            capture_spps=(4,), maxBounces=mb,
            resX=res, resY=res, mogwai_globals=globals(),
            gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
        )

_HEADLESS_SCRIPT_DONE = True

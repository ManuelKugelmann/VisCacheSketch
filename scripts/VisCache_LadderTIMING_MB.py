"""
VisCache_LadderTIMING_MB.py — multibounce wall-clock comparison.

Sponza b=4 has 74% rays saved per SPONZA_MB. The single-bounce TIMING
sweep revealed a wall-clock LOSS on saturated-light scenes due to the
fixed per-pixel hash-overhead. Multibounce should flip this: with 74%
rays skipped, the per-pixel hash lookup is amortized across multiple
bounces' shadow rays, expected to deliver real wall-clock savings.

Sponza × b={0, 4} at x4 SPP:
  - vanilla b=0 (single-bounce baseline)
  - vanilla b=4 (multi-bounce baseline)
  - cache b=0 canonical (stderr=0.10)
  - cache b=4 canonical (stderr=0.10)

Pass criterion: cache b=4 wall-clock < vanilla b=4 wall-clock by a
margin proportional to 74% rays-saved (expected ~50%+ wall-clock).
This validates the multibounce-is-where-cache-shines claim with
real ms numbers.

Output dirs:
  TIMING_MB_VAN/  — vanilla b={0, 4} captures + CSV
  TIMING_MB/      — cache canonical b={0, 4} captures + CSV

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s TIMING_MB -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor,
    run_baseline,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "TIMING_MB"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

CANONICAL_VC = {
    "bootThreshold":                  8,
    "matureThreshold":                32,
    "varThreshold":                   0.001,
    "stderrThreshold":                0.10,
    "wilsonZSquared":                 0.0,
    "muShrinkZSquared":               0.0,
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

MB_VALUES = [0, 4]


def _gt(scene_name, variant_tag="vanilla"):
    src_dir = f"captures/ladder/TIMING_MB_VAN/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_{variant_tag}_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, variant_tag)
    return gt_hdr, floor


for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    vanCaptureDir = f"captures/ladder/TIMING_MB_VAN/{scene_name}"
    captureDir    = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(vanCaptureDir, exist_ok=True)
    os.makedirs(captureDir,    exist_ok=True)

    # Vanilla per-bounce baselines (separate step dir to dodge schema collision).
    for mb in MB_VALUES:
        run_baseline(
            step_name="TIMING_MB_VAN", frame_configs=[(0, 0, 1)],
            scene_file=scene_file, resX=res, resY=res,
            maxBounces=mb, gt_spp=4096, extra_spp=[4],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
        )

    # Cache canonical per bounce.
    for mb in MB_VALUES:
        gt_var = f"vanilla_b{mb}"
        gt_hdr, floor = _gt(scene_name, gt_var)
        if gt_hdr is None:
            print(f"[TIMING_MB] {scene_name} {gt_var} GT missing — skip mb={mb}")
            continue

        def _build(spp, mb=mb):
            return render_graph_PathTracer(
                viscache=True, maxBounces=mb,
                samplesPerPixel=spp, useJitter=True,
                extraVCProps=CANONICAL_VC,
            )

        tag = f"viscache_canonical_b{mb}"
        # force_actual_spp=1 + frames=4 → 4 frame-accumulation renders per
        # variant. Profiler needs multiple frames for a stable average;
        # single-frame renders return invalid -1 averages and the gpu_ms
        # column comes out empty (observed previously on b=0).
        _run_baseline_variant(
            STEP, [(0, 0, 4)], scene_file, tag,
            _build, "AccumulatePass.output",
            capture_spps=(4,), maxBounces=mb,
            force_actual_spp=1,
            resX=res, resY=res, mogwai_globals=globals(),
            gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
        )

_HEADLESS_SCRIPT_DONE = True

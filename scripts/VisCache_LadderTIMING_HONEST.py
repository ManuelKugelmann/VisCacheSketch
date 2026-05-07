"""
VisCache_LadderTIMING_HONEST.py — harness-honest vanilla-vs-cache wall-clock.

Bypasses run_baseline / run_variants / _run_baseline_variant entirely.
Both vanilla and cache render through the SAME minimal render loop
within a single Mogwai invocation — same renderFrame mechanics, same
warmup, same number of frames, profiler enabled identically.

The prior TIMING / TIMING_MB attempts had vanilla and cache going
through different harness paths (run_baseline vs run_variants vs
_run_baseline_variant), which embedded ~18× cross-run variance in
the absolute ms numbers. This script eliminates that confound — both
paths are measured the same way back-to-back.

Sponza × b ∈ {0, 4} at x4 SPP:
  - vanilla b=0 / vanilla b=4
  - cache canonical (stderr=0.10) b=0 / cache canonical b=4

Output: stdout-only table; no CSV upsert (avoids the
baseline-vs-variant schema collision). Ratios within this single
Mogwai run are the honest comparison.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s TIMING_HONEST -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, _load_scene_if_needed, kResX, kResY,
)
from PathTracer_Graph import render_graph_PathTracer
try:
    from falcor import *
except ImportError:
    pass

STEP = "TIMING_HONEST"
res = int(os.environ.get("RES", "512"))
SPP = 1                  # cache is designed for 1-SPP-per-frame + multi-frame accumulation
                          # (the actual real-time use case). Every frame's a 1-SPP draw;
                          # cache state warms across consecutive frames.
RENDER_FRAMES = 16        # measure 16 steady-state frames after warmup
N_WARMUP = 64             # 64 frames warmup so the cache reaches steady-state cell maturity
                          # before measurement begins. Earlier 4-8 warmup was too short —
                          # cache was still cold when we measured.

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


def measure_one(m, fc, label, build_fn):
    """Build graph via build_fn(), warmup N_WARMUP frames, reset stats,
    render RENDER_FRAMES frames, return (label, gpu_tracepass_ms,
    gpu_total_ms). Removes the graph after."""
    g = build_fn()
    m.addGraph(g)
    try:
        m.profiler.enabled = True
    except Exception:
        pass
    for _ in range(N_WARMUP):
        m.renderFrame()
    try:
        m.profiler.reset_stats()
    except Exception:
        pass
    for _ in range(RENDER_FRAMES):
        m.renderFrame()

    pt = None; tot = None
    try:
        events = m.profiler.events
        for k, v in events.items():
            if "/gpu_time" not in k or not isinstance(v, dict):
                continue
            avg = v.get("average", -1.0)
            if avg is None or avg <= 0:
                continue
            base = k.rsplit("/gpu_time", 1)[0]
            if base.endswith("/PathTracer/tracePass"):
                pt = float(avg)
            elif base.endswith("/onFrameRender/RenderGraphExe::execute()") \
              or base.endswith("/onFrameRender"):
                tot = float(avg)
    except Exception:
        pass

    m.removeGraph(g)
    return (label, pt, tot)


for scene_file in get_scenes(default=["Sponza"]):
    print(f"\n[TIMING_HONEST] === {scene_file} ===")
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    _load_scene_if_needed(m, scene_file, res, res)

    results = []
    for mb in (0, 4):
        # Vanilla
        results.append(measure_one(
            m, fc, f"vanilla_b{mb}",
            lambda mb=mb: render_graph_PathTracer(
                viscache=False, maxBounces=mb, samplesPerPixel=SPP, useJitter=True,
            ),
        ))
        # Cache canonical
        results.append(measure_one(
            m, fc, f"cache_b{mb}",
            lambda mb=mb: render_graph_PathTracer(
                viscache=True, maxBounces=mb, samplesPerPixel=SPP, useJitter=True,
                extraVCProps=CANONICAL_VC,
            ),
        ))

    print(f"\n[TIMING_HONEST] === Results ({scene_name}, x{SPP}, {RENDER_FRAMES} frames + {N_WARMUP} warmup) ===")
    print(f"  {'config':<15} {'tracepass_ms':>13} {'total_ms':>10}")
    for label, pt, tot in results:
        pt_str = f"{pt:.3f}" if pt is not None else "-"
        tot_str = f"{tot:.3f}" if tot is not None else "-"
        print(f"  {label:<15} {pt_str:>13} {tot_str:>10}")

    print()
    print(f"  {'comparison':<25} {'vanilla_ms':>11} {'cache_ms':>10} {'saved':>8}")
    by_label = {l: pt for l, pt, _ in results if pt is not None}
    for mb in (0, 4):
        v = by_label.get(f"vanilla_b{mb}")
        c = by_label.get(f"cache_b{mb}")
        if v is not None and c is not None:
            pct = 100 * (v - c) / v
            print(f"  Sponza b={mb} canonical {v:>11.2f} {c:>10.2f} {pct:>+7.1f}%")

_HEADLESS_SCRIPT_DONE = True

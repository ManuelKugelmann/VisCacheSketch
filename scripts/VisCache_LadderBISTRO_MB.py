"""
VisCache_LadderBISTRO_MB.py — Bistro multibounce verification at canonical.

SPONZA_MB showed cache delivers -74pp rays at b=4 with err matched. Test
whether this generalizes to firefly-class scenes (BistroExt, BistroInt).
At multibounce, even firefly-class should benefit: each bounce adds new
shadow rays the cache can amortize, and the per-bounce cache hit rate
is independent of the firefly-floor on the directly-lit pass.

Sweep: cell4×4 + bayer2×2 + ct=8 + vt=0.10 + pm=0.02 + maxBounces ∈
{0, 1, 4} on BistroExt + BistroInt at x4. Compares against
vanilla_b{0,1,4}_x4096 GTs from step 00.

3 maxBounces × 1 vt × 2 scenes × 1 SPP = 6 captures. ~10 min Bistro is
slower than Sponza but no x16 here.

Pass criterion: rays_traced_pct drops at b=4 vs b=0 (cache amortizes
multibounce shadow rays), and full metric battery shows acceptable
trade — paying with linear-space variance for rays cost is fine, but
art5 must stay at-or-below vanilla.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s BISTRO_MB \\
        -c "BistroExterior,BistroInterior"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor, kResX, kResY,
    run_baseline,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "BISTRO_MB"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

# SPONZA_VT canonical — same config, different scenes.
CANONICAL_VC = {
    "bootThreshold":                  8,
    "matureThreshold":                32,
    "varThreshold":                   0.10,
    "pMin":                           0.02,
    "bayerN":                         2,
    "forceDescendFootprintPx":        16,
    "stderrThreshold":                0.0,
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

MB_VALUES = [0, 1, 4]


def _gt(scene_name, variant_tag="vanilla"):
    src_dir = f"captures/ladder/00/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_{variant_tag}_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, variant_tag)
    return gt_hdr, floor


for scene_file in get_scenes(default=["BistroExterior", "BistroInterior"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # Ensure multibounce vanilla GTs exist in step 00 (Bistro scenes were
    # missing vanilla_b{1,4}_x4096 — render them once, cached). Each
    # GT ~5-10 min; happens once then reused by all future multibounce
    # tests on these scenes.
    for mb in (1, 4):
        run_baseline(
            step_name="00", frame_configs=[(0, 0, 1)],
            scene_file=scene_file, resX=res, resY=res,
            maxBounces=mb, gt_spp=4096, extra_spp=[4],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
        )

    for mb in MB_VALUES:
        gt_var = "vanilla" if mb == 0 else f"vanilla_b{mb}"
        gt_hdr, floor = _gt(scene_name, gt_var)
        if gt_hdr is None:
            print(f"[BISTRO_MB] {scene_name} {gt_var} GT missing — skip mb={mb}")
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

"""
VisCache_LadderSPONZA_MB.py — multibounce + cache on Sponza, validated config.

SMOKE A earlier tested viscache_b{1,4} on Sponza using VISCACHE_DEFAULTS
(ct=32, vt=0.10, pm=0.05) — neutral err result. SPONZA_CT + SPONZA_VT
since established the new canonical (ct=8 + vt=0.10 at x4 / vt=0.001 at
x16). This run repeats SMOKE A with the proper config — Stage E pre-
flight: does the SPONZA-canonical generalize to multibounce?

Sweep: cell4×4 + bayer2×2 + ct=8 + vt={0.10, 0.001} + pm=0.02 +
maxBounces ∈ {0 (DI baseline), 1, 4} on Sponza at x4 (canonical
multibounce-friendly SPP). Compares against `vanilla_b{0,1,4}_x4096`
GTs already in step 00.

3 maxBounces × 2 vt × 1 scene × 1 SPP = 6 captures. ~3-5 min.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s SPONZA_MB \\
        -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor, kResX, kResY,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "SPONZA_MB"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

# SPONZA_CT/VT canonical config (overrides VISCACHE_DEFAULTS).
SPONZA_CANONICAL_VC = {
    "bootThreshold":                  8,        # ct=8 (SPONZA_CT knee)
    "matureThreshold":                32,       # 4× ct
    "varThreshold":                   0.10,     # SPP-varies; x4 winner; will override per variant
    "pMin":                           0.02,
    "bayerN":                         2,
    "forceDescendFootprintPx":        16,       # cell4×4
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

VT_VALUES = {"vt010": 0.100, "vt001": 0.001}
MB_VALUES = [0, 1, 4]

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

    for vt_tag, vt in VT_VALUES.items():
        for mb in MB_VALUES:
            gt_var = "vanilla" if mb == 0 else f"vanilla_b{mb}"
            gt_hdr, floor = _gt(scene_name, gt_var)
            if gt_hdr is None:
                print(f"[SPONZA_MB] {scene_name} {gt_var} GT missing — skip mb={mb}")
                continue

            vc_overrides = {**SPONZA_CANONICAL_VC, "varThreshold": vt}

            def _build(spp, mb=mb, vc_overrides=vc_overrides):
                return render_graph_PathTracer(
                    viscache=True, maxBounces=mb,
                    samplesPerPixel=spp, useJitter=True,
                    extraVCProps=vc_overrides,
                )

            tag = f"viscache_canonical_{vt_tag}_b{mb}"
            _run_baseline_variant(
                STEP, [(0, 0, 1)], scene_file, tag,
                _build, "AccumulatePass.output",
                capture_spps=(4,), maxBounces=mb,
                resX=res, resY=res, mogwai_globals=globals(),
                gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
            )

_HEADLESS_SCRIPT_DONE = True

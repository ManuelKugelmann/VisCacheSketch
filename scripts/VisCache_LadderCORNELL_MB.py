"""
VisCache_LadderCORNELL_MB.py — Cornell multibounce verification at canonical.

SPONZA_MB and BISTRO_MB demonstrated cache benefits scale with bounce
depth on penumbra-class (Sponza) and firefly-class (BistroInt). Test
the framework on the 4 Cornell scenes — diverse lighting characteristics
in a fast-rendering envelope (~1 min/render).

Sweep: cell4×4 + bayer2×2 + ct=8 + vt=0.10 + pm=0.02 + maxBounces ∈
{0, 1, 4} on all 4 Cornell scenes at x4. Auto-renders missing
vanilla_b{1,4}_x4096 GTs for Cornell_1PL and Cornell_3AL.

4 scenes × 3 maxBounces = 12 captures + 2 missing GTs × 2 bounces
≈ 16 captures total. ~15-20 min Mogwai.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s CORNELL_MB
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor, kResX, kResY,
    run_baseline,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "CORNELL_MB"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

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
DEFAULT_SCENES = [
    "CornellBox_1AreaLight", "CornellBox_1PointLight",
    "CornellBox_3AreaLights", "CornellBox_32PointLights",
]


def _gt(scene_name, variant_tag="vanilla"):
    src_dir = f"captures/ladder/00/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_{variant_tag}_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, variant_tag)
    return gt_hdr, floor


for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # Auto-render missing multibounce vanilla GTs in step 00 (cached if present).
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
            print(f"[CORNELL_MB] {scene_name} {gt_var} GT missing — skip mb={mb}")
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

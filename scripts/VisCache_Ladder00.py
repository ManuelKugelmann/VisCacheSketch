"""
VisCache_Ladder00.py — Step 00: Vanilla baselines (no VisCache).

Reference renders for L2 error and noise comparison. Renders x1 SPP
(error baseline) + x4096 SPP ground truth (noise baseline) per scene.

Usage:
    Mogwai.exe --headless -s scripts/VisCache/VisCache_Ladder00.py
"""
import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_baseline, run_baseline_wsrestir, run_baseline_pixel_restir,
    run_baseline_rtxdi, get_scenes, finalize_baseline,
    make_baseline_comparison_plate, make_baseline_bar_plot,
)

res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    baseline_dir = f"captures/ladder/00/{scene_name}"
    if os.path.exists(baseline_dir):
        shutil.rmtree(baseline_dir, ignore_errors=True)

    # 1. Vanilla baseline FIRST — produces the GT HDR all variants compare to.
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        gt_spp=4096,
        extra_spp=[2, 4, 8, 16],
        mogwai_globals=globals(),
    )

    # 2. Pure per-pixel ReSTIR (WS layer disabled) — isolates the screen-space
    #    temporal+spatial reservoir from the world-space cell hint layer.
    run_baseline_pixel_restir(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # 3. Full WS-ReSTIR DI (per-pixel + WS-cell hint).
    run_baseline_wsrestir(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # 4. RTXDI external reference (proper-implementation quality bar).
    run_baseline_rtxdi(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1,),
        mogwai_globals=globals(),
    )

    # 5. Comparison plates per scene at x1 (and x4 where available) — render
    #    + GT-error grid stitched side-by-side across {vanilla, pixel_restir,
    #    wsrestir, rtxdi}.
    make_baseline_comparison_plate("00", scene_file, resX=res, resY=res, spp=1)
    make_baseline_comparison_plate("00", scene_file, resX=res, resY=res, spp=4,
                                    variants=("vanilla", "pixel_restir", "wsrestir"))

finalize_baseline("00")

# Bar plot across all scenes / variants / SPPs from the populated CSV.
make_baseline_bar_plot("00")

_HEADLESS_SCRIPT_DONE = True

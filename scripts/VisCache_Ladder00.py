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
    #    Uses the graph's default maxBounces (3), which is also the canonical
    #    GT all subsequent ladder steps reference.
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        gt_spp=4096,
        extra_spp=[2, 4, 8, 16],
        mogwai_globals=globals(),
    )

    # 1b. Multi-bounce vanilla baselines — same SPP grid, varying maxBounces.
    #     Uses variant_tag="vanilla_b<N>" so these don't collide with the
    #     canonical "vanilla" outputs above. No separate GT (4096 spp) is
    #     rendered for these — they share the canonical vanilla GT for
    #     error/noise comparisons.
    #
    #     Used by: WS-PT validation matrix (validates path-space reuse against
    #     vanilla PT at multiple bounce regimes; ReSTIRPTPass port currently
    #     broken so vanilla multi-bounce is the trustworthy comparator).
    for mb in (1, 4, 8):
        run_baseline(
            step_name="00",
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            gt_spp=4096,            # ignored when variant_tag != "vanilla"
            extra_spp=[2, 4, 8, 16],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
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

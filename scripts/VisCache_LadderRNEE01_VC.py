"""
VisCache_LadderRNEE01_VC.py — RNEE01_VC: ReSTIR NEE + VisCache visibility.

Sibling of RNEE00 (vblind baseline). Runs the same nee_F16 / nee_F16R3d
variants with VisCachePass `enableVisCacheVisibilityCheck=True` +
`enableVisCacheLightSelection=True`, producing `_vc` tag variants that
pair 1:1 with the vblind baselines.

What this measures:
  - Does VisCache visibility-cache amortization help K-RIS NEE quality?
  - On each scene-class regime, what's the delta on err / rmse / psnr /
    flip / ms_ssim?
  - rays_traced_pct is now informative (cache hits replace explicit
    shadow rays at NEE call sites).

Same NEE architecture (K=16, every-vertex K-RIS, optional cell-reservoir
fold). VC toggles are the only change.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE01_VC -c CornellBox_3AreaLights
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE01_VC -c "<scenes>"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE01_VC      # default ALL_SCENES
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRNEEPass_F16_vc,
    run_baseline_ReSTIRNEEPass_F16R3d_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RNEE01_VC"
res = int(os.environ.get("RES", "512"))

# Same bounce set as RNEE00 for direct vblind-vs-VC comparison.
NEE_BOUNCES = (1, 4, 8)

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16),
        mogwai_globals=globals(),
    )

    # GT note: per-bounce vanilla_b{1,4,8} GTs live in Ladder00. Same
    # GT as RNEE00 — delta vs vblind is purely the cache effect.

    # === VC-on variants ===
    for mb in NEE_BOUNCES:
        run_baseline_ReSTIRNEEPass_F16_vc(STEP, [(0, 0, 1)], scene_file,
                                          maxBounces=mb, **common)
        run_baseline_ReSTIRNEEPass_F16R3d_vc(STEP, [(0, 0, 1)], scene_file,
                                             maxBounces=mb, **common)

make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

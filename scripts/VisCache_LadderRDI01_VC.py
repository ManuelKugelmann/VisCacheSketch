"""
VisCache_LadderRDI01_VC.py — RDI01_VC: ReSTIR DI + VisCache visibility/light cache.

Sibling of RDI00 (vblind baseline). Runs the same R2dP2d / R3dP3d /
PureKRIS variants with VisCache's V-aware target pdf engaged
(`visInPHat=1`), producing `_vcache` tag variants that pair 1:1 with
the `_vblind` baselines.

What this measures:
  - Does VisCache visibility-cache amortization reduce K-RIS variance
    by eliminating the "RIS picks shadowed bright sample" failure mode?
  - On each scene-class regime, what's the |VC| - |vblind| delta on
    err / rmse / psnr / flip / ms_ssim?
  - rays_traced_pct is now informative (cache hits replace explicit
    shadow rays). Cell-pool warmup overhead and visibility-cache
    eviction policies become visible levers.

Same architecture as the vblind baselines — VisCache is opt-in via
the `visInPHat=1` flip; everything else (K, mCap, sampler, biasCorrection,
spatial K/radius) is identical so the delta is attributable to the cache.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI01_VC -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI01_VC -c "<scenes>"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI01_VC      # default ALL_SCENES

Outputs:
  - per-variant 4×3 diagnostic plates per scene
    (runtime/captures/ladder/RDI01_VC/<scene>/plates/)
  - reference-comparison plot per scene
    (runtime/captures/ladder/RDI01_VC/reference_comparison_<scene>.png)
  - cross-step ladder_progress.png updated to include this step
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc,
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline_vc,
    run_baseline_ReSTIRDI_R2dP2d_PureKRIS_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RDI01_VC"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16),
        mogwai_globals=globals(),
    )

    # GT note: vanilla GT lives in Ladder00 (direct-only). VC variants
    # compare against the same GT as the vblind baselines so the delta
    # is purely the cache effect.

    # === VisCache-enabled variants (visInPHat=1, _vcache tag) ===
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dP2d_PureKRIS_vc(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline_vc(STEP, [(0, 0, 1)], scene_file, **common)

# === Reference-comparison plot ===
make_baseline_reference_comparison_plot(STEP)

# RDI01_VC publishes VC-on variants for comparison against RDI00; no winner.
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

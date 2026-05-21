"""
VisCache_LadderRNEE00.py — RNEE00 BASELINE.

Mirrors RDI00 (DI) and RPT00 (PT) on the NEE side: establishes the
cache-less reference floor for ReSTIR NEE before any ablation work.
Runs ONLY the canonical NEE references — no "ours" variants yet (those
land in RNEE01+).

  nee_kris_F16_b{1,4,8} — Pure K-RIS NEE (F=16 candidates). NOT ReSTIR
                          — no reservoir, no reuse, just better single-
                          shot light selection. Should match vanilla PT
                          in expected value but with lower per-frame
                          noise (sqrt(F)=4× reduction). GT resolved
                          from Ladder00's `vanilla_b{N}_x4096` captures
                          (shared with RPT00).
  nee_F16R3d_b{1,4,8}   — Pure K-RIS NEE + 3D cell reservoirs. IS
                          ReSTIR — the cell IS the reservoir, identity-
                          stream merge IS the reuse. vblind here
                          (reservoirK=1, lo=0 prescribed safe config per
                          project_kslot_archcontext). Bottoms-out the
                          cell-reuse mechanism for VisCache integration
                          in RNEE01_VC.

All variants are visibility-blind p̂ baselines (V via post-shadow trace
at NEE event), matching the recipe used in RDI00 / RPT00. VisCache-
amortized V is a later step.

Frame-accumulation SPP emulation: `actual_spp=1, num_frames=spp` — same
convention as the other baseline ladders, so noise is apples-to-apples
across RDI00 / RNEE00 / RPT00.

This is intentionally LEAN — every variant here is a reference comparator.
It is NOT the place for K-slot / step-C / Fibonacci-footprint sweeps;
those live in later ladder steps (RNEE01+) where the *improvement over
baseline* is what's being measured.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE00 -c CornellBox_3AreaLights
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE00 -c "CornellBox_3AreaLights,Sponza"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RNEE00      # default ALL_SCENES

Outputs (after finalize_step at end):
  - per-variant 4×3 diagnostic plates per scene
    (runtime/captures/ladder/RNEE00/<scene>/plates/)
  - cross-variant overview plot
    (runtime/captures/ladder/RNEE00/_overview.png)
  - cross-step ladder_progress.png updated to include this step
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRNEEPass_F16,
    run_baseline_ReSTIRNEEPass_F16R3d,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RNEE00"
res = int(os.environ.get("RES", "512"))

# NEE bounce set matches RPT00's 1/4/8 — apples-to-apples cross-step.
# b=1 = direct-only sanity. b=4 / b=8 exercise cell-reuse depth.
NEE_BOUNCES = (1, 4, 8)

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16, 64),
        mogwai_globals=globals(),
    )

    # GT note: per-bounce vanilla_b{1,4,8} GTs live in Ladder00; the
    # `_resolve_gt_for_variant` resolver finds them there via the matching
    # variant_tag. Run `-s 00` first if GTs aren't already present.

    # === ReSTIRNEEPass references (vblind, no VisCache) ===
    # F=16 K-RIS pure (no cells) — the sqrt(F) noise-reduction floor.
    # F=16 + R3d (with cell reservoirs at default safe config K=1 lo=0) —
    # the cell-reuse layer that VisCache will later amortise visibility on.
    for mb in NEE_BOUNCES:
        run_baseline_ReSTIRNEEPass_F16(
            STEP, [(0, 0, 1)], scene_file, maxBounces=mb, **common
        )
        run_baseline_ReSTIRNEEPass_F16R3d(
            STEP, [(0, 0, 1)], scene_file, maxBounces=mb, **common
        )

# === Reference-comparison plot: variants vs bounce-matched vanilla, per metric ===
# One figure per scene, lines across SPP for rmse/psnr/flip/ms_ssim/oklab/
# gpu_trace. No rays_traced — baseline-only step, caching enters RNEE01+.
make_baseline_reference_comparison_plot(STEP)

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] — RNEE00 publishes baselines, not winners. Improvement
# tracking begins in RNEE01.
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

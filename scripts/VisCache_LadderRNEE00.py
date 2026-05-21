"""
VisCache_LadderRNEE00.py — RNEE00 BASELINE.

Mirrors RDI00 (DI) and RPT00 (PT) on the NEE side: establishes the
cache-less reference floor for ReSTIR NEE before any ablation work.
Runs ONLY the canonical NEE references — no "ours" variants yet (those
land in RNEE01+).

  vanilla_b{1,3}    — Falcor PathTracer multi-bounce vanilla NEE reference.
                      b=1 (direct-only) is the cheapest sanity check;
                      b=3 (default ReSTIR NEE depth) is the parity target.
                      Provides the x4096 GT each nee_*_b{N} is compared
                      against (variant_tag matches so the GT resolver
                      pairs them up).
  nee_F16_b{1,3}    — ReSTIRNEEPass pure K-RIS (F=16 candidates, no
                      cell reservoirs, no VisCache). The sqrt(F)=4×
                      noise-reduction reference for our cell-reservoir
                      enhancement; should match vanilla PT in expected
                      value but with lower per-frame noise.
  nee_F16R3d_b{1,3} — Pure K-RIS NEE + 3D cell reservoirs (vblind,
                      reservoirK=1, lo=0 — the prescribed safe config
                      per project_kslot_archcontext). Bottoms-out the
                      cell-reuse mechanism for VisCache integration in
                      RNEE01+.

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
    get_scenes, run_baseline,
    run_baseline_ReSTIRNEEPass_F16,
    run_baseline_ReSTIRNEEPass_F16R3d,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RNEE00"
res = int(os.environ.get("RES", "512"))

# NEE bounces to test. b=1 = direct-only sanity. b=3 = ReSTIR NEE prescribed
# default (cell-reuse mechanism engages at primary + 2 indirect bounces).
NEE_BOUNCES = (1, 3)

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16, 64),
        mogwai_globals=globals(),
    )

    # === Multi-bounce vanilla references ===
    # Provides per-bounce x4096 GT; variant_tag pairs each GT with its
    # corresponding nee_*_b{N}.
    for mb in NEE_BOUNCES:
        run_baseline(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            gt_spp=4096,
            extra_spp=[2, 4, 8, 16],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
        )

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

"""
VisCache_Ladder00.py — Step 00: Canonical baseline matrix.

All references + all our implementations side-by-side. The goal is a clean
baseline ladder where each "ours" variant is within sampling-noise of its
paired reference — the validation step before any feature ablation.

DI side (current):
  - vanilla     — path tracer DI reference (NEE, single-bounce).
  - rtxdi       — external RTXDIPass; the ReSTIR DI reference.
  - restir_2d   — our 2D ReSTIR DI (tile pool + per-pixel reservoir);
                  visibility-blind p̂, RTXDI-faithful recipe.
                  Should match `rtxdi` within noise.
  - restir_3d   — our 3D ReSTIR DI (cell pool + cell-merged reservoir);
                  world-space analog of `restir_2d`. No reprojection
                  needed (cell ID camera-invariant).
                  Should match `restir_2d` within noise.

PT side (future):
  - vanilla_b{1,4,8}  — path tracer multi-bounce reference.
  - restirpt_b{1,4,8} — DQLin ReSTIR PT (port of NVlabs F8) reference.
  - restir_pt_2d / restir_pt_3d — our ReSTIR PT (TBD).

All variants are visibility-blind p̂ baselines (V comes via post-RIS shadow
+ V=0 invalidation, matching RTXDI's and DQLin's recipes). V-aware p̂ is
an improvement that lives in a separate ablation step.

Pure ReSTIR track: visibilityCheck=False on our variants. The combination
with VisCache (cache-amortized V) is a future ladder step.

Frame-accumulation SPP emulation everywhere: `actual_spp=1, num_frames=spp`
(vanilla via its low-SPP branch; rtxdi/restir_* via `force_actual_spp=1`).
Identical accumulator semantics → apples-to-apples noise comparison.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 00 -c <SCENES>
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_baseline, run_baseline_rtxdi,
    run_baseline_restir_2d, run_baseline_restir_3d,
    run_baseline_reference_restirpt,
    get_scenes, finalize_baseline,
    make_baseline_comparison_plate, make_baseline_bar_plot,
)

res = int(os.environ.get("RES", "512"))

# Iterating on `restir_*` variants typically. Wipe only those captures so
# vanilla GT (x4096, ~4 min/scene) and rtxdi reference stay cached. Set
# RECLEAN=1 to force full rmtree instead.
RECLEAN = os.environ.get("RECLEAN", "0") not in ("0", "", "false", "False")

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    baseline_dir = f"captures/ladder/00/{scene_name}"
    if RECLEAN and os.path.exists(baseline_dir):
        import shutil
        shutil.rmtree(baseline_dir, ignore_errors=True)
    elif os.path.exists(baseline_dir):
        # Additive iteration: only clear the variants under active iteration
        # so cached vanilla/rtxdi captures + GTs survive.
        for pattern in ("s_*restir_2d*", "s_*restir_3d*"):
            for f in glob.glob(os.path.join(baseline_dir, pattern)):
                try: os.remove(f)
                except OSError: pass

    # 1. Vanilla baseline FIRST — provides x4096 GT for error metric.
    run_baseline(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        gt_spp=4096,
        extra_spp=[2, 4, 8, 16],
        mogwai_globals=globals(),
    )

    # 1b. Multi-bounce vanilla PathTracer — `vanilla_b{1,4,8}`. Shares the
    #     canonical x4096 GT from (1); variant_tag prevents output collision.
    #     Provides per-bounce-depth PT references for the ReSTIRPT comparison
    #     in (1c). Additive: untouched by the `restir_2d`/`restir_3d` cleanup
    #     in the loop header.
    for mb in (1, 4, 8):
        run_baseline(
            step_name="00",
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            gt_spp=4096,
            extra_spp=[2, 4, 8, 16],
            mogwai_globals=globals(),
            variant_tag=f"vanilla_b{mb}",
        )

    # 1c. DQLin ReSTIRPT reference — canonical (ReSTIR mode) and BPR (Bekaert
    #     path reuse). Both share the RTXDI direct feed; both validated against
    #     vanilla_b{N}_x4096 GT.
    for mb in (1, 4, 8):
        run_baseline_reference_restirpt(
            step_name="00",
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_b{mb}",
        )
        run_baseline_reference_restirpt(
            step_name="00",
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_bpr_b{mb}",
            pathSamplingMode="PathReuse",
        )
        # Lin 2026 §6.1 Stage A — unified DI+GI in one ReSTIR reservoir
        # (no external RTXDI feed). Probe variant; canonical reference
        # (`restirpt_b{N}`) preserved above for ablation comparison.
        run_baseline_reference_restirpt(
            step_name="00",
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_unified_b{mb}",
            unifiedDIGI=True,
        )

    # 2. RTXDI external reference — the parity target.
    #    RTXDI = 1-sample-per-frame; x4 = 4 frames into accumulator.
    run_baseline_rtxdi(
        step_name="00",
        frame_configs=[(0, 0, 1)],
        scene_file=scene_file,
        resX=res, resY=res,
        capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # 3. restir_2d — our 2D ReSTIR DI (RTXDI-faithful: blind p̂, V via post-RIS shadow).
    run_baseline_restir_2d(
        step_name="00", frame_configs=[(0, 0, 1)], scene_file=scene_file,
        resX=res, resY=res, capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # 4. restir_3d — world-space 3D analog (also blind, same recipe).
    run_baseline_restir_3d(
        step_name="00", frame_configs=[(0, 0, 1)], scene_file=scene_file,
        resX=res, resY=res, capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # 5. Comparison plate per scene at x1 across all baselines.
    make_baseline_comparison_plate(
        "00", scene_file, resX=res, resY=res, spp=1,
        variants=("vanilla", "rtxdi", "restir_2d_vblind", "restir_3d_vblind"),
    )

finalize_baseline("00")

# Bar plot across all scenes / variants / SPPs from the populated CSV.
make_baseline_bar_plot("00")

_HEADLESS_SCRIPT_DONE = True

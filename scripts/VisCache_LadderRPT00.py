"""
VisCache_LadderRPT00.py — RPT00 BASELINE.

Mirrors RDI00's role on the PT side: establishes the cache-less reference
floor for ReSTIR PT before any ablation work. Runs ONLY the canonical PT
references — no "ours" variants yet (those land in RPT01+).

  restirpt_b{1,4,8}            — DQLin ReSTIR PT (reservoir resampling
                                 across temporal + spatial neighbours)
                                 with Lin §15 chroma-preserving clamp
                                 `fireflyClampK=100`. Biased but stable.
  restirpt_unclamped_b{1,4,8}  — Same algorithm, `fireflyClampK=1e9` (no
                                 clamp). Paper-canonical unbiased but
                                 firefly-unstable. Pairs with the clamped
                                 variant for cost-of-clamp measurement
                                 and for the V-aware-eliminates-clamp
                                 hypothesis in RPT01_VC.
  pathreuse_b{1,4,8}           — Bekaert path reuse (NOT ReSTIR — no
                                 reservoir resampling). Same plugin
                                 (`ReSTIRPTPass` with `pathSamplingMode=
                                 PathReuse`) and same shift machinery,
                                 but deterministic shift only. Stable
                                 without firefly clamping; clamped at
                                 K=100 for consistency. Same GT.

All variants ride RTXDI for direct lighting (matches the DQLin recipe) and
are visibility-blind p̂ (V via post-RIS shadow + V=0 invalidation, matching
the recipe used in RTXDI / DQLin). VisCache-amortized V is a later step.

Frame-accumulation SPP emulation everywhere: `actual_spp=1, num_frames=spp`
— identical accumulator semantics as RDI00 / Ladder00, so noise statistics
are apples-to-apples across the three baseline ladders.

This is intentionally LEAN — every variant here is a reference comparator.
It is NOT the place for fireflyClampK / spatialNeighborCount / sampling-mode
sweeps; those live in later ladder steps (RPT01+) where the *improvement
over baseline* is what's being measured.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT00 -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT00 -c "Sponza,BistroInterior"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT00      # default ALL_SCENES

Outputs (after finalize_step at end):
  - per-variant 4×3 diagnostic plates per scene
    (runtime/captures/ladder/RPT00/<scene>/plates/)
  - cross-variant overview plot
    (runtime/captures/ladder/RPT00/_overview.png)
  - cross-step ladder_progress.png updated to include this step
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline_reference_restirpt,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RPT00"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # GT note: per-bounce vanilla_b{1,4,8} GTs live in Ladder00; the
    # `_resolve_gt_for_variant` resolver finds them there via the matching
    # variant_tag. Run `-s 00` first if GTs aren't already present.

    # === DQLin ReSTIR PT references (clamped + unclamped + path-reuse) ===
    # All share RTXDI for direct illumination; all validated against the
    # paired vanilla_b{N} GT in Ladder00.
    for mb in (1, 4, 8):
        # Clamped reservoir resampling (Lin §15 K=100, default).
        run_baseline_reference_restirpt(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_b{mb}",
        )
        # Unclamped paper-canonical (K=1e9, no clamp). Pairs with the
        # clamped variant — RPT01_VC tests whether VisCache V-in-pHat
        # eliminates the need for the clamp.
        run_baseline_reference_restirpt(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_unclamped_b{mb}",
            fireflyClampK=1e9,
        )
        # Bekaert path-reuse mode (no reservoir resampling). Clamped at
        # K=100 for consistency; not paired unclamped because BPR doesn't
        # have the temporal+spatial reservoir-merge firefly amplification.
        run_baseline_reference_restirpt(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"pathreuse_b{mb}",
            pathSamplingMode="PathReuse",
        )
        # Lin 2026 §6.1 Stage A — unified DI+GI in one ReSTIR reservoir
        # (no external RTXDI feed). DISABLED 2026-05-06 pending Phase 1
        # §6.2.3 force-NEE shift MIS bookkeeping (.plans/restirpt-forced-
        # nee-reconnection.md). Re-enable when force-NEE MIS is corrected.
        # The `unifiedDIGI=True` path through run_baseline_reference_restirpt
        # is preserved; uncomment to probe.
        #run_baseline_reference_restirpt(
        #    step_name=STEP,
        #    frame_configs=[(0, 0, 1)],
        #    scene_file=scene_file,
        #    resX=res, resY=res,
        #    maxBounces=mb,
        #    capture_spps=(1, 4),
        #    mogwai_globals=globals(),
        #    variant_tag=f"restirpt_unified_b{mb}",
        #    unifiedDIGI=True,
        #)

# === Reference-comparison plot: variants vs DQLin restirpt + vanilla per metric ===
# One figure per scene, lines across SPP for rmse/psnr/flip/ms_ssim/oklab/
# gpu_trace. No rays_traced — baseline-only step, caching enters RPT01+.
make_baseline_reference_comparison_plot(STEP)

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] — RPT00 publishes baselines, not winners. Improvement
# tracking begins in RPT01.
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

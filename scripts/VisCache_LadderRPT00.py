"""
VisCache_LadderRPT00.py — RPT00 BASELINE.

Mirrors RDI00's role on the PT side: establishes the cache-less reference
floor for ReSTIR PT before any ablation work. Runs ONLY the canonical PT
references — no "ours" variants yet (those land in RPT01+).

  vanilla_b{1,4,8}     — Falcor PathTracer multi-bounce reference. Provides
                         the x4096 GT each restirpt_b{N} is compared
                         against (variant_tag matches so the GT resolver
                         pairs them up).
  restirpt_b{1,4,8}    — DQLin ReSTIR PT reference (port of NVlabs F8) in
                         ReSTIR mode. The parity target for our future
                         ReSTIRPT R2d/R3d implementations.
  restirpt_bpr_b{1,4,8}— DQLin ReSTIR PT reference in BPR (Bekaert path
                         reuse) mode. Different sampling strategy on top
                         of the same shift machinery.

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
    get_scenes, run_baseline, run_baseline_reference_restirpt,
    finalize_step,
)

STEP = "RPT00"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # === Multi-bounce vanilla references ===
    # Provides per-bounce x4096 GT for the ReSTIRPT comparison below.
    # variant_tag pairs each GT with its corresponding restirpt_b{N}.
    for mb in (1, 4, 8):
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

    # === DQLin ReSTIR PT references (canonical + BPR) ===
    # Both share RTXDI for direct illumination; both validated against
    # the paired vanilla_b{N} GT above.
    for mb in (1, 4, 8):
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
        run_baseline_reference_restirpt(
            step_name=STEP,
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

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] — RPT00 publishes baselines, not winners. Improvement
# tracking begins in RPT01.
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

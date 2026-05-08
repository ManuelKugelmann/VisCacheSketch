"""
VisCache_LadderRDI00.py — first step of the ReSTIRDI ladder stage.

Exercises the architectural-matrix factorial across all 5 implemented
ReSTIRDI variants on each scene. Each move from base R2dP2d to the next
variant isolates exactly one architectural decision — pool addressing,
+R3d, drop per-pixel layer, etc.

Variants:
  ReSTIRDI_R2dP2d     — strict RTXDI baseline (R2d per-pixel + screen-tile pool, no R3d)
  ReSTIRDI_R2dP3d     — strict + 3D pool (R3d still off; isolates pool-addressing change)
  ReSTIRDI_R2dR3dP2d  — adds cell-level reservoir (still screen-tile pool)
  ReSTIRDI_R2dR3dP3d  — full 3D both pool + cell reservoir (current canonical)
  ReSTIRDI_R3dP3d     — pure 3D, no per-pixel reservoir (cell at sub-pixel footprint)
  (ReSTIRDI_H2dR3dP3d is scaffold-only — slim per-pixel history; raises NotImplementedError)

Reference comparators: vanilla (no cache) + production RTXDI.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00 -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00 -c "Sponza,BistroInterior"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00      # default ALL_SCENES

Outputs (after finalize_step at end):
  - per-variant 4×3 diagnostic plates per scene
    (runtime/captures/ladder/RDI00/<scene>/plates/)
  - cross-variant overview plot showing rays / err / noise scatter
    (runtime/captures/ladder/RDI00/_overview.png)
  - cross-step ladder_progress.png updated to include this step
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline, run_baseline_rtxdi,
    run_baseline_ReSTIRDI_R2dP2d,
    run_baseline_ReSTIRDI_R2dP3d,
    run_baseline_ReSTIRDI_R2dR3dP2d,
    run_baseline_ReSTIRDI_R2dR3dP3d,
    run_baseline_ReSTIRDI_R3dP3d,
    run_baseline_ReSTIRDI_H2dR3dP3d,
    run_baseline_ReSTIRDI_R2dR3dP3d_noPre,
    run_baseline_ReSTIRDI_R2dR3dP3d_preOnly,
    run_baseline_ReSTIRDI_R2dR3dP3d_hybrid,
    run_baseline_ReSTIRDI_R3dP3d_noPre,
    # preOnlyLightBVH ruled out — LightBVH samples are pixel-conditional and
    # can't be shared across pool readers; pool/presampling pattern only makes
    # sense with shading-agnostic samplers (PdfMipmap).
    finalize_step, kResX, kResY,
)

STEP = "RDI00"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4),                     # x1 stresses cold-cell fallback path; x4 is the canonical
        mogwai_globals=globals(),
    )

    # === References ===
    # vanilla: auto-renders 1 + gt_spp; doesn't take capture_spps. extra_spp adds one extra SPP.
    run_baseline(STEP, [(0, 0, 1)], scene_file,
                 resX=res, resY=res, mogwai_globals=globals(),
                 extra_spp=[4])
    run_baseline_rtxdi(STEP, [(0, 0, 1)], scene_file, **common)       # RTXDI production

    # === Architectural matrix (5 variants) ===
    # Move-by-move:
    # base R2dP2d → switch pool to 3D (R2dP3d) → add R3d (R2dR3dP2d / R2dR3dP3d) → drop per-pixel (R3dP3d)
    run_baseline_ReSTIRDI_R2dP2d    (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dP3d    (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dR3dP2d (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dR3dP3d (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_H2dR3dP3d (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d    (STEP, [(0, 0, 1)], scene_file, **common)

    # === Fresh-vs-pool Pareto sweep, K_total=24 normalized ===
    # All variants run K_total = 24 (= RTXDI localLightCandidateCount) for
    # apples-to-apples architectural comparison. Sweep fresh-K from 0
    # (RTXDI-faithful pure pool) to 24 (no pool, pure main-pass LightBVH):
    #   F00P24 = preOnly (RTXDI-faithful)
    #   F01P23..F02P22 = pool-heavy hybrids
    #   F04P20..F08P16 = mid hybrids (F08P16 ≈ current default's split)
    #   F16P08         = fresh-heavy hybrid
    #   F24P00 = noPre (pure main-pass LightBVH)
    # Pre-pass is auto-enabled for poolK > 0; auto-disabled for poolK = 0.
    for freshK in (0, 1, 2, 4, 8, 16, 24):
        run_baseline_ReSTIRDI_R2dR3dP3d_hybrid(STEP, [(0, 0, 1)], scene_file,
                                               freshK=freshK, **common)
    # R3dP3d corner samples (pure 3D, no per-pixel layer) — kept narrow
    # because R3d-vs-R2d-pixel-layer is the H2d ladder's job.
    run_baseline_ReSTIRDI_R3dP3d_noPre(STEP, [(0, 0, 1)], scene_file, **common)

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] because RDI00 is not setting up a hand-off to RDI01
# yet — the architectural-matrix story is the output, not a pinned winner.
finalize_step(STEP, carried_winners=[])

# Headless-ladder convention: don't exit() — let the harness finalize.
_HEADLESS_SCRIPT_DONE = True

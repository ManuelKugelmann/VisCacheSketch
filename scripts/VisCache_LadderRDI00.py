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
    run_baseline_ReSTIRDI_R2dPR3d,
    run_baseline_ReSTIRDI_R3dPR3d,
    run_baseline_ReSTIRDI_H2dR3dP3d,
    run_baseline_ReSTIRDI_R2dR3dP3d_noPre,
    run_baseline_ReSTIRDI_R2dR3dP3d_preOnly,
    run_baseline_ReSTIRDI_R2dP2d_F00P24,
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

    # NOTE: every ReSTIRDI_* variant tag auto-appends _F{fresh:02d}P{pool:02d}
    # in _run_baseline_restir, so the CSV now reads e.g. ReSTIRDI_R2dP2d_F32P16
    # (default K_total = 48 = 32 fresh-LightBVH + 16 pool-draws), or
    # ReSTIRDI_R3dP3d_F24P00 for the noPre RTXDI-parity variant. Hybrid runners
    # set the F##P## explicitly; the auto-suffix sees it and skips.

    # === Architectural matrix (pruned 2026-05-11) ===
    # Variant lineage RTXDI → R2dP2d → R2dP3d → R3dP3d → (future) PR3d.
    #   R2dP2d   = our RTXDI ARCHITECTURAL EQUIVALENT (per-pixel reservoir + screen-tile pool).
    #              Measured cum Δ = −0.39pp WIN over RTXDI across 5-scene set at F00P24.
    #   R2dP3d   = bridge: same per-pixel layer, swap pool addressing to 3D world-cell.
    #   R3dP3d   = bridge: also swap per-pixel to world-keyed (camera-invariant).
    #   (future) R2dPR3d / R3dPR3d — replace P3d's raw pdf-pool with multi-reservoir pool (PR3d/ReGIR-at-tile).
    #   (defer)  HR2d (history-overlay on full R2d) — future extension for dynamic-camera fallback.
    # Dropped variants (validated as redundant via 5-scene A/B at N=1024 split-buffer):
    #   R2dR3dP2d, R2dR3dP3d — single-slot tile-R3d adds nothing (cum Δ +0.004 vs no-R3d)
    #   PR3d-alone           — no per-pixel layer = not ReSTIR
    #   H2dR3dP3d, H2dPR3d   — slim-history variants; HR2d (full R2d + history overlay) is the chosen future direction
    run_baseline_ReSTIRDI_R2dP2d    (STEP, [(0, 0, 1)], scene_file, **common)  # = RTXDI architectural mirror
    run_baseline_ReSTIRDI_R2dP3d    (STEP, [(0, 0, 1)], scene_file, **common)  # bridge: 3D pool
    run_baseline_ReSTIRDI_R3dP3d    (STEP, [(0, 0, 1)], scene_file, **common)  # bridge: + camera-invariant
    # PR3d (mode=1) retired 2026-05-11 — quality lift on Sponza (R3dPR3d x4
    # err=5.73 vs R3dP3d 5.91, −0.18pp) doesn't justify the 15-30× perf cost
    # on area-light scenes. Re-enable by uncommenting below if exploring
    # PR3d optimizations (skip-count-update, pixel-Bayer dispersion).
    # See memory project_pr3d_perf_investigation.md.
    if os.environ.get("ENABLE_PR3D"):
        run_baseline_ReSTIRDI_R2dPR3d   (STEP, [(0, 0, 1)], scene_file, **common)
        run_baseline_ReSTIRDI_R3dPR3d   (STEP, [(0, 0, 1)], scene_file, **common)

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

    # === True RTXDI architectural mirror ===
    # F00P24 with screen-tile pool + no R3d — direct apples-to-apples to
    # RTXDI production plugin at K_total=24.
    run_baseline_ReSTIRDI_R2dP2d_F00P24(STEP, [(0, 0, 1)], scene_file, **common)

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] because RDI00 is not setting up a hand-off to RDI01
# yet — the architectural-matrix story is the output, not a pinned winner.
finalize_step(STEP, carried_winners=[])

# Headless-ladder convention: don't exit() — let the harness finalize.
_HEADLESS_SCRIPT_DONE = True

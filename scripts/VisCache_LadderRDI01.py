"""
VisCache_LadderRDI01.py — RDI01 ARCHITECTURAL + K-BUDGET EXPLORATION.

Builds on the RDI00 cache-less RTXDI-parity baselines (R2dP2d_RTXDIBaseline,
R3dP3d_RTXDIBaseline). RDI01 sweeps the architectural-matrix + K-budget axes
while keeping visibility cache OFF — the goal here is to characterise the
*algorithmic* design space, not the cache acceleration:

  * Architectural matrix at the "current canonical" K=48 (32 fresh + 16
    pool): R2dP2d, R2dP3d, R3dP3d. Each variant isolates one architectural
    decision relative to its lineage neighbour (pool addressing, +R3d, drop
    per-pixel layer).
  * Fresh-vs-pool Pareto sweep at K_total = 24 (matched to RTXDI): swept
    over freshK ∈ {0,1,2,4,8,16,24}. Identifies whether the win is in
    pre-pass-amortised pool sampling, per-pixel BSDF-conditional fresh
    sampling, or a hybrid mix.
  * Corner samples: R2dP2d_F00P24 (RTXDI-architectural mirror at K=24, but
    mCap=5 — predates the baseline-mCap-20 alignment), R3dP3d_noPre (pure
    fresh, K=24).

Visibility cache features (visibilityCheck, lightSelection) stay OFF here —
those land in later ladder steps that measure cache *acceleration* over the
RDI00 baseline floor.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI01 -c Sponza
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline, run_baseline_rtxdi,
    run_baseline_ReSTIRDI_R2dP2d,
    run_baseline_ReSTIRDI_R2dP3d,
    run_baseline_ReSTIRDI_R3dP3d,
    run_baseline_ReSTIRDI_R2dPR3d,
    run_baseline_ReSTIRDI_R3dPR3d,
    run_baseline_ReSTIRDI_R2dR3dP3d_hybrid,
    run_baseline_ReSTIRDI_R2dP2d_F00P24,
    run_baseline_ReSTIRDI_R3dP3d_noPre,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline,
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline,
    finalize_step, kResX, kResY,
)

STEP = "RDI01"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4),
        mogwai_globals=globals(),
    )

    # === References (carried forward from RDI00) ===
    # vanilla + rtxdi are re-rendered here so RDI01 is self-contained for
    # the cross-variant overview plot. (Upsert-keyed; cached from RDI00 if
    # already on disk.)
    run_baseline(STEP, [(0, 0, 1)], scene_file,
                 resX=res, resY=res, mogwai_globals=globals(),
                 extra_spp=[4])
    run_baseline_rtxdi(STEP, [(0, 0, 1)], scene_file, **common)

    # === Baselines (re-rendered for at-a-glance comparison) ===
    # These are the RDI00 baselines; included here so the RDI01 overview
    # plot shows the floor that each experiment is improving (or not).
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)

    # === Architectural matrix at K=48 (current "canonical" K-budget) ===
    # Variant lineage RTXDI → R2dP2d → R2dP3d → R3dP3d. Each move isolates
    # one architectural decision:
    #   R2dP2d  — strict RTXDI architectural mirror (per-pixel reservoir +
    #             screen-tile pool). Cumulative Δ ≈ −0.39 pp WIN over RTXDI
    #             across the 5-scene matrix at K_total=48.
    #   R2dP3d  — bridge: swap pool addressing 2D → 3D world-cell.
    #   R3dP3d  — bridge: also swap per-pixel layer to world-keyed (pure
    #             camera-invariant 3D).
    # Dropped variants (validated as redundant via 5-scene A/B at N=1024
    # split-buffer): R2dR3dP2d, R2dR3dP3d (single-slot tile-R3d adds nothing,
    # cum Δ +0.004 vs no-R3d). H2dR3dP3d (slim-history) deferred —
    # full-history HR2d is the chosen future direction.
    run_baseline_ReSTIRDI_R2dP2d(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dP3d(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d(STEP, [(0, 0, 1)], scene_file, **common)

    # PR3d (mode=1) retired 2026-05-11 — quality lift on Sponza (R3dPR3d x4
    # err=5.73 vs R3dP3d 5.91, −0.18pp) doesn't justify the 15-30× perf cost
    # on area-light scenes. Re-enable by setting ENABLE_PR3D=1 if exploring
    # PR3d optimizations (skip-count-update, pixel-Bayer dispersion). See
    # memory project_pr3d_perf_investigation.md.
    if os.environ.get("ENABLE_PR3D"):
        run_baseline_ReSTIRDI_R2dPR3d(STEP, [(0, 0, 1)], scene_file, **common)
        run_baseline_ReSTIRDI_R3dPR3d(STEP, [(0, 0, 1)], scene_file, **common)

    # === Fresh-vs-pool Pareto sweep, K_total=24 normalized ===
    # All variants run K_total = 24 (= RTXDI localLightCandidateCount) for
    # apples-to-apples comparison. Sweep fresh-K from 0 (RTXDI-faithful pure
    # pool) to 24 (no pool, pure main-pass LightBVH):
    #   F00P24 = preOnly (RTXDI-faithful pure-pool)
    #   F01P23..F02P22 = pool-heavy hybrids
    #   F04P20..F08P16 = mid hybrids
    #   F16P08         = fresh-heavy hybrid
    #   F24P00 = noPre (pure main-pass LightBVH)
    # Pre-pass is auto-enabled for poolK > 0; auto-disabled for poolK = 0.
    for freshK in (0, 1, 2, 4, 8, 16, 24):
        run_baseline_ReSTIRDI_R2dR3dP3d_hybrid(STEP, [(0, 0, 1)], scene_file,
                                               freshK=freshK, **common)

    # R3dP3d corner sample (pure 3D, no per-pixel, no pre-pass) — kept
    # narrow because R3d-vs-R2d-pixel-layer is the H2d ladder's job.
    run_baseline_ReSTIRDI_R3dP3d_noPre(STEP, [(0, 0, 1)], scene_file, **common)

    # F00P24 with screen-tile pool + no R3d at mCap=5 — pre-RTXDIBaseline
    # variant kept here to show the mCap=5 → mCap=20 delta vs the baseline.
    run_baseline_ReSTIRDI_R2dP2d_F00P24(STEP, [(0, 0, 1)], scene_file, **common)

# === Cross-variant overview plot + ladder progress refresh ===
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

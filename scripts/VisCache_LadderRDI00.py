"""
VisCache_LadderRDI00.py — RDI00 BASELINE.

This step establishes the cache-less RTXDI-parity floor for ReSTIR DI. It
runs ONLY:

  vanilla                       — Falcor PathTracer, no cache, no ReSTIR.
  rtxdi                         — Falcor's production RTXDI plugin.
  ReSTIRDI_R2dP2d_RTXDIBaseline — our 2D track baseline (per-pixel R2d
                                  reservoir + screen-tile P2d pool).
  ReSTIRDI_R3dP3d_RTXDIBaseline — our 3D track baseline (pure R3d cell
                                  reservoir + world-cell P3d pool, no
                                  per-pixel layer).

Both `_RTXDIBaseline` variants mirror RTXDI's defaults at every knob:
  K = 24 (localLightCandidateCount), drawn from a PdfMipmap pre-pass that
  is the RTXDI presample-tile equivalent
  mCap = 20 (maxHistoryLength)
  spatial = 1 sample, radius 30 px
  visibility cache OFF (vblind, no visibilityCheck, no lightSelection)

This is intentionally LEAN — every variant here is either a reference
comparator (vanilla, rtxdi) or a baseline floor for one of the two
architecture branches we track (2D, 3D). It is NOT the place for K-budget
sweeps, sampler experiments, or feature ablations — those live in later
ladder steps (RDI01+) where the *improvement over baseline* is what's
being measured.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00 -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00 -c "Sponza,BistroInterior"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00      # default ALL_SCENES

Outputs (after finalize_step at end):
  - per-variant 4×3 diagnostic plates per scene
    (runtime/captures/ladder/RDI00/<scene>/plates/)
  - cross-variant overview plot (just 4 entries — references + 2 baselines)
    (runtime/captures/ladder/RDI00/_overview.png)
  - cross-step ladder_progress.png updated to include this step
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline, run_baseline_rtxdi,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline,
    run_baseline_ReSTIRDI_R2dP2d_RTXDISplit,
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline,
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

    # === Baselines — RTXDI-parity floor (cache-less) ===
    # 2D track: per-pixel R2d reservoir + screen-tile P2d pool. K=24 from
    # PdfMipmap pre-pass, mCap=20, vblind, no visibility cache.
    # 3D track: pure R3d cell reservoir at sub-pixel footprint + world-cell
    # P3d pool. Same K/mCap/sampler/cache settings.
    # Improvements over these baselines (visibility cache, V-aware target
    # pdf, larger K budgets, alternative samplers, architectural variants)
    # are measured in RDI01+.
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)
    # RTXDISplit (F0E8I8P24) — second attempt with proper SUB-RESERVOIR
    # architecture (RTXDI_SampleLightsForSurface analog). Env+inf samples
    # stream into category-private LocalReservoirs, then merge into the
    # compound `local` via streamingMergeReservoir. Hierarchical winner
    # selection (sub-roulette × compound-roulette) suppresses fat-tail
    # candidate adoption that the first single-reservoir attempt
    # (+43% Bistro rmse, see .agents/handoff 2026-05-15) ran into.
    run_baseline_ReSTIRDI_R2dP2d_RTXDISplit(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)

# === Cross-variant overview plot + ladder progress refresh ===
# carried_winners=[] — RDI00 publishes baselines, not winners. Improvement
# tracking begins in RDI01.
finalize_step(STEP, carried_winners=[])

# Headless-ladder convention: don't exit() — let the harness finalize.
_HEADLESS_SCRIPT_DONE = True

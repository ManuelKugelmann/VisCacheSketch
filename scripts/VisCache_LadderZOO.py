"""
VisCache_LadderZOO.py — ReSTIRDI variant zoo: exercise all 5 implemented
variants of the architectural matrix on a shared scene.

Variants:
  ReSTIRDI_R2dP2d     — strict RTXDI baseline (R2d per-pixel + screen-tile pool, no R3d)
  ReSTIRDI_R2dP3d     — strict + 3D pool (R3d still off; isolates pool addressing change)
  ReSTIRDI_R2dR3dP2d  — adds cell-level reservoir (still screen-tile pool)
  ReSTIRDI_R2dR3dP3d  — full 3D both pool + cell reservoir (current canonical)
  ReSTIRDI_R3dP3d     — pure 3D, no per-pixel reservoir (cell at sub-pixel footprint)
  (ReSTIRDI_H2dR3dP3d is scaffold-only — slim per-pixel history; raises NotImplementedError)

Reads as a factorial design: each move from one variant to the next isolates
exactly one architectural decision.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s ZOO -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s ZOO -c "Sponza,BistroInterior"
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
    kResX, kResY,
)

STEP = "ZOO"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(4,),
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
    # base R2dP2d → switch pool to 3D (R2dP3d) → add R3d (R2dR3dP3d → R2dR3dP2d) → drop pixel layer (R3dP3d)
    run_baseline_ReSTIRDI_R2dP2d   (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dP3d   (STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dR3dP2d(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R2dR3dP3d(STEP, [(0, 0, 1)], scene_file, **common)
    run_baseline_ReSTIRDI_R3dP3d   (STEP, [(0, 0, 1)], scene_file, **common)

# Headless-ladder convention: don't exit() — let the harness finalize.
_HEADLESS_SCRIPT_DONE = True

"""
VisCache_LadderRPT01.py — Tune `params.fireflyClampK` for the ReSTIRPT
reference. Sweeps K ∈ {1e9, 1000, 100, 30, 10} at b=4 x{1,4} per scene
against bounce-matched `vanilla_b4_x4096` GT (read from step 00).

GT lives in step 00 (`captures/ladder/00/<scene>/`); RPT01 only renders
the K-sweep restirpt variants. Run step 00 first.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 00     # GT first
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT01

Env vars:
    RES         : resolution (default 512)
    RECLEAN=1   : wipe captures/ladder/RPT01/<scene> before running
    K_VALUES    : space-separated K floats (default "1e9 1000 100 30 10")
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    run_baseline_reference_restirpt,
    get_scenes, finalize_baseline,
    make_baseline_comparison_plate, make_baseline_bar_plot,
)

res = int(os.environ.get("RES", "512"))
RECLEAN = os.environ.get("RECLEAN", "0") not in ("0", "", "false", "False")
K_VALUES = [float(x) for x in os.environ.get("K_VALUES", "1e9 1000 100 30 10").split()]
BOUNCE = 4
STEP = "RPT01"

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    baseline_dir = f"captures/ladder/{STEP}/{scene_name}"
    if RECLEAN and os.path.exists(baseline_dir):
        import shutil
        shutil.rmtree(baseline_dir, ignore_errors=True)

    for K in K_VALUES:
        K_tag = f"K{int(K)}" if K >= 1 else f"K{K:.3f}".replace(".", "p")
        run_baseline_reference_restirpt(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=BOUNCE,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_b{BOUNCE}_{K_tag}",
            fireflyClampK=K,
        )

    plate_variants = tuple(
        f"restirpt_b{BOUNCE}_K{int(K)}" if K >= 1 else f"restirpt_b{BOUNCE}_K{K:.3f}".replace(".", "p")
        for K in K_VALUES
    )
    for spp in (1, 4):
        make_baseline_comparison_plate(
            STEP, scene_file, resX=res, resY=res, spp=spp,
            variants=plate_variants,
        )

finalize_baseline(STEP)
make_baseline_bar_plot(STEP)

_HEADLESS_SCRIPT_DONE = True

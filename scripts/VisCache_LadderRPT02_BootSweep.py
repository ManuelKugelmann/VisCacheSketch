"""
VisCache_LadderRPT02_BootSweep.py — find 50% trace target on PT.

Per user 2026-05-27 /loop directive: experiment to reach 50% traced on
similar quality on all scenes.

Current state (RPT01_VC @ x16): PT shows 98% rays_traced on Sponza
because canonical bootThreshold=16 keeps primary maturity gate strict.
Old vanilla-PT ladder step 18 hit 12% rays_traced on Sponza at ct=2
(at ~2× rmse cost vs vanilla).

This step sweeps bootThreshold ∈ {2, 4, 8, 16} on PT (ReSTIRPT canonical)
with maxBounces=4 to find the sweet spot where rays_traced ≤ 50% on all
scenes AND quality stays close to canonical (bt=16) baseline.

Sweep: 4 bt × 3 scenes = 12 variants.

Scenes: Cornell_3AreaLights (control) + Sponza (medium-hard) +
BistroExterior (hardest).

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RPT02_BootSweep
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_reference_restirpt_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RPT02_BootSweep"
res = int(os.environ.get("RES", "512"))

BT_VALUES = [2, 4, 8, 16]
DEFAULT_SCENES = ["CornellBox_3AreaLights.pyscene",
                  "Sponza.pyscene",
                  "BistroExterior.pyscene"]

for scene_file in get_scenes(default=DEFAULT_SCENES):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16),
        mogwai_globals=globals(),
    )

    for bt in BT_VALUES:
        run_baseline_reference_restirpt_vc(
            STEP, [(0, 0, 1)], scene_file,
            maxBounces=4,
            variant_tag=f"restirpt_vc_b4_bt{bt:02d}_fpOff",
            extraVCProps={
                "bootThreshold": bt,
                # Turn off footprint floor so bt actually binds the maturity
                # gate (otherwise log2(cellPx) overrides low bt on coarse
                # cells — Sponza cells have cellPx >> 2^bt, floor wins).
                "bootThresholdFactorFootprintPx": 0.0,
            },
            **common
        )

make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

"""
VisCache_LadderRPT03_StderrSweep.py — relax convergence gate on PT.

RPT02 showed bootThreshold sweep had ZERO effect on PT trace rate
(identical numbers across bt ∈ {2,4,8,16}). Diagnosis: the bottleneck
isn't maturity (cells reach bootThreshold), it's CONVERGENCE — cells
mature but fail the stderr gate (`stderr² > gStderrThreshold²`) so the
cascade descends and ultimately fails to find a trusted cell.

This sweep relaxes stderrThreshold to let more cells qualify as
converged. Canonical = 0.10 (allows trust when sqrt(var/N) ≤ 0.10).
Looser threshold = more cells trusted = lower trace rate.

Sweep: 4 stderr values × 3 scenes = 12 variants.
  stderr ∈ {0.10, 0.20, 0.40, 0.80} — canonical to very-relaxed.

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RPT03_StderrSweep
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_reference_restirpt_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RPT03_StderrSweep"
res = int(os.environ.get("RES", "512"))

STDERR_VALUES = [0.10, 0.20, 0.40, 0.80]
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

    for se in STDERR_VALUES:
        run_baseline_reference_restirpt_vc(
            STEP, [(0, 0, 1)], scene_file,
            maxBounces=4,
            variant_tag=f"restirpt_vc_b4_se{int(se*100):03d}",
            extraVCProps={"stderrThreshold": se},
            **common
        )

make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

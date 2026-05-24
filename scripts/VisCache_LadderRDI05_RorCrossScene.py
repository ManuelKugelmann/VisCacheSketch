"""
VisCache_LadderRDI05_RorCrossScene.py — ror=1 (FullTrace) cross-scene check.

RDI04 found ror=2 (CacheCV) hurts err on Sponza/Bistro because trusted
cells return raw cached mu as visibility — biased single-sample
multiplier where cell mu has high within-cell variance.

ror=1 (FullTrace) traces every reval call — no mu-substitution, no bias.
Cost = +1.7pp rays on Cornell vs ror=0; question is whether that cost
holds on hard scenes AND quality stays err-stable.

Direct comparison: 3 modes × 3 scenes = 9 variants.

  ror0 = no reval (control)
  ror1 = FullTrace (always trace at reval, unbiased)
  ror2 = CacheCV (cache-routed, bias risk on diverse cells)

Hypothesis:
  Sponza/Bistro: ror1 keeps err parity with ror0 (small +rays cost),
                  ror2 regresses err (mu-bias).
  Cornell: all three near parity; ror2 wins slightly on rays.

If hypothesis holds, cross-scene recipe is: pick ror=1 for hard scenes,
ror=2 for easy/well-cached scenes. Or: ror=1 universally as the
"minimal additional rays" cross-scene answer.

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RDI05_RorCrossScene
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RDI05_RorCrossScene"
res = int(os.environ.get("RES", "512"))

DEFAULT_SCENES = ["CornellBox_3AreaLights.pyscene",
                  "Sponza.pyscene",
                  "BistroExterior.pyscene"]

# (ror, tag_suffix) — ror=1/2 already auto-tag via wrapper suffix
VARIANTS = [
    (0, "_ror0"),
    (1, ""),     # tag becomes "..._raytraced" via wrapper
    (2, ""),     # tag becomes "..._cachecv"  via wrapper
]

for scene_file in get_scenes(default=DEFAULT_SCENES):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16),
        mogwai_globals=globals(),
    )

    for ror, suffix in VARIANTS:
        run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc(
            STEP, [(0, 0, 1)], scene_file,
            maxBounces=0,
            retraceOnReuseMode=ror,
            tag_suffix_extra=suffix,
            **common
        )

# === Cross-variant overview plot + ladder progress refresh ===
make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

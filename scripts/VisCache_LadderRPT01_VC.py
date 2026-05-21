"""
VisCache_LadderRPT01_VC.py — RPT01_VC: ReSTIR PT + VisCache visibility/light cache.

Sibling of RPT00 (vblind baseline). Adds the VisCache-on counterparts of the
clamped and unclamped DQLin ReSTIR PT references:

  restirpt_vc_b{1,4,8}            — VisCache on, clamped (fireflyClampK=100)
  restirpt_vc_unclamped_b{1,4,8}  — VisCache on, unclamped (K=1e9)
                                    HEADLINE: does V-aware target pdf via
                                    VisCache eliminate the firefly explosion
                                    that K=1e9 produces without cache?

Skipped (per plan): pathreuse_vc — BPR mode doesn't have the temporal/spatial
reservoir-merge amplification that VisCache visibility cache addresses;
adding it doesn't isolate a distinct hypothesis.

Hypothesis matrix RPT00 + RPT01_VC together isolate:
  - Clamp cost (vblind):        restirpt_b{N}    vs restirpt_unclamped_b{N}
  - VC benefit on clamped:       restirpt_b{N}    vs restirpt_vc_b{N}
  - VC benefit on unclamped:     restirpt_unclamped_b{N} vs restirpt_vc_unclamped_b{N}
  - **VC-replaces-clamp claim:** restirpt_vc_unclamped_b{N} ≈ restirpt_b{N}
                                 → V-aware sampling makes the clamp unnecessary

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT01_VC -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT01_VC -c "<scenes>"
    runtime/pythondist/python.exe scripts/run_ladder.py -s RPT01_VC      # default ALL_SCENES
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline_reference_restirpt_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RPT01_VC"
res = int(os.environ.get("RES", "512"))

for scene_file in get_scenes():
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # GT note: per-bounce vanilla_b{1,4,8} GTs live in Ladder00. Same
    # GT as RPT00 — delta vs vblind is purely the cache effect.

    for mb in (1, 4, 8):
        # VC + clamped (Lin §15 K=100 default in helper).
        run_baseline_reference_restirpt_vc(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_vc_b{mb}",
        )
        # VC + unclamped (paper-canonical K=1e9). Tests the headline:
        # does V-aware target sampling neutralise the temporal+spatial
        # firefly amplification that K=1e9 produces without cache?
        run_baseline_reference_restirpt_vc(
            step_name=STEP,
            frame_configs=[(0, 0, 1)],
            scene_file=scene_file,
            resX=res, resY=res,
            maxBounces=mb,
            capture_spps=(1, 4),
            mogwai_globals=globals(),
            variant_tag=f"restirpt_vc_unclamped_b{mb}",
            fireflyClampK=1e9,
        )

make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

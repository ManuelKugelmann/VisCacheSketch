"""
VisCache_LadderRDI04_RevalLite.py — minimal-extra-ray revalidation.

Goal: improve on RDI03's `ror=0` (no-reval) baseline with **minimal**
additional ray cost. Ideally aggregate `rays_traced_pct` stays below
`vanilla (no VC anywhere)` everywhere, while keeping the err gain that
revalidation buys.

Observation from RDI03 Cornell_3AL:
  ror=0 (no reval): rays_traced_pct = 54.4%, err = 0.804% (x16)
  ror=1 FullTrace:  rays_traced_pct = 56.1%, err = 0.789% (x16)
  ror=2 CacheCV:    rays_traced_pct = 54.1%, err = 0.789% (x16)

ror=2 already *barely* moves aggregate rays vs ror=0 because reval
queries go through the cache and the cache absorbs them. The remaining
reval traces (~33% of reval queries at x16) are concentrated in
*immature* cells (cell count < bootThreshold). Make cells mature faster
→ even fewer reval traces.

Sweep design (5 variants):

  baseline_ror0           — RDI03's no-reval baseline (control)
  ror2_canonical          — RDI03's CacheCV baseline (already small extra)
  ror2_bt08               — CacheCV + bootThreshold=8 (trust earlier)
  ror2_pa48               — CacheCV + posACoarse=0.48 (coarser cells, denser obs)
  ror2_combo              — CacheCV + bt=8 + pa=0.48 (both levers)

Expected: ror2_combo aggregate rays_traced_pct ≤ ror0 baseline AND
err ≤ ror0 baseline. If yes, this is the "free quality bump" variant
the user asked for.

Scenes: Cornell_3AL (control where cells mature easily) +
Sponza/Bistro (cross-scene generalization — RDI02 showed bt/pa
levers help here much more).

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RDI04_RevalLite
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RDI04_RevalLite"
res = int(os.environ.get("RES", "512"))

DEFAULT_SCENES = ["CornellBox_3AreaLights.pyscene",
                  "Sponza.pyscene",
                  "BistroExterior.pyscene"]

# (ror, bt, pa, tag_suffix) — tag distinguishes; bt/pa flow through extraVCProps
VARIANTS = [
    (0, 16, 0.12, "_ror0_baseline"),       # control: no reval
    (2, 16, 0.12, "_ror2_canonical"),      # cacheCV at canonical cell settings
    (2,  8, 0.12, "_ror2_bt08"),           # cacheCV + lower boot threshold
    (2, 16, 0.48, "_ror2_pa48"),           # cacheCV + coarser cells
    (2,  8, 0.48, "_ror2_combo"),          # cacheCV + both levers
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

    for ror, bt, pa, suffix in VARIANTS:
        run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc(
            STEP, [(0, 0, 1)], scene_file,
            maxBounces=0,
            retraceOnReuseMode=ror,
            tag_suffix_extra=suffix,
            extraVCProps={
                "bootThreshold": bt,
                "posACoarse":    pa,
            },
            **common
        )

# === Cross-variant overview plot + ladder progress refresh ===
make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

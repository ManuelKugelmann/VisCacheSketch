"""
VisCache_LadderRDI03_RevalSweep.py — exercise the REVAL counter.

Per memory project_per_mode_session_complete_2026_05_23: DI's
rays_traced_reval_pct stays at 0 on every scene because
`retraceOnReuseMode=0` (Off) is the canonical default. The reuse-
revalidation V-test site is gated off entirely.

This step sweeps `retraceOnReuseMode ∈ {0, 1, 2}`:

  0 = Off (canonical, Basic-equiv) — REVAL site dormant; counter = 0
  1 = FullTrace (≡ RTXDI RayTraced) — every reused sample retraces;
      REVAL counter bumps via vcDiagCountRay direct call. Unbiased
      but pricier (one extra shadow ray per reused candidate).
  2 = CacheCV — reused sample retrace goes through vcVisibility_Ray;
      REVAL counter bumps via cache-routed path. Cheap once cache
      mature; unbiased via CV+RRR.

Sweep design: 3 modes × 3 scenes = 9 variants.

Scenes:
  CornellBox_3AreaLights — control (cache works well, modest reuse impact)
  Sponza — medium-hard (cache cold; mode 1 forces traces, mode 2 may help)
  BistroExterior — hardest (cache barely matures; mode 2 may approach mode 1)

Variant tag:
  R2dP2d_RTXDIBaseline_ror{0,1,2}_vcache

Expected per-mode behavior:
  ror0: rays_reval=0, rays_nee+prop unchanged from RDI01_VC baseline
  ror1: rays_reval=100% (FullTrace, no gating), err lower than ror0 (unbiased)
  ror2: rays_reval=somewhere-in-between, err similar to ror1 but cache-amortized

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RDI03_RevalSweep

Output:
  - Per-variant 4×3 diagnostic plates per scene
  - Cross-variant overview plot
  - LADDERLOG carry: which retraceOnReuseMode is the best quality/cost trade
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RDI03_RevalSweep"
res = int(os.environ.get("RES", "512"))

# retraceOnReuseMode values: 0=Off (canonical), 1=FullTrace, 2=CacheCV
ROR_VALUES = [0, 1, 2]
ROR_LABELS = {0: "off", 1: "fulltrace", 2: "cachecv"}

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

    for ror in ROR_VALUES:
        run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc(
            STEP, [(0, 0, 1)], scene_file,
            maxBounces=0,
            variant_tag=f"R2dP2d_RTXDIBaseline_ror{ror}_vcache",
            retraceOnReuseMode=ror,
            **common
        )

# === Cross-variant overview plot + ladder progress refresh ===
make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

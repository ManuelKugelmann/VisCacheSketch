"""
VisCache_LadderRDI02_CellTune.py — cross-scene cell-maturity tuning.

Targets the gap surfaced by RDI01_VC + per-mode-counter validation
(commit 02712ccd + memory project_per_mode_session_complete_2026_05_23):
Cornell hits ~54% rays_traced at canonical settings, but Sponza /
Bistro stay at ~98% because cells never reach `bootThreshold=16`
before frame end.

Cell maturity depends on per-cell observation density per frame. Two
levers we can tune cross-scene from the existing wrappers:

  posACoarse — coarser quant → bigger cells → MORE per-cell queries
              per frame → cells mature faster. Canonical = 0.12 (qa012).
  bootThreshold — lower trust threshold → cells trusted earlier in their
              life → savings show up at lower SPP. Canonical = 16.

Sweep design: 2×3 = 6 variants per scene.

  bootThreshold ∈ {8, 16}        (canonical 16 vs aggressive 8)
  posACoarse    ∈ {0.12, 0.24, 0.48}  (canonical, 2×, 4×)

Scenes: Cornell_3AreaLights (control — canonical worked here),
        Sponza (medium-hard),
        BistroExterior (hardest geometry).

Variant tag layout:
  <basevariant>_bt{08,16}_pa{12,24,48}_vcache  (e.g. R2dP2d_RTXDIBaseline_bt08_pa24_vcache)

Per-mode counters (rays_traced_{nee,reval,proposal,reconnect}_pct) tell
us WHICH mode benefits most from each setting — PROPOSAL is the main
target since visInPHat=1 reads dominate DI's cache traffic.

Usage:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RDI02_CellTune

  # Single-scene scoping:
  runtime/pythondist/python.exe scripts/run_ladder.py -s RDI02_CellTune -c Sponza

Output:
  - 4×3 diagnostic plates per variant per scene
  - cross-variant overview plot
  - LADDERLOG-relevant carry: lowest rays_traced_pct without err regression
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc,
    make_baseline_reference_comparison_plot,
    finalize_step,
)

STEP = "RDI02_CellTune"
res = int(os.environ.get("RES", "512"))

# Sweep axes
BT_VALUES = [8, 16]
PA_VALUES = [0.12, 0.24, 0.48]

# Targeted scene shortlist (override via SCENES env var). Per directive
# from project_per_mode_session_complete_2026_05_23, focus on the three
# scenes where the per-mode matrix already has comparison data.
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
        for pa in PA_VALUES:
            tag_suffix = f"_bt{bt:02d}_pa{int(pa*100):02d}"
            run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline_vc(
                STEP, [(0, 0, 1)], scene_file,
                maxBounces=0,
                variant_tag=f"R2dP2d_RTXDIBaseline{tag_suffix}_vcache",
                extraVCProps={
                    "bootThreshold": bt,
                    "posACoarse":    pa,
                    # Keep posBCoarse / dirBCoarse / distBCoarse at canonical
                    # values (merged in via _merge_canonical_vc); we're only
                    # sweeping the two axes that affect cell maturity.
                },
                **common
            )

# === Cross-variant overview plot + ladder progress refresh ===
make_baseline_reference_comparison_plot(STEP)
finalize_step(STEP, carried_winners=[])

_HEADLESS_SCRIPT_DONE = True

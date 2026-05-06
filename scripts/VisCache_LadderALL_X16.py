"""
VisCache_LadderALL_X16.py — canonical config validation across all scenes
at x{4, 16}.

Purpose: smoke kickoff for Stage C.2 (multi-level PT DI canonical
re-validation under current metric, per LADDER_PLAN). SPONZA_CT and
SPONZA_VT calibrated ct=8 + per-SPP vt on Sponza; check whether the
canonical generalizes (or what shape the per-scene gap takes) at the
high-SPP regime where vt should be tightest.

Two configs:
  - x4_canonical: ct=8 vt=0.10 pm=0.02 cell4x4 bayer2x2  (SPONZA_VT x4 carry)
  - x16_canonical: ct=8 vt=0.001 pm=0.02 cell4x4 bayer2x2 (SPONZA_VT x16 carry)

Each config is rendered at its native SPP per scene. 4 Cornell + Sponza +
BistroExt + BistroInt = 7 scenes × 2 SPPs = 14 captures. ~15-20 min.

Per the methodology rule: this is a *validation* sweep, not a parameter
sweep — it proves the SPONZA-derived per-SPP carry holds across the full
scene matrix, or surfaces the cases where it doesn't (those become
candidates for per-class carry tables). Either way the result earns a
LADDERLOG row only if it lands at a local optimum across scenes.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s ALL_X16
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    _run_baseline_variant, get_scenes, _baseline_noise_floor, run_baseline,
)
from PathTracer_Graph import render_graph_PathTracer

STEP = "ALL_X16"
res = int(os.environ.get("RES", "512"))
res_tag = f"{res}x{res}"

# Two carries from SPONZA_VT — same except varThreshold.
CANONICAL_X4 = {
    "bootThreshold":                  8,
    "matureThreshold":                32,
    "varThreshold":                   0.10,   # SPONZA_VT x4 optimum
    "pMin":                           0.02,
    "bayerN":                         2,
    "forceDescendFootprintPx":        16,
    "stderrThreshold":                0.0,
    "bootThresholdFactorFootprintPx": 0.0,
    "cascadeWindowForward":           12,
    "enableHierarchicalConsistency":  False,
    "hierarchicalMuTolerance":        0.20,
    "accelDecayDisagreeThresh":       0.0,
    "numLevels":                      8,
    "autoTuneCells":                  True,
    "enableVisCacheAdaptivePMin":     True,
    "enableVisCacheVarianceGate":     True,
    "enableVisCacheDecay":            True,
}

CANONICAL_X16 = {**CANONICAL_X4, "varThreshold": 0.001}  # SPONZA_VT x16 optimum

DEFAULT_SCENES = [
    "CornellBox_1AreaLight", "CornellBox_1PointLight",
    "CornellBox_3AreaLights", "CornellBox_32PointLights",
    "Sponza", "BistroExterior", "BistroInterior",
]


def _gt(scene_name):
    src_dir = f"captures/ladder/00/{scene_name}"
    gt_hdr = os.path.join(src_dir, f"s_x4096_{res_tag}_vanilla_hdr.exr")
    if not os.path.exists(gt_hdr):
        return None, None
    floor = _baseline_noise_floor(src_dir, 4096, res_tag, "vanilla")
    return gt_hdr, floor


for scene_file in get_scenes(default=list(DEFAULT_SCENES)):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    # Step-00 vanilla baseline for x{4, 16} should already exist on disk
    # for all 7 scenes. Re-run cached if needed.
    run_baseline(
        step_name="00", frame_configs=[(0, 0, 1)],
        scene_file=scene_file, resX=res, resY=res,
        gt_spp=4096, extra_spp=[4, 16],
        mogwai_globals=globals(),
    )

    gt_hdr, floor = _gt(scene_name)
    if gt_hdr is None:
        print(f"[ALL_X16] {scene_name} GT missing — skip")
        continue

    for spp, cfg, label in (
        (4,  CANONICAL_X4,  "vt010"),
        (16, CANONICAL_X16, "vt001"),
    ):
        def _build(spp=spp, cfg=cfg):
            return render_graph_PathTracer(
                viscache=True, samplesPerPixel=spp, useJitter=True,
                extraVCProps=cfg,
            )

        tag = f"viscache_canonical_{label}"
        _run_baseline_variant(
            STEP, [(0, 0, 1)], scene_file, tag,
            _build, "AccumulatePass.output",
            capture_spps=(spp,),
            resX=res, resY=res, mogwai_globals=globals(),
            gt_hdr_for_post=gt_hdr, noise_floor_for_post=floor,
        )

_HEADLESS_SCRIPT_DONE = True

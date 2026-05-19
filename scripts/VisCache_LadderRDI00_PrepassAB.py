"""
RDI00 prepass A/B verification — cross-variant and cross-scene.

Verifies the prepass-on-vs-off delta in isolation for BOTH active
canonical baselines (R2dP2d_F17P24 and R3dP3d_F00P24), with all
other optimizations frozen at current HEAD. Removes the pre-vs-post-opt
confounding that mixed multiple commits into one measurement.

Variants emitted (same K=41, same mCap=20, same Basic biasCorrection
within each pair — only wsCellPoolPrePass differs):

  R2dP2d_RTXDIBaseline_F17P24   prepass OFF (current canonical)
  R2dP2d_PrepassOn_F17P24       prepass ON  (ablation)
  R3dP3d_RTXDIBaseline_F00P24   prepass OFF (current canonical)
  R3dP3d_PrepassOn_F00P24       prepass ON  (ablation)

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_PrepassAB -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_PrepassAB \
        -c "Sponza,BistroInterior,CornellBox_32PointLights"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline,
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline,
    _run_baseline_restir, finalize_step,
)

STEP = "RDI00_PrepassAB"
res = int(os.environ.get("RES", "512"))


def run_R2dP2d_PrepassOn(step_name, frame_configs, scene_file, **kwargs):
    """R2dP2d F17P24 prepass-ON ablation."""
    extra = dict(kwargs.get("extraVCProps", {}) or {})
    extra["cellReservoirFootprintPx"] = 0
    kwargs2 = dict(kwargs)
    kwargs2["extraVCProps"] = extra
    kwargs2.setdefault("mCap", 20.0)
    kwargs2.setdefault("emissiveSampler", "PdfMipmap")
    kwargs2.setdefault("biasCorrection", 0)
    return _run_baseline_restir(
        step_name, frame_configs, scene_file,
        tag_prefix="ReSTIRDI_R2dP2d_PrepassOn",
        addr_mode_kwargs={"poolAddrMode": 1, "poolTileSize": 16},
        initialCandidates=17,
        cellPoolDrawK=24,
        wsCellPoolPrePass=True,  # <- key ablation
        prePassEmissiveSampler="PdfMipmap",
        **kwargs2,
    )


def run_R3dP3d_PrepassOn(step_name, frame_configs, scene_file,
                         cellPoolFootprintPx=16,
                         cellReservoirFootprintPx=1, **kwargs):
    """R3dP3d F00P24 prepass-ON ablation."""
    extra = dict(kwargs.get("extraVCProps", {}) or {})
    extra["enablePixelReservoir"] = False
    extra["cellReservoirMerge"] = 1
    extra["cellReservoirFootprintPx"] = cellReservoirFootprintPx
    kwargs2 = dict(kwargs)
    kwargs2["extraVCProps"] = extra
    kwargs2.setdefault("mCap", 20.0)
    kwargs2.setdefault("emissiveSampler", "PdfMipmap")
    kwargs2.setdefault("biasCorrection", 0)
    return _run_baseline_restir(
        step_name, frame_configs, scene_file,
        tag_prefix="ReSTIRDI_R3dP3d_PrepassOn",
        addr_mode_kwargs={"poolAddrMode": 0, "cellPoolFootprintPx": cellPoolFootprintPx},
        initialCandidates=0,
        cellPoolDrawK=24,
        wsCellPoolPrePass=True,  # <- key ablation
        prePassEmissiveSampler="PdfMipmap",
        **kwargs2,
    )


for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16, 64),
        mogwai_globals=globals(),
    )

    # R2dP2d pair
    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)
    run_R2dP2d_PrepassOn(STEP, [(0, 0, 1)], scene_file, **common)

    # R3dP3d pair
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)
    run_R3dP3d_PrepassOn(STEP, [(0, 0, 1)], scene_file, **common)

finalize_step(STEP, carried_winners=[])
_HEADLESS_SCRIPT_DONE = True

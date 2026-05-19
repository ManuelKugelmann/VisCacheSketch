"""
RDI00 prepass A/B verification — Sponza-focused.

Verifies the Sponza F17P24 prepass-on-vs-off delta in isolation, with
ALL other optimizations (gNormalAddr removed, USE_VISCACHE_NORMAL_ADDR
gate) frozen at current HEAD. Removes the pre-vs-post-opt confounding
that mixed three commits into one measurement.

Variants emitted (same scene, same K=41, same mCap=20, same Basic
biasCorrection — only wsCellPoolPrePass differs):

  ReSTIRDI_R2dP2d_RTXDIBaseline_F17P24       — prepass OFF (current canonical)
  ReSTIRDI_R2dP2d_PrepassOn_F17P24            — prepass ON (ablation)

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_PrepassAB -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_PrepassAB -c "Sponza,BistroInterior"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes, run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline,
    _run_baseline_restir, finalize_step,
)

STEP = "RDI00_PrepassAB"
res = int(os.environ.get("RES", "512"))


def run_PrepassOn(step_name, frame_configs, scene_file, **kwargs):
    """F17P24 prepass-ON ablation: same as RTXDIBaseline_F17P24 but
    wsCellPoolPrePass=True. Pure prepass A/B at current HEAD."""
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


for scene_file in get_scenes(default=["Sponza"]):
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    captureDir = f"captures/ladder/{STEP}/{scene_name}"
    os.makedirs(captureDir, exist_ok=True)

    common = dict(
        resX=res, resY=res,
        capture_spps=(1, 4, 16, 64),
        mogwai_globals=globals(),
    )

    run_baseline_ReSTIRDI_R2dP2d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)
    run_PrepassOn(STEP, [(0, 0, 1)], scene_file, **common)

finalize_step(STEP, carried_winners=[])
_HEADLESS_SCRIPT_DONE = True

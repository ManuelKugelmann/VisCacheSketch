"""
RDI00 K-slot probe — characterize K>1 reservoir architecture.

First ladder step exercising the K-slot evolution wired in commits
dc5072e..57d1354. Variants:

  ReSTIRDI_R3dP3d_K1_F00P24   reservoirK=1 (baseline twin of canonical
                              R3dP3d_RTXDIBaseline_F00P24)
  ReSTIRDI_R3dP3d_K4_F00P24   reservoirK=4 (4 slots per world cell,
                              atomic-counter insert, in-cell merge read)
  ReSTIRDI_R3dP3d_K8_F00P24   reservoirK=8

K=1 must rmse-match the canonical R3dP3d baseline within RNG noise
floor (~0.2%). K=4 and K=8 are genuine algorithmic changes — quality
delta vs K=1 is the metric of interest. Expected: K-slot aggregates
multiple writers per cell into a single returned merged reservoir,
giving variance reduction proportional to K (in the limit of
independent writers contributing samples to the cell).

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_KSlot -c Sponza
    runtime/pythondist/python.exe scripts/run_ladder.py -s RDI00_KSlot \\
        -c "Sponza,BistroInterior,CornellBox_32PointLights"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from VisCache_LadderCommon import (
    get_scenes,
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline,
    _run_baseline_restir, finalize_step,
)

STEP = "RDI00_KSlot"
res = int(os.environ.get("RES", "512"))


def _R3dP3d_KN(N: int, step_name, frame_configs, scene_file,
               cellPoolFootprintPx=16, cellReservoirFootprintPx=1, **kwargs):
    """R3dP3d F00P24 with reservoirK=N.

    IMPORTANT: at K>1 this currently produces IDENTICAL output to K=1 in the
    canonical config. Reason: R3dP3d_F00P24 uses spatialNeighbours=0 (cell-RIS
    spatial merge disabled — that path has a known bias issue with
    biasCorrection=0). With cell-RIS disabled, the cell-reservoir machinery
    is WRITE-ONLY: mergeIntoCell writes the per-frame K-RIS winner to its
    cell, but nothing READS the cell reservoirs back for shading or temporal
    reuse.

    The K-slot architecture (atomic-counter insert + in-cell merge read) is
    therefore structurally present but algorithmically dormant in this variant.
    Sanity check: K=1/4/8 should all give matching rmse — confirming K=1
    parity is preserved (no regression) AND K>1 plumbing doesn't crash.

    To genuinely exercise K-slot, future work needs either:
    (a) Fix the cell-RIS spatial merge bias at biasCorrection=0, then enable
        spatialNeighbours>0 to invoke loadCellMerged() in the cell-RIS loop.
    (b) Add a new "temporal-cell-reuse" path that reads the cell reservoir
        from the previous frame, analogous to per-pixel temporal reuse but
        keyed by world-cell instead of pixel.xy.

    Both are beyond K-slot scope (algorithm changes); the K-slot pieces are
    ready to be consumed when either path lands.
    """
    extra = dict(kwargs.get("extraVCProps", {}) or {})
    extra["enablePixelReservoir"] = False
    extra["cellReservoirMerge"] = 1
    extra["cellReservoirFootprintPx"] = cellReservoirFootprintPx
    extra["reservoirK"] = N
    kwargs2 = dict(kwargs)
    kwargs2["extraVCProps"] = extra
    kwargs2.setdefault("mCap", 20.0)
    kwargs2.setdefault("emissiveSampler", "PdfMipmap")
    kwargs2.setdefault("biasCorrection", 0)
    return _run_baseline_restir(
        step_name, frame_configs, scene_file,
        tag_prefix=f"ReSTIRDI_R3dP3d_K{N}fp{cellReservoirFootprintPx}",
        addr_mode_kwargs={"poolAddrMode": 0, "cellPoolFootprintPx": cellPoolFootprintPx},
        initialCandidates=0,
        cellPoolDrawK=24,
        wsCellPoolPrePass=False,
        prePassEmissiveSampler="PdfMipmap",
        **kwargs2,
    )


def _R3dP3d_F8P0_KN(N: int, step_name, frame_configs, scene_file,
                    cellPoolFootprintPx=16, cellReservoirFootprintPx=8,
                    cellLevelOffsetWrite=0, **kwargs):
    """R3dP3d F8P0 with reservoirK=N. Pure fresh K-RIS (no pool draws);
    cell-RIS is THE primary aggregation mechanism. Documented ideal K-slot
    architecture per .plans/unified-reservoir-addressing.md final-status section.
    """
    extra = dict(kwargs.get("extraVCProps", {}) or {})
    extra["enablePixelReservoir"] = False
    extra["cellReservoirMerge"] = 1
    extra["cellReservoirFootprintPx"] = cellReservoirFootprintPx
    extra["reservoirK"] = N
    extra["cellLevelOffsetWrite"] = cellLevelOffsetWrite
    kwargs2 = dict(kwargs)
    kwargs2["extraVCProps"] = extra
    kwargs2.setdefault("mCap", 20.0)
    kwargs2.setdefault("emissiveSampler", "PdfMipmap")
    kwargs2.setdefault("biasCorrection", 0)
    lo_tag = f"lo{cellLevelOffsetWrite}" if cellLevelOffsetWrite > 0 else ""
    return _run_baseline_restir(
        step_name, frame_configs, scene_file,
        tag_prefix=f"ReSTIRDI_R3dP3d_F8P0_K{N}fp{cellReservoirFootprintPx}{lo_tag}",
        addr_mode_kwargs={"poolAddrMode": 0, "cellPoolFootprintPx": cellPoolFootprintPx},
        initialCandidates=8,    # 8 fresh K-RIS candidates per pixel per frame
        cellPoolDrawK=0,        # NO pool draws — cell-RIS is the primary aggregation
        wsCellPoolPrePass=False,
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

    # Canonical R3dP3d baseline (frozen yardstick at K=1 implicitly).
    run_baseline_ReSTIRDI_R3dP3d_RTXDIBaseline(STEP, [(0, 0, 1)], scene_file, **common)

    # K-slot at canonical fp=1 (1 writer per cell — K=temporal-history only).
    _R3dP3d_KN(1, STEP, [(0, 0, 1)], scene_file, **common)  # K=1, parity check
    _R3dP3d_KN(4, STEP, [(0, 0, 1)], scene_file, **common)  # K=4, first multi-slot
    _R3dP3d_KN(8, STEP, [(0, 0, 1)], scene_file, **common)  # K=8, cache-line ceiling

    # K-slot at fp=8 (multi-writer cells — K=genuine spatial aggregation).
    _R3dP3d_KN(4, STEP, [(0, 0, 1)], scene_file, cellReservoirFootprintPx=8, **common)
    _R3dP3d_KN(8, STEP, [(0, 0, 1)], scene_file, cellReservoirFootprintPx=8, **common)

    # F8 + P0 + K=variant: pure-fresh + K-slot cell-RIS (no pool). The
    # documented ideal architecture where cell-RIS IS the primary aggregation.
    _R3dP3d_F8P0_KN(1, STEP, [(0, 0, 1)], scene_file, **common)
    _R3dP3d_F8P0_KN(4, STEP, [(0, 0, 1)], scene_file, **common)
    _R3dP3d_F8P0_KN(8, STEP, [(0, 0, 1)], scene_file, **common)

    # Step C — multi-level cascade write+read. K=4/8 × lo=1/2: each cell
    # access mirrors home + N coarser cells. Coarser cells aggregate K
    # writers from neighbouring primary pixels — extra effective candidates
    # without extra K-RIS cost. NEE-ready (same primitive composes with
    # path-cumulative footprint in ReSTIRNEEPass).
    for lvlOff in (1, 2):
        for K in (4, 8):
            _R3dP3d_F8P0_KN(K, STEP, [(0, 0, 1)], scene_file,
                            cellLevelOffsetWrite=lvlOff, **common)

finalize_step(STEP, carried_winners=[])
_HEADLESS_SCRIPT_DONE = True

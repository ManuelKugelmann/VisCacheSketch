"""
ReSTIRDIPass_Graph.py — Standalone ReSTIR DI baseline.

Mirrors the NEE pattern: a clean factory function for the ReSTIRDIPass
plus its supporting VisCachePass (vblind — no visibility cache, no light
selection cache). Use this as the cache-less baseline for VisCache
integration testing.

  VBuffer → VisCache (vblind) ⇄ PathTracerX(useReSTIRDIPass=True)
                              → AccumulatePass → ToneMapper

The default config mirrors the RDI00 R2dP2d_RTXDIBaseline floor from
`VisCache_LadderRDI00.py`: per-pixel R2d reservoir + cell-pool P2d,
K=24 K-RIS candidates, mCap=20, spatial reuse 4 neighbours / 32 px
radius. RTXDI-parity at the parameter level; no VisCache visibility
prediction yet.

Usage (standalone):
    Mogwai.exe --script scripts/ReSTIRDIPass_Graph.py

Usage (factory):
    from ReSTIRDIPass_Graph import render_graph_ReSTIRDIPass
    g = render_graph_ReSTIRDIPass(samplesPerPixel=4)

To layer VisCache visibility on top, use ReSTIRDIPass_VisCache_Graph.py.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PathTracer_Graph import render_graph_PathTracer

try:
    from falcor import *
except ImportError:
    pass


def render_graph_ReSTIRDIPass(samplesPerPixel=1, maxBounces=0, useJitter=True,
                              initialCandidates=24, mCap=20.0,
                              spatialNeighbours=4, spatialPixelsK=4,
                              spatialPixelsRadius=32,
                              cellReservoirFootprintPx=0,
                              cellPoolFootprintPx=16,
                              cellPoolDrawK=24,
                              biasCorrection=0,
                              emissiveSampler="PdfMipmap",
                              visibilityCheck=False, lightSelection=False,
                              extraVCProps=None):
    """Build the canonical ReSTIRDIPass baseline graph.

    Defaults mirror the RDI00 R2dP2d_RTXDIBaseline: K=24 from PdfMipmap
    presample, mCap=20, spatial 4×32px, no VisCache visibility prediction.

    Args mirror render_graph_PathTracer's DI-relevant subset. For VisCache
    visibility/light-selection layering, set visibilityCheck=True and/or
    lightSelection=True — or use ReSTIRDIPass_VisCache_Graph.py.
    """
    return render_graph_PathTracer(
        viscache=True,                # VisCachePass required (provides reservoirs/pool buffer)
        reservoirs=True,              # turn on §9.4 WS-ReSTIR DI
        useReSTIRDIPass=True,         # route through the standalone DI pass
        maxBounces=maxBounces,        # DI = direct only; 0 = no indirect bounces
        samplesPerPixel=samplesPerPixel,
        useJitter=useJitter,
        initialCandidates=initialCandidates,
        mCap=mCap,
        spatialNeighbours=spatialNeighbours,
        spatialPixelsK=spatialPixelsK,
        spatialPixelsRadius=spatialPixelsRadius,
        cellReservoirFootprintPx=cellReservoirFootprintPx,
        cellPoolFootprintPx=cellPoolFootprintPx,
        cellPoolDrawK=cellPoolDrawK,
        biasCorrection=biasCorrection,
        emissiveSampler=emissiveSampler,
        prePassEmissiveSampler="Power",   # RTXDI presample-tile parity
        visibilityCheck=visibilityCheck,
        lightSelection=lightSelection,
        extraVCProps=extraVCProps,
    )


if 'm' in globals():
    m.addGraph(render_graph_ReSTIRDIPass())

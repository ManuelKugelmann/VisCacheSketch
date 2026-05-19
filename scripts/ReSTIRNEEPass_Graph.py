"""
ReSTIRNEEPass_Graph.py — every-vertex K-RIS NEE on a clean PathTracerX base.

VBuffer → ReSTIRNEEPass → AccumulatePass → ToneMapper.

The K knob (numNEECandidates) defaults to 16. Set K=1 to fall through to
byte-for-byte vanilla NEE (useful as a sanity baseline).

Usage:
    Mogwai.exe --script scripts/ReSTIRNEEPass_Graph.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

try:
    from falcor import *
except ImportError:
    pass


def render_graph_ReSTIRNEEPass(maxBounces=3, samplesPerPixel=1, useJitter=True,
                               numNEECandidates=16, emissiveSampler=None,
                               useNEECells=False,
                               cellReservoirFootprintPx=1):
    g = RenderGraph("ReSTIRNEEPass")

    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # When 3D cell-reservoir reuse is enabled, NEE pulls the gReservoirs
    # buffer + VisCacheParams cbuffer from VisCachePass via InternalDictionary
    # (same wiring DI uses). cellReservoirFootprintPx=1 → sub-pixel cell
    # at primary hit; path.cellFootprintPx in the shader widens with
    # BSDF roughness at each subsequent bounce (Sharc-style).
    if useNEECells:
        vc_props = {**VISCACHE_DEFAULTS,
                    "spp": samplesPerPixel,
                    "enableReservoirs": True,
                    "reservoirCapacity": 1 << 20,
                    "cellReservoirFootprintPx": cellReservoirFootprintPx,
                    "mCap": 20.0,
                    # NEE drives cell reads/writes inline; no per-pixel
                    # reservoir layer needed.
                    "enablePixelReservoir": False,
                    # No cell pool (NEE uses K-RIS streaming inside the
                    # shader; cells are the reuse layer).
                    "enableCellPool": False,
                    # Cell-NEE doesn't engage VisCache visibility yet.
                    "enableVisCacheVisibilityCheck": False,
                    "enableVisCacheLightSelection": False}
        vc = createPass("VisCachePass", vc_props)
        g.addPass(vc, "VisCache")

    pt_props = {
        "samplesPerPixel":   samplesPerPixel,
        "maxSurfaceBounces": maxBounces,
        "colorFormat":       "LogLuvHDR",
        "numNEECandidates":  numNEECandidates,
        "useNEECells":       useNEECells,
    }
    if emissiveSampler is not None:
        pt_props["emissiveSampler"] = emissiveSampler
    pt = createPass("ReSTIRNEEPass", pt_props)
    g.addPass(pt, "ReSTIRNEE")

    accum = createPass("AccumulatePass", {"enabled": True, "precisionMode": "Single"})
    g.addPass(accum, "AccumulatePass")

    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    g.addEdge("VBufferRT.vbuffer",   "ReSTIRNEE.vbuffer")
    g.addEdge("VBufferRT.viewW",     "ReSTIRNEE.viewW")
    g.addEdge("ReSTIRNEE.color",     "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")

    # VisCachePass has no edges into the NEE path (cell-reservoir buffer flows
    # via InternalDictionary, not as a render-graph edge). Mark one of its
    # diagnostic outputs so Falcor's graph compiler doesn't prune the pass as
    # dead — that prune would also skip its dict-publish, leaving NEE with
    # mVisCacheAvailable=false and USE_NEE_CELLS silently gated off.
    if useNEECells:
        g.markOutput("VisCache.vcAccumMeanVarMatCount")
    return g


if 'm' in globals():
    m.addGraph(render_graph_ReSTIRNEEPass())

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
                               cellReservoirFootprintPx=1,
                               reservoirK=1,
                               cellLevelOffsetWrite=0,
                               normalACoarse=None,
                               visibilityCheck=False,
                               lightSelection=False,
                               extraVCProps=None):
    g = RenderGraph("ReSTIRNEEPass")

    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Add VisCachePass when ANY VC toggle is on (cells, visibilityCheck,
    # lightSelection). Earlier this was gated on `useNEECells` only — that
    # bug meant pure K-RIS NEE never even had the cache pass in the graph,
    # so `visibilityCheck=True` was a no-op (the shader define
    # USE_VISCACHE_VISIBILITYCHECK ended up 0 because mVisCacheAvailable
    # was false). Visibility-cache amortization should work for ANY NEE
    # shadow ray, independent of whether cell reservoirs are engaged.
    need_vc_pass = useNEECells or visibilityCheck or lightSelection
    if need_vc_pass:
        vc_props = {**VISCACHE_DEFAULTS,
                    "spp": samplesPerPixel,
                    # Cell-reservoir reuse: only enable buffer + dict publish
                    # when useNEECells is on. Visibility-cache + light-
                    # selection-cache are independent toggles.
                    "enableReservoirs":     bool(useNEECells),
                    "reservoirCapacity":    1 << 20,
                    "cellReservoirFootprintPx": cellReservoirFootprintPx if useNEECells else 0,
                    "reservoirK":           reservoirK,
                    "cellLevelOffsetWrite": cellLevelOffsetWrite,
                    "mCap":                 20.0,
                    "enablePixelReservoir": False,
                    "enableVisCacheVisibilityCheck": bool(visibilityCheck),
                    "enableVisCacheLightSelection":  bool(lightSelection)}
        if normalACoarse is not None:
            vc_props["normalACoarse"] = float(normalACoarse)
        # extraVCProps: caller-supplied overrides (e.g. CANONICAL_VC_SETTINGS
        # from VisCache_LadderCommon — bayer4x4, stderr=0.10, qa012 quant).
        # Applied last so they win over the defaults above.
        if extraVCProps:
            vc_props.update(extraVCProps)
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
    # mVisCacheAvailable=false and the visibility-cache + cell-reservoir
    # paths silently gated off.
    if need_vc_pass:
        g.markOutput("VisCache.vcAccumMeanVarMatCount")
        g.markOutput("VisCache.vcAccumRaysSplitNeeReval", TextureChannelFlags.RGBA)
        g.markOutput("VisCache.vcAccumRaysNoiseErrorCold", TextureChannelFlags.RGBA)
    return g


if 'm' in globals():
    m.addGraph(render_graph_ReSTIRNEEPass())

"""
PathTracer_Graph.py  —  Vanilla Falcor PathTracer render graph.

Full-featured path tracer with accumulation and tone mapping.
VBuffer → PathTracer → AccumulatePass → ToneMapper.
Optionally adds VisCache for shadow gating (§11.2) when viscache=True.

Usage:
    Mogwai.exe --script scripts/PathTracer_Graph.py --scene VeachAjar.pyscene
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_defaults import VISCACHE_DEFAULTS

try:
    from falcor import *
except ImportError:
    pass


def render_graph_PathTracer(viscache=False, maxBounces=3, samplesPerPixel=1, useJitter=True,
                            wsReservoirs=False, wsCellLevelJitter=0,
                            wsReservoirCapacity=1 << 20,  # 1M cells = 4× WORST-CASE R3dP3d footprint=1 (~262K active at 512²). 32 MB.
                            wsMCap=30.0, wsSpatialNeighbours=4, wsLightMuMin=0.01,
                            wsInitialCandidates=8,
                            wsVisInPHat=1,
                            wsRetraceOnReuseMode=0,    # 0=Off (default; matches RTXDI Basic / our shipping behaviour), 1=FullTrace (≡ RTXDI RayTraced), 2=CacheCV (cheap CV+RRR via cache, same PT-canonical knobs).
                            wsCellPool=False, wsCellPoolCapacity=1 << 12, wsCellPoolDrawK=0,  # 4K cells; at N=1024 × 16 B/slot = 64 MB. The previous 1<<18=256K default OOM'd at N=1024 (4 GB slot buffer).
                            wsCellPoolPrePass=False,
                            wsSpatialPixelsK=4, wsSpatialPixelsRadius=32,
                            wsPoolAddrMode=0, wsPoolTileSize=16,
                            wsCellPoolFootprintPx=0,
                            wsCellReservoirFootprintPx=0,
                            emissiveSampler=None,    # main pass: None = Falcor default (LightBVH)
                            prePassEmissiveSampler=None,    # pre-pass override (defaults to emissiveSampler if None); "Power" = shading-agnostic pool fill (RTXDI-pdf-mipmap-equivalent for cell pool only)
                            prePassWsVisInPHat=None,        # pre-pass override for wsVisInPHat (defaults to wsVisInPHat). Set to 1 → pre-pass uses VisCache cache lookups for V-aware pool fill (§9.4 step (d) + §9.2 V amortization). Combined with Bayer N×N gate, this is the warmup-with-amortization design from §11.2.
                            prePassBayerN=None,             # pre-pass-only bayerN override (Bayer N×N gate). Default: same as VisCache default (1 = full screen each frame). Set to 4 → 16-frame Bayer sweep with 1/16 of pixels firing explicit shadow rays each frame, the rest using cache lookups.
                            visibilityCheck=None, lightSelection=None,
                            extraVCProps=None,
                            useReSTIRDIPass=False):  # If True + wsReservoirs=True, route DI through standalone ReSTIRDIPass instead of PathTracer-integrated WS-ReSTIR (refactor in progress).
    """Build a PathTracer render graph.

    Args:
        viscache: If True, add VisCache pass for shadow gating (§11.2).
        useJitter: If False, pin samples to pixel center (no subpixel jitter).
        wsReservoirs: If True, enable §9.4 world-space ReSTIR DI reservoirs
            (requires viscache=True since reservoirs ride VisCache's posA cascade).
        wsCellLevelJitter: Per-pixel stochastic LOD jitter range (0 = off).
            When >0, the per-pixel level is offset above the analytical entry
            level (computed from wsCellReservoirFootprintPx) by a truncated-
            exponential offset in [0, jitter].
        visibilityCheck: If not None, override enableVisCacheVisibilityCheck (§9.2).
        lightSelection: If not None, override enableVisCacheLightSelection (§9.1).
        extraVCProps: Optional dict merged into VisCache properties at create time
            — for arbitrary one-off overrides. Falcor 8 doesn't expose Pass.setProperty
            from Python, so all per-toggle tweaks must go through create-time props.
    """
    name = "PathTracer_VisCache" if viscache else "PathTracer"
    if wsReservoirs:
        name += "_WSReSTIR"
    g = RenderGraph(name)
    if wsReservoirs and not viscache:
        # WS reservoirs are exported by the VisCache pass; can't run without it.
        viscache = True

    # V-Buffer (visibility buffer — primary ray hits)
    vbuf = createPass("VBufferRT", {
        "samplePattern": "Stratified" if useJitter else "Center",
        "sampleCount":   16,
    })
    g.addPass(vbuf, "VBufferRT")

    # Visibility Cache (optional) — no graph edges, exposes data via InternalDictionary
    if viscache:
        vc_props = {**VISCACHE_DEFAULTS, "spp": samplesPerPixel}
        if visibilityCheck is not None:
            vc_props["enableVisCacheVisibilityCheck"] = bool(visibilityCheck)
        if lightSelection is not None:
            vc_props["enableVisCacheLightSelection"] = bool(lightSelection)
        if extraVCProps:
            vc_props.update(extraVCProps)
        if wsReservoirs:
            vc_props.update({
                "enableWSReservoirs":   True,
                "wsInitialCandidates":  wsInitialCandidates,
                "wsVisInPHat":          wsVisInPHat,
                "wsRetraceOnReuseMode": wsRetraceOnReuseMode,
                "wsCellLevelJitter":    wsCellLevelJitter,
                "wsReservoirCapacity":  wsReservoirCapacity,
                "wsMCap":               wsMCap,
                "wsSpatialNeighbours":  wsSpatialNeighbours,
                "wsLightMuMin":         wsLightMuMin,
                "wsSpatialPixelsK":     wsSpatialPixelsK,
                "wsSpatialPixelsRadius": wsSpatialPixelsRadius,
                "wsCellReservoirFootprintPx": wsCellReservoirFootprintPx,
            })
        if wsReservoirs and wsCellPool:
            vc_props.update({
                "enableWSCellPool":     True,
                "wsCellPoolCapacity":   wsCellPoolCapacity,
                "wsCellPoolDrawK":      wsCellPoolDrawK,
                "wsPoolAddrMode":       wsPoolAddrMode,
                "wsPoolTileSize":       wsPoolTileSize,
                "wsCellPoolFootprintPx": wsCellPoolFootprintPx,
            })
        vc = createPass("VisCachePass", vc_props)
        g.addPass(vc, "VisCache")

    # §9.4 Step (b) WS-cascade ReGIR: optional cell-pool pre-pass instance.
    # Runs BEFORE the main PathTracer to populate the cell pool from K-RIS
    # candidates. Skips shading entirely (Lr=0). The main instance then
    # reads from the populated pool. Both instances share the same VisCache
    # cell-pool buffer via InternalDictionary.
    if viscache and wsReservoirs and wsCellPool and wsCellPoolPrePass:
        pt_pre_props = {
            "samplesPerPixel":     samplesPerPixel,
            "maxSurfaceBounces":   maxBounces,
            "colorFormat":         "LogLuvHDR",
            "wsCellPoolFillOnly":  True,
        }
        # Pre-pass-specific sampler override falls back to main emissiveSampler.
        prePassSampler = prePassEmissiveSampler if prePassEmissiveSampler is not None else emissiveSampler
        if prePassSampler is not None:
            pt_pre_props["emissiveSampler"] = prePassSampler
        pt_pre = createPass("PathTracer", pt_pre_props)
        # Pre-pass-specific VisCache overrides for the warmup-with-amortization
        # design (§11.2): higher bayerN concentrates explicit shadow-ray
        # firing into a Bayer pattern, the rest of the pixels use cache
        # lookups for V-aware pool fill (§9.4 step d + §9.2 V amortization).
        # Falcor 8 doesn't expose Pass.setProperty from Python, so any per-
        # PathTracerPrePass overrides go through createPass props above —
        # but VisCache state (bayerN, wsVisInPHat) is shared via the
        # InternalDictionary, so a true per-pass override would require a
        # second VisCache instance or per-pass cbuffer fields. For now this
        # parameter is here as a marker; wiring requires per-pass
        # VisCacheParams override (Task #32).
        g.addPass(pt_pre, "PathTracerPrePass")
        g.addEdge("VBufferRT.vbuffer", "PathTracerPrePass.vbuffer")
        g.addEdge("VBufferRT.viewW",   "PathTracerPrePass.viewW")

    # Falcor PathTracer (full-featured: NEE, MIS, Russian roulette, volumes).
    # Skipped when ReSTIRDIPass is the radiance producer — avoids double-write
    # to the WS reservoir buffer (both passes would target gWSPixelReservoirs).
    if not (viscache and wsReservoirs and useReSTIRDIPass):
        pt_props = {
            "samplesPerPixel":    samplesPerPixel,
            "maxSurfaceBounces":  maxBounces,
            "colorFormat":        "LogLuvHDR",
        }
        if emissiveSampler is not None:
            pt_props["emissiveSampler"] = emissiveSampler   # "Uniform" | "LightBVH" | "Power" | "Null"
        pt = createPass("PathTracer", pt_props)
        g.addPass(pt, "PathTracer")
    # NOTE: PathTracerPrePass → PathTracerMain ordering relies on Falcor's
    # UAV barrier system (both passes touch gWSCellPools). Within a frame,
    # pool writes from pre-pass complete before main reads (UAV barrier).
    # No explicit graph edge needed — and adding one (e.g. color → ...)
    # would break the input-format contract.

    # Accumulate samples over frames for progressive rendering. PathTracer internally
    # loops N² Bayer subframes per execute() call, so AccumulatePass sees one fully
    # composed dense frame per renderFrame — no subframe awareness needed here.
    accum_props = {
        "enabled":       True,
        "precisionMode": "Single",
    }
    accum = createPass("AccumulatePass", accum_props)
    g.addPass(accum, "AccumulatePass")

    # Tone mapper
    tone = createPass("ToneMapper", {
        "autoExposure":  False,
        "exposureValue": 0.0,
        "operator":      "Aces",
    })
    g.addPass(tone, "ToneMapper")

    # Optional standalone ReSTIRDIPass (refactor in progress; gated off by
    # default). When enabled, REPLACES PathTracer as the radiance producer
    # for primary-hit DI (mirrors RTXDIPass integration). PathTracer is also
    # removed from the graph so it can't double-write the reservoir buffer
    # alongside our standalone pass.
    use_restirdi = viscache and wsReservoirs and useReSTIRDIPass
    if use_restirdi:
        # ReSTIRDIPass is forked from Falcor's PathTracer plugin — accepts
        # the same props (samplesPerPixel, maxBounces, colorFormat,
        # emissiveSampler) as PathTracer.
        rdi_props = {
            "samplesPerPixel":    samplesPerPixel,
            "maxSurfaceBounces":  maxBounces,
            "colorFormat":        "LogLuvHDR",
        }
        if emissiveSampler is not None:
            rdi_props["emissiveSampler"] = emissiveSampler
        restirdi = createPass("ReSTIRDIPass", rdi_props)
        g.addPass(restirdi, "ReSTIRDIPass")
        g.addEdge("VBufferRT.vbuffer", "ReSTIRDIPass.vbuffer")
        g.addEdge("VBufferRT.viewW",   "ReSTIRDIPass.viewW")

    # Edges
    if not use_restirdi:
        g.addEdge("VBufferRT.vbuffer", "PathTracer.vbuffer")
        g.addEdge("VBufferRT.viewW",   "PathTracer.viewW")
        g.addEdge("PathTracer.color",  "AccumulatePass.input")
    else:
        g.addEdge("ReSTIRDIPass.color", "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    # Force PathTracerPrePass to execute. Without a marked output or a
    # downstream consumer, Falcor's render graph optimizer prunes the
    # pass entirely (it has no observable effect on graph outputs from
    # the optimizer's POV — the cell-pool UAV side effect is invisible
    # to the dependency tracker). Marking its color keeps it scheduled.
    if viscache and wsReservoirs and wsCellPool and wsCellPoolPrePass:
        g.markOutput("PathTracerPrePass.color")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")  # pre-tonemapper HDR (captured as EXR)

    # -------------------------------------------------------------------
    # VisCache diagnostic heatmaps (only when viscache=True)
    # -------------------------------------------------------------------
    # Diagnostic heatmaps are written INLINE by PathTracer (PixelStats pattern)
    # into textures owned by the VisCache pass. The ColorMapPass must execute
    # AFTER PathTracer finishes, but there's no data edge from PathTracer to
    # the diagnostic textures (they flow via InternalDictionary). We enforce
    # ordering by routing the diagnostic textures through AccumulatePass first
    # (which already depends on PathTracer.color).
    # -------------------------------------------------------------------
    if viscache:
        # Mark diagnostic outputs (captured at end of frame, after all passes)
        g.markOutput("VisCache.vcAccumMeanVarMatCount", TextureChannelFlags.RGBA)   # R=variance*4, G=maturity, B=mean, A=count
        g.markOutput("VisCache.vcFrameMeanVarMatSamplesRaw", TextureChannelFlags.RGBA)  # R=variance*4, G=maturity, B=mean, A=samplesRaw
        g.markOutput("VisCache.vcFrameLevelProbesSamplesCold", TextureChannelFlags.RGBA)  # R=level, G=probeSteps, B=samples, A=coldmiss
        g.markOutput("VisCache.vcFrameHashAHashBHashABRays", TextureChannelFlags.RGBA)  # R=qAHash, G=qBHash, B=combinedHash, A=raysTraced
        g.markOutput("VisCache.vcAccumRaysNoiseErrorCold", TextureChannelFlags.RGBA)  # R=raysTraced, G=renderNoise, B=renderError, A=coldmiss
        g.markOutput("VisCache.vcAccumRaysSplitNeeReval", TextureChannelFlags.RGBA)  # R=NEE_ratio, G=Reval_ratio, B+A reserved

    return g


# ---------------------------------------------------------------------------
# Load graph (only when run directly by Mogwai, not when imported as module)
# ---------------------------------------------------------------------------
if 'm' in globals():
    m.addGraph(render_graph_PathTracer())

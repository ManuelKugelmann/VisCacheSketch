import Utils.Color.ColorMap;
import Utils.Sampling.SampleGenerator;
import Utils.Debug.PixelDebug;
import PathShift;

static const bool gUseCausticReservoirs   = USE_CAUSTIC_RESERVOIRS;
static const uint gDebugCausticReservoirs = DEBUG_CAUSTIC_RESERVOIRS;

[shader("compute")]
[numthreads(8, 4, 1)]
void SampleLightPaths(uint3 index: SV_DispatchThreadID) {
    if (index.y * gPathGenerator.mParams.mOutputDim.x + index.x >= gPathGenerator.mParams.mLightSubpathCount) return;
    gPathGenerator.DebugSetPixel(-1);

    gPathGenerator.SampleLightPath(PathId(gRandomSeed, index.xy));
}

[shader("compute")]
[numthreads(8, 4, 1)]
void SampleCameraPaths(uint3 index : SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    const PathReservoir r = gPathGenerator.SampleCanonicalPaths(PathId(gRandomSeed, id));

    gPathGenerator.StoreReservoir(id, r);
}

[shader("compute")]
[numthreads(8, 8, 1)]
void ResolveLightTraceReservoirs(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);
    SampleGenerator sg = MakeSampleGenerator(id, gRandomSeed);

    const PackedPathVertex primaryVertex = gPathGenerator.LoadPrimaryVertex(id);

    const float m = 1 / float(gPathGenerator.mParams.mLightSubpathCount);

    // merge light trace reservoirs in pixel

    uint minid = ~0u;

    PathReservoir r = {};
    PathReservoir cr = {};

    const uint2 range = gPathGenerator.mLightTraceReservoirs.GetCellDataRange(id.y * gPathGenerator.mParams.mOutputDim.x + id.x);
    for (uint i = range.x; i < range.y; i++) {
        const LightTraceReservoir lr = gPathGenerator.mLightTraceReservoirs[i];
        PathReservoir c = PathReservoir(lr.path, lr.W, 0);
        c.PrepareMerge(m);

        // [Falcor 8 port] gShiftLightPathsToPixelCenters branch disabled. The
        // ShiftPath call trips Falcor 8 ParameterBlock reflection during
        // setVars for ResolveLightTraceReservoirs. Bisect points to deep
        // PathState<true> nested-type reflection — not fixable in our slang
        // code without rewriting major data structures. The rest of the
        // ReSTIR resampling pipeline (light/camera reservoir merge, caustic
        // split) runs fine; only the optional sub-pixel re-projection
        // optimization is missing. See docs/SLANG_AND_FALCOR_NOTES.md.
        // if (gPathGenerator.gShiftLightPathsToPixelCenters && c.mSample.HasFlag(PathFlags::eNonCausticLightPath)) {
        //     gPathGenerator.DebugSetPixel(-1);
        //     float jacobian; int2 tmp;
        //     const bool valid = ShiftPath(c.mSample, primaryVertex, tmp, jacobian).IsValid();
        //     gPathGenerator.DebugSetPixel(id);
        //     if (!valid || !(jacobian > 0)) continue;
        // }

        float u = sampleNext1D(sg);

        if (gPathGenerator.gDisableLVC) {
            uint l = c.mSample.mSuffix.mLightSubpath.mId.mId.y * gPathGenerator.mParams.mOutputDim.x + c.mSample.mSuffix.mLightSubpath.mId.mId.x;
            if (l < minid) {
                u = 0; // always pick the lowest ID for deterministic-ness
                minid = l;
            } else
                u = 1;
        }

        if (gUseCausticReservoirs && c.mSample.HasFlag(PathFlags::eCausticLightPath)) {
            cr.Merge(u, c);
        } else {
            r.Merge(u, c);
        }
    }

    // Merge with camera tracing sample

    if (!gPathGenerator.gLightTraceOnly) {
        PathReservoir c = gPathGenerator.LoadOutputReservoir(id);
        c.PrepareMerge();
        r.Merge(sampleNext1D(sg), c);
    }

    r.mM = 1;
    r.FinalizeMerge();
    gPathGenerator.StoreReservoir(id, r);

    if (gUseCausticReservoirs) {
        cr.mM = 1;
        cr.FinalizeMerge();
        gPathGenerator.StoreCausticReservoir(id, cr);
    }
}

[shader("compute")]
[numthreads(8, 8, 1)]
void OutputRadiance(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    float4 radiance = gPathGenerator.mOutputRadiance[id];

    const uint flatId = id.y * gPathGenerator.mParams.mOutputDim.x + id.x;

    // Copy radiance from the pixel's reservoir to the output buffer.

    if (gPathGenerator.gUseResampling) {
        if ((gDebugCausticReservoirs & 1) == 0) {
            const PathReservoir r = gPathGenerator.LoadInputReservoir(id);
            if (r.mW > 0 && r.mSample.IsValid()) {
                radiance.rgb += r.GetRadiance();
            }
        }

        if (gUseCausticReservoirs && (gDebugCausticReservoirs & 2) == 0) {
            const PathReservoir r = gPathGenerator.LoadCausticReservoir(id);
            if (r.mW > 0 && r.mSample.IsValid()) {
                radiance.rgb += r.GetRadiance();
            }
        }
    } else if (gPathGenerator.gBidirectional && ! gPathGenerator.gDisableCameraConnection) {
        // Add light trace contribution from atomic buffer
        radiance.rgb += gPathGenerator.mAtomicRadiance.Load<float3>(flatId * sizeof(float3));
    }

    if (gPathGenerator.gDebugHeatmap && (uint)gPathGenerator.mParams.mDebugCounter != 0 ) {
        const float m = float(gPathGenerator.mOutputCounterData.Load(0));
        const float v = gPathGenerator.mOutputCounterData.Load((1 + flatId) * sizeof(uint));
        radiance = float4( colormapViridis( SafeDivide(v, m) ), 1);

        print("Heatmap value/max:", float2(v, m));
    }

    gPathGenerator.mOutputRadiance[id] = radiance;

}

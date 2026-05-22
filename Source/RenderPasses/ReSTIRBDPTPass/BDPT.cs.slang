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

// ResolveLightTraceReservoirs has been extracted to ResolveLightTrace.cs.slang
// (task #10 — Falcor 8 Slang reflector workaround). Host dispatch points there.

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

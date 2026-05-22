/** Bisect: add ComputeSpatialMisWeight call (helper must actually be invoked, else DCE'd) */
import PathShift;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;
import Utils.Debug.PixelDebug;

Texture2D<uint4> gVertices;
static const RMISType gMISType = (RMISType)SPATIAL_RMIS_TYPE;

SampleGenerator GetNeighborOffsetSampleGenerator(const uint2 id) { return MakeSampleGenerator(id, gRandomSeed + 1); }

PathSample SpatialShift(const PathSample basePath, const PackedPathVertex newVertex, out float jacobian) {
    jacobian = 0;
    PathSample result = {};
    if (!basePath.HasFlag(PathFlags::eCausticLightPath)) {
        int2 tmp;
        result = ShiftPath(basePath, newVertex, tmp, jacobian);
    }
    return result;
}

float ComputeSpatialMisWeight(const uint2 center, PathReservoir sample, float jacobianToCenter, float centerM, int candidateIndex, float candidateTargetPdf) {
    float mi = 0;
    float msum = centerM * sample.mSample.GetTargetPdf() * jacobianToCenter;
    if (candidateIndex == -1)
        mi = msum;
    SampleGenerator spatialSg = GetNeighborOffsetSampleGenerator(center);
    for (uint i = 0; i < gPathGenerator.mParams.mSpatialReuseSamples; i++) {
        const int2 p = center + int2(sample_disk_concentric(sampleNext2D(spatialSg)) * gPathGenerator.mParams.mSpatialReuseRadius);
        if (any(p < 0) || any(p >= gPathGenerator.mParams.mOutputDim) || all(p == center))
            continue;
        if (candidateIndex == i) {
            mi = sample.mM * candidateTargetPdf / jacobianToCenter;
            msum += mi;
            continue;
        }
        const PackedPathVertex vp = gPathGenerator.LoadPrimaryVertex(p);
        if (!vp.IsFinite())
            continue;
        const PathReservoir candidate = gPathGenerator.LoadInputReservoir(p);
        if (!(candidate.mM > 0))
            continue;
        float jacobian;
        const PathSample shifted = SpatialShift(sample.mSample, vp, jacobian);
        if (jacobian > 0) {
            const float m = candidate.mM * shifted.GetTargetPdf() * jacobian;
            msum += m;
            if (candidateIndex == i)
                mi = m;
        }
    }
    return msum > 0 ? mi / msum : 0;
}

[shader("compute")]
[numthreads(8, 4, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim))
        return;
    gPathGenerator.DebugSetPixel(id);

    PathReservoir r = gPathGenerator.LoadInputReservoir(id);
    const PackedPathVertex vertex = gPathGenerator.LoadPrimaryVertex(id);
    if (!vertex.IsFinite()) {
        gPathGenerator.StoreReservoir(id, r);
        return;
    }

    const float centerM = r.mM;
    float misW = ComputeSpatialMisWeight(id, r, 1, centerM, -1, r.mSample.GetTargetPdf());

    // [test] also read from mLightTraceReservoirs (HashMap), like the real
    // ResolveLightTraceReservoirs body does.
    const uint2 range = gPathGenerator.mLightTraceReservoirs.GetCellDataRange(id.y * gPathGenerator.mParams.mOutputDim.x + id.x);
    float sumW = 0;
    for (uint i = range.x; i < range.y; i++) {
        const LightTraceReservoir lr = gPathGenerator.mLightTraceReservoirs[i];
        sumW += lr.W;
    }

    float jacobian;
    PathSample shifted = SpatialShift(r.mSample, vertex, jacobian);

    gPathGenerator.mOutputRadiance[id] = float4(shifted.IsValid() ? 1 : 0, jacobian, misW, sumW);
}

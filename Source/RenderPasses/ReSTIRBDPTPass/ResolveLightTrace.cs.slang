/** [Falcor 8 workaround for task #10] standalone resolve pass.
    Built up from the passing probe minimum.
*/
import Utils.Color.ColorMap;
import PathShift;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;
import Utils.Debug.PixelDebug;

Texture2D<uint4> gResolveVerts;
static const RMISType gResolveMIS = (RMISType)SPATIAL_RMIS_TYPE;
static const bool gUseCausticReservoirs = USE_CAUSTIC_RESERVOIRS;

SampleGenerator GetResolveOffsetSampleGenerator(const uint2 id) { return MakeSampleGenerator(id, gRandomSeed + 1); }

PathSample SpatialShiftHelper(const PathSample basePath, const PackedPathVertex newVertex, out float jacobian) {
    jacobian = 0;
    PathSample result = {};
    if (!basePath.HasFlag(PathFlags::eCausticLightPath)) {
        int2 tmp;
        result = ShiftPath(basePath, newVertex, tmp, jacobian);
    }
    return result;
}

float ComputeWarmupMisWeight(const uint2 center, PathReservoir sample, float jacobianToCenter, float centerM, int candidateIndex, float candidateTargetPdf) {
    float mi = 0;
    float msum = centerM * sample.mSample.GetTargetPdf() * jacobianToCenter;
    if (candidateIndex == -1)
        mi = msum;
    SampleGenerator spatialSg = GetResolveOffsetSampleGenerator(center);
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
        const PathSample shifted = SpatialShiftHelper(sample.mSample, vp, jacobian);
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

    // Warmup helper call — required to keep Slang's ParameterBlock reflector
    // happy with this entry's ShiftPath references (see [[task #10]]).
    const float centerM = r.mM;
    float _warmupMis = ComputeWarmupMisWeight(id, r, 1, centerM, -1, r.mSample.GetTargetPdf());

    // === REAL RESOLVE LOGIC (lifted from BDPT.cs.slang::ResolveLightTraceReservoirs) ===
    SampleGenerator sg = MakeSampleGenerator(id, gRandomSeed);

    const PackedPathVertex primaryVertex = gPathGenerator.LoadPrimaryVertex(id);

    const float m = 1 / float(gPathGenerator.mParams.mLightSubpathCount);

    uint minid = ~0u;
    PathReservoir rOut = {};
    PathReservoir cr = {};

    const uint2 range = gPathGenerator.mLightTraceReservoirs.GetCellDataRange(id.y * gPathGenerator.mParams.mOutputDim.x + id.x);
    for (uint i = range.x; i < range.y; i++) {
        const LightTraceReservoir lr = gPathGenerator.mLightTraceReservoirs[i];
        PathReservoir c = PathReservoir(lr.path, lr.W, 0);
        c.PrepareMerge(m);

        if (gPathGenerator.gShiftLightPathsToPixelCenters && c.mSample.HasFlag(PathFlags::eNonCausticLightPath)) {
            gPathGenerator.DebugSetPixel(-1);
            float jacobian;
            const PathSample shifted = SpatialShiftHelper(c.mSample, primaryVertex, jacobian);
            const bool valid = shifted.IsValid();
            gPathGenerator.DebugSetPixel(id);
            if (!valid || !(jacobian > 0))
                continue;
        }

        float u = sampleNext1D(sg);

        if (gPathGenerator.gDisableLVC) {
            uint l = c.mSample.mSuffix.mLightSubpath.mId.mId.y * gPathGenerator.mParams.mOutputDim.x + c.mSample.mSuffix.mLightSubpath.mId.mId.x;
            if (l < minid) {
                u = 0;
                minid = l;
            } else
                u = 1;
        }

        if (gUseCausticReservoirs && c.mSample.HasFlag(PathFlags::eCausticLightPath)) {
            cr.Merge(u, c);
        } else {
            rOut.Merge(u, c);
        }
    }

    if (!gPathGenerator.gLightTraceOnly) {
        PathReservoir c = gPathGenerator.LoadOutputReservoir(id);
        c.PrepareMerge();
        rOut.Merge(sampleNext1D(sg), c);
    }

    rOut.mM = 1;
    rOut.FinalizeMerge();
    gPathGenerator.StoreReservoir(id, rOut);

    if (gUseCausticReservoirs) {
        cr.mM = 1;
        cr.FinalizeMerge();
        gPathGenerator.StoreCausticReservoir(id, cr);
    }
}

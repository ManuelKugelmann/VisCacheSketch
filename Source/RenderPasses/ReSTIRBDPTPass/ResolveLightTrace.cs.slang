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

// Body verbatim from the original BDPT.cs.slang::ResolveLightTraceReservoirs.
// ONLY change: a single ComputeWarmupMisWeight call inserted after the
// SampleGenerator init, with its result discarded. Required to keep Slang's
// ParameterBlock reflector happy when this entry calls ShiftPath (see [[task #10]]
// and docs/SLANG_AND_FALCOR_NOTES.md). Removing the call re-introduces the
// SIGSEGV during ComputePass::setVars.
[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);
    SampleGenerator sg = MakeSampleGenerator(id, gRandomSeed);

    // [Falcor 8 reflector warmup — additive, no algorithmic effect, keep at
    // function scope so Slang's DCE can't eliminate the ShiftPath reference.]
    const PathReservoir _warmupRes = gPathGenerator.LoadInputReservoir(id);
    const float _warmupMis = ComputeWarmupMisWeight(id, _warmupRes, 1, _warmupRes.mM, -1, _warmupRes.mSample.GetTargetPdf());

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

        if (gPathGenerator.gShiftLightPathsToPixelCenters && c.mSample.HasFlag(PathFlags::eNonCausticLightPath)) {
            gPathGenerator.DebugSetPixel(-1); // dont want messages from this shift
            // Reject path if it is not samplable from the primary vertex
            float jacobian;
            int2 tmp;
            const bool valid = ShiftPath(c.mSample, primaryVertex, tmp, jacobian).IsValid();
            gPathGenerator.DebugSetPixel(id);
            if (!valid || !(jacobian > 0))
                continue;
        }

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

/** ShiftToPrevFrame entry — split out from old TemporalReuse.cs.slang.
    Uses the warmup recipe from task #10/12.
*/
import PathShift;
import Utils.Color.ColorHelpers;
import Utils.Debug.PixelDebug;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;

static const bool gUseCausticReservoirs  = USE_CAUSTIC_RESERVOIRS;

SampleGenerator GetWarmupSG(const uint2 id) { return MakeSampleGenerator(id, gRandomSeed + 1); }

PathSample TempShiftHelper(const PathSample basePath, const PackedPathVertex newVertex, out float jacobian) {
    jacobian = 0;
    PathSample result = {};
    if (!basePath.HasFlag(PathFlags::eCausticLightPath)) {
        int2 tmp;
        result = ShiftPath(basePath, newVertex, tmp, jacobian);
    }
    return result;
}

float ComputeTempWarmupMis(const uint2 center, PathReservoir sample, float jacobianToCenter, float centerM, int candidateIndex, float candidateTargetPdf) {
    float mi = 0;
    float msum = centerM * sample.mSample.GetTargetPdf() * jacobianToCenter;
    if (candidateIndex == -1)
        mi = msum;
    SampleGenerator spatialSg = GetWarmupSG(center);
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
        const PathSample shifted = TempShiftHelper(sample.mSample, vp, jacobian);
        if (jacobian > 0) {
            const float m = candidate.mM * shifted.GetTargetPdf() * jacobian;
            msum += m;
            if (candidateIndex == i)
                mi = m;
        }
    }
    return msum > 0 ? mi / msum : 0;
}

PathSample TemporalShift<let bShiftToPrev : bool>(const uint2 basePixel, const PathSample basePath, const PackedPathVertex newVertex, out float jacobian, out bool causticReject) {
    jacobian = 0;
    causticReject = false;
    PathSample result = {};

    int2 newPixel;
    if (basePath.HasFlag(PathFlags::eCausticLightPath) && gPathGenerator.gBidirectional && !gPathGenerator.gShiftSuffixes) {
        jacobian = 1;
        float3 pos = PathVertex(basePath.mSuffix.mVertex).GetPosition();
        newPixel = bShiftToPrev ? gPathGenerator.GetPrevPixelCoord(pos) : gPathGenerator.GetPixelCoord(pos);
        result = basePath;
    } else {
        result = ShiftPath(basePath, newVertex, newPixel, jacobian, bShiftToPrev);
    }

    if (result.IsValid() && jacobian > 0 && result.HasFlag(PathFlags::eCausticLightPath) && gPathGenerator.gBidirectional) {
        const int2 d = basePixel - newPixel;
        causticReject = dot(d, d) > (gPathGenerator.mParams.mCausticReuseRadius * gPathGenerator.mParams.mCausticReuseRadius);
    }

    return result;
}

[shader("compute")]
[numthreads(8, 4, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    const int2 prevPixel = int2((id + 0.5) + gPathGenerator.mParams.mOutputDim * gPathGenerator.mMotionVectors[id]);
    if (any(prevPixel < 0) || any(prevPixel >= gPathGenerator.mParams.mOutputDim)) return;

    const PackedPathVertex prevVertex = gPathGenerator.LoadPrevPrimaryVertex<true>(prevPixel);
    if (!prevVertex.IsFinite()) return;

    PathReservoir r = gPathGenerator.LoadOutputReservoir(id);

    // Warmup call (task #10/12 recipe)
    const float _warmup = ComputeTempWarmupMis(id, r, 1, r.mM, -1, r.mSample.GetTargetPdf());

    if (r.mSample.IsValid()) {
        bool causticReject;
        float jacobianToPrev;
        const float shiftedTargetPdf = TemporalShift<false>(prevPixel, r.mSample, prevVertex, jacobianToPrev, causticReject).GetTargetPdf();
        r.mSample.mSuffix.mVertex.pad1 = SafeDivide(shiftedTargetPdf, jacobianToPrev);
        gPathGenerator.StoreReservoir(id, r);
    }

    if (gUseCausticReservoirs) {
        r = gPathGenerator.LoadCausticReservoir(id);
        if (r.mSample.IsValid()) {
            int2 newPixel;
            float jacobianToPrev;
            const float shiftedTargetPdf = ShiftCausticPath(r.mSample, newPixel, jacobianToPrev, false).GetTargetPdf();
            r.mSample.mSuffix.mVertex.pad1 = SafeDivide(shiftedTargetPdf, jacobianToPrev);
            r.mSample.mPrefixPdf = shiftedTargetPdf > 0 ? gPathGenerator.LoadPrevCausticReservoir(newPixel).mM : 0;
            gPathGenerator.StoreCausticReservoir(id, r);
        }
    }
}

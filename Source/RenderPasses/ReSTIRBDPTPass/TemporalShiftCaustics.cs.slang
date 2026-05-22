/** ShiftCaustics entry — split out from old TemporalReuse.cs.slang.
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

[shader("compute")]
[numthreads(8, 4, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    PathReservoir r = gUseCausticReservoirs ?
        gPathGenerator.LoadPrevCausticReservoir(id) :
        gPathGenerator.LoadPrevReservoir(id);

    // Warmup call (task #10/12 recipe)
    const float _warmup = ComputeTempWarmupMis(id, r, 1, r.mM, -1, r.mSample.GetTargetPdf());

    if (!(r.mW > 0) || !r.mSample.IsValid() || !r.mSample.HasFlag(PathFlags::eCausticLightPath))
        return;

    const float originalTargetPdf = r.mSample.GetTargetPdf();

    print("Shifting caustic path... f, W:", float2(originalTargetPdf, r.mW));

    int2 newId = id;
    float jacobian = 0;
    r.mSample = ShiftCausticPath(r.mSample, newId, jacobian);

    const bool success = r.mSample.IsValid() && jacobian > 0;
    gPathGenerator.IncrementCounter(success ? DebugCounterType::eCausticShiftSuccesses : DebugCounterType::eCausticShiftFailures);

    if (success) {
        print("   Shifted caustic path. new f, jacobian:", float2(luminance(r.mSample.mContribution), jacobian));

        r.mSample.mSuffix.mVertex.pad1 = jacobian;
        r.mSample.mPrefixPdf = originalTargetPdf;

        const uint flatId = newId.y * gPathGenerator.mParams.mOutputDim.x + newId.x;
        gPathGenerator.mCausticReservoirMap.Insert(flatId, r);
    }
}

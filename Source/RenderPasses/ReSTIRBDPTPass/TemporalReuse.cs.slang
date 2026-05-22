/** Temporal reuse — main entry. Uses the ResolveLightTrace recipe (task #10):
    ComputeTempWarmupMis helper called from main so Slang's ParameterBlock
    reflector handles the entry's ShiftPath references.
*/
import PathShift;
import Utils.Color.ColorHelpers;
import Utils.Debug.PixelDebug;
import Utils.Sampling.SampleGenerator;
import Utils.Math.MathHelpers;

static const bool gUnbiasedTemporalReuse = UNBIASED_TEMPORAL_REUSE;
static const bool gUseCausticShift       = USE_CAUSTIC_SHIFT;
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

void TemporalReuse(const uint2 id, inout SampleGenerator sg, inout PathReservoir r, inout PathReservoir cr) {
    const PackedPathVertex primaryHit = gPathGenerator.LoadPrimaryVertex(id);
    if (!primaryHit.IsFinite()) return;

    const int2 prevPixel = int2((id + 0.5) + gPathGenerator.mParams.mOutputDim * gPathGenerator.mMotionVectors[id]);
    if (any(prevPixel < 0) || any(prevPixel >= gPathGenerator.mParams.mOutputDim)) return;

    PathReservoir candidate = gPathGenerator.LoadPrevReservoir(prevPixel);
    if (!(candidate.mM > 0) || isinf(candidate.mM))
        return;

    const PackedPathVertex prevVertex = gPathGenerator.LoadPrevPrimaryVertex<false>(prevPixel);
    if (!prevVertex.IsFinite())
        return;

    if (r.mSample.IsValid()) {
        print("\nCenter id, seed, bounces:", uint4(r.mSample.mId.mId, r.mSample.mId.mSeed, r.mSample.mBounces));
        print("  f, W, M, suffix:", float4(r.mSample.GetTargetPdf(), r.mW, r.mM, luminance(r.mSample.mSuffix.mContribution)));
    } else {
        print("\nInvalid center sample", 0);
    }

    const float centerM = r.mM;
    float candidateTargetPdf = 0;
    float jacobianToCenter = 0;
    bool causticCandidate = false;

    if (candidate.mSample.IsValid()) {
        if (candidate.mSample.HasFlag(PathFlags::eCausticLightPath) && gUseCausticShift) {
            causticCandidate = true;
        } else {
            print("Candidate id, seed, bounces:", uint4(candidate.mSample.mId.mId, candidate.mSample.mId.mSeed, candidate.mSample.mBounces));
            print("  f, W, M, suffix:", float4(candidate.mSample.GetTargetPdf(), candidate.mW, candidate.mM, luminance(candidate.mSample.mSuffix.mContribution)));

            candidateTargetPdf = candidate.mSample.GetTargetPdf();
            bool causticReject;
            candidate.mSample = TemporalShift<false>(id, candidate.mSample, primaryHit, jacobianToCenter, causticReject);
            if (causticReject) {
                candidate.mSample = {};
                jacobianToCenter = 0;
            }
            gPathGenerator.IncrementCounter( candidate.mSample.IsValid() && jacobianToCenter > 0 ? DebugCounterType::eTemporalShiftSuccesses : DebugCounterType::eTemporalShiftFailures );
            print("  f, jacobianToCenter:", float2(candidate.mSample.GetTargetPdf(), jacobianToCenter));
        }
    } else {
        print("Invalid candidate sample", 0);
    }

    {
        const float mi = SafeDivide(candidate.mM * candidateTargetPdf, jacobianToCenter);
        const float m = SafeDivide(mi, mi + centerM * candidate.mSample.GetTargetPdf());
        candidate.PrepareMerge(m, jacobianToCenter);
    }

    {
        float f = 0;
        if (r.mSample.IsValid()) {
            if (gUnbiasedTemporalReuse) {
                f = r.mSample.mSuffix.mVertex.pad1;
            } else {
                bool causticReject;
                float jacobianToPrev;
                const float shiftedTargetPdf = TemporalShift<true>(prevPixel, r.mSample, prevVertex, jacobianToPrev, causticReject).GetTargetPdf();
                f = SafeDivide(shiftedTargetPdf, jacobianToPrev);
                print("  f, jacobianToPrev:", float2(shiftedTargetPdf, jacobianToPrev));
            }
        }

        const float mi = centerM * r.mSample.GetTargetPdf();
        const float m = SafeDivide(mi, mi + candidate.mM * f);
        r.PrepareMerge(m);
    }

    if (!causticCandidate) {
        if (r.Merge(sampleNext1D(sg), candidate))
            gPathGenerator.IncrementCounter(DebugCounterType::eTemporalReuseAcceptances);
    }

    if (gUseCausticShift) {
        if (gUseCausticReservoirs) {
            float m = 0;
            if (cr.mSample.IsValid()) {
                float f, prevM;
                if (gUnbiasedTemporalReuse) {
                    f = cr.mSample.mSuffix.mVertex.pad1;
                    prevM = cr.mSample.mPrefixPdf;
                    cr.mSample.mPrefixPdf = 1;
                } else {
                    int2 newPixel;
                    float jacobianToPrev;
                    const float shiftedTargetPdf = ShiftCausticPath(cr.mSample, newPixel, jacobianToPrev, true).GetTargetPdf();
                    f = SafeDivide(shiftedTargetPdf, jacobianToPrev);
                    prevM = gPathGenerator.LoadPrevCausticReservoir(newPixel).mM;
                    print("  f, jacobianToPrev:", float2(shiftedTargetPdf, jacobianToPrev));
                }

                const float mi = cr.mM * cr.mSample.GetTargetPdf();
                m = SafeDivide(mi, mi + prevM * f);
            }
            cr.PrepareMerge(m);
        }

        const uint2 range = gPathGenerator.mCausticReservoirMap.GetCellDataRange(id.y * gPathGenerator.mParams.mOutputDim.x + id.x);
        for (uint i = range.x; i < range.y; i++) {
            candidate = gPathGenerator.mCausticReservoirMap[i];
            jacobianToCenter   = candidate.mSample.mSuffix.mVertex.pad1;
            candidateTargetPdf = candidate.mSample.mPrefixPdf;
            candidate.mSample.mPrefixPdf = 1;

            const float rM = gUseCausticReservoirs ? cr.mM : r.mM;

            {
                const float mi = SafeDivide(candidate.mM * candidateTargetPdf, jacobianToCenter);
                const float m = SafeDivide(mi, mi + rM * candidate.mSample.GetTargetPdf());
                candidate.PrepareMerge(m, jacobianToCenter);
            }

            if (gUseCausticReservoirs) {
                candidate.mM = 0;
                if (cr.Merge(sampleNext1D(sg), candidate))
                    gPathGenerator.IncrementCounter(DebugCounterType::eCausticReuseAcceptances);
            } else {
                if (r.Merge(sampleNext1D(sg), candidate))
                    gPathGenerator.IncrementCounter(DebugCounterType::eCausticReuseAcceptances);
            }
        }

        if (gUseCausticReservoirs) {
            float proxyM = gPathGenerator.LoadPrevCausticReservoir(prevPixel).mM;
            cr.mM += proxyM;
            cr.FinalizeMerge();
        }
    }

    r.FinalizeMerge();
}

[shader("compute")]
[numthreads(8, 4, 1)]
void main(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    SampleGenerator sg = MakeSampleGenerator(id, gRandomSeed);

    PathReservoir r = gPathGenerator.LoadOutputReservoir(id);
    PathReservoir cr = {};
    if (gUseCausticReservoirs) cr = gPathGenerator.LoadCausticReservoir(id);

    // Warmup call (task #10/12 recipe) — keeps Slang reflector happy.
    const float _warmup = ComputeTempWarmupMis(id, r, 1, r.mM, -1, r.mSample.GetTargetPdf());

    TemporalReuse(id, sg, r, cr);

    if (gPathGenerator.mParams.mMCap > 0) r.mM = min(r.mM, gPathGenerator.mParams.mMCap);
    gPathGenerator.StoreReservoir(id, r);

    if (gUseCausticReservoirs) {
        if (gPathGenerator.mParams.mMCap > 0) cr.mM = min(cr.mM, gPathGenerator.mParams.mMCap);
        gPathGenerator.StoreCausticReservoir(id, cr);
    }
}

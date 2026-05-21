import PathShift;
import Utils.Color.ColorHelpers;
import Utils.Debug.PixelDebug;
import Utils.Sampling.SampleGenerator;

static const bool gUnbiasedTemporalReuse = UNBIASED_TEMPORAL_REUSE;
static const bool gUseCausticShift       = USE_CAUSTIC_SHIFT;
static const bool gUseCausticReservoirs  = USE_CAUSTIC_RESERVOIRS;

PathSample TemporalShift<let bShiftToPrev : bool>(const uint2 basePixel, const PathSample basePath, const PackedPathVertex newVertex, out float jacobian, out bool causticReject) {
    jacobian = 0;
    causticReject = false;
    PathSample result = {};

    int2 newPixel;
    if (basePath.HasFlag(PathFlags::eCausticLightPath) && gPathGenerator.gBidirectional && !gPathGenerator.gShiftSuffixes) {
        // just copy caustic paths if suffix shifts are disabled
        jacobian = 1;
        float3 pos = PathVertex(basePath.mSuffix.mVertex).GetPosition();
        newPixel = bShiftToPrev ? gPathGenerator.GetPrevPixelCoord(pos) : gPathGenerator.GetPixelCoord(pos);
        result = basePath;
    } else {
        result = ShiftPath(basePath, newVertex, newPixel, jacobian, bShiftToPrev);
    }

    if (result.IsValid() && jacobian > 0 && result.HasFlag(PathFlags::eCausticLightPath) && gPathGenerator.gBidirectional) {
        // When caustic shifts are disabled, reject caustic paths if they don't land in the same pixel
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

    // shift candidate from last frame to current frame

    float candidateTargetPdf = 0;
    float jacobianToCenter = 0;

    bool causticCandidate = false;

    if (candidate.mSample.IsValid()) {
        if (candidate.mSample.HasFlag(PathFlags::eCausticLightPath) && gUseCausticShift) {
            // caustic samples handled separately below
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

    // Talbot RMIS

    // apply mis weight to previous frame's sample
    {
        const float mi = SafeDivide(candidate.mM * candidateTargetPdf, jacobianToCenter);
        const float m = SafeDivide(
            mi,
            mi + centerM * candidate.mSample.GetTargetPdf());
        candidate.PrepareMerge(m, jacobianToCenter);
    }

    // apply mis weight to current frame's sample r.mSample
    {
        // shift current sample to previous frame
        float f = 0;
        if (r.mSample.IsValid()) {
            if (gUnbiasedTemporalReuse) {
                // sample was already shifted in ShiftToPrevFrame
                // HACK: storing 'shiftedTargetPdf / jacobianToPrev' in reservoir
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
        const float m = SafeDivide(
            mi,
            mi + candidate.mM * f);
        r.PrepareMerge(m);
    }

    if (!causticCandidate) {
        // perform the merge
        if (r.Merge(sampleNext1D(sg), candidate))
            gPathGenerator.IncrementCounter(DebugCounterType::eTemporalReuseAcceptances);
    }


    // merge with caustic reservoirs
    if (gUseCausticShift) {

        // shift current caustic sample to previous frame
        if (gUseCausticReservoirs) {
            float m = 0;
            if (cr.mSample.IsValid()) {
                float f, prevM;
                if (gUnbiasedTemporalReuse) {
                    // sample was already shifted in ShiftToPrevFrame
                    // HACK: storing 'shiftedTargetPdf / jacobianToPrev' in reservoir
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
                m = SafeDivide(
                    mi,
                    mi + prevM * f);
            }

            cr.PrepareMerge(m);
        }

        // perform the merge
        const uint2 range = gPathGenerator.mCausticReservoirMap.GetCellDataRange(id.y * gPathGenerator.mParams.mOutputDim.x + id.x);
        for (uint i = range.x; i < range.y; i++) {
            candidate = gPathGenerator.mCausticReservoirMap[i];

            // HACK: store jacobian and original target pdf in reservoir
            jacobianToCenter   = candidate.mSample.mSuffix.mVertex.pad1;
            candidateTargetPdf = candidate.mSample.mPrefixPdf;
            candidate.mSample.mPrefixPdf = 1;

            const float rM = gUseCausticReservoirs ? cr.mM : r.mM;

            // apply mis weight to previous frame's sample (same Talbot RMIS as for non-caustic samples)
            {
                const float mi = SafeDivide(candidate.mM * candidateTargetPdf, jacobianToCenter);
                const float m = SafeDivide(
                    mi,
                    mi + rM * candidate.mSample.GetTargetPdf());
                candidate.PrepareMerge(m, jacobianToCenter);
            }

            if (gUseCausticReservoirs) {
                candidate.mM = 0; // dont contribute to the current reservoir's M
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

    print("Final center f, W, M, suffix:", float4(r.mSample.GetTargetPdf(), r.mW, r.mM, luminance(r.mSample.mSuffix.mContribution)));
    print("  bounces, lv, prefix:", float3(r.mSample.mBounces, r.mSample.mSuffix.mLightSubpath.mVertexCount, r.mSample.mPrefixBounces));
}

// Shift current frame's reservoirs to the previous frame. This should be called with last frame's parameters.
// Store the shifted target pdf and jacobian in extra space in the current frame's reservoir
[shader("compute")]
[numthreads(8, 4, 1)]
void ShiftToPrevFrame(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    const int2 prevPixel = int2((id + 0.5) + gPathGenerator.mParams.mOutputDim * gPathGenerator.mMotionVectors[id]);
    if (any(prevPixel < 0) || any(prevPixel >= gPathGenerator.mParams.mOutputDim)) return;

    const PackedPathVertex prevVertex = gPathGenerator.LoadPrevPrimaryVertex<true>(prevPixel);
    if (!prevVertex.IsFinite()) return;

    PathReservoir r = gPathGenerator.LoadOutputReservoir(id);
    if (r.mSample.IsValid()) {
        bool causticReject;
        float jacobianToPrev;
        const float shiftedTargetPdf = TemporalShift<false>(prevPixel, r.mSample, prevVertex, jacobianToPrev, causticReject).GetTargetPdf();

        // HACK: storing 'shiftedTargetPdf / jacobianToPrev' in reservoir
        r.mSample.mSuffix.mVertex.pad1 = SafeDivide(shiftedTargetPdf, jacobianToPrev);

        gPathGenerator.StoreReservoir(id, r);
    }

    if (gUseCausticReservoirs) {
        r = gPathGenerator.LoadCausticReservoir(id);
        if (r.mSample.IsValid()) {
            int2 newPixel;
            float jacobianToPrev;
            const float shiftedTargetPdf = ShiftCausticPath(r.mSample, newPixel, jacobianToPrev, false).GetTargetPdf();

            // HACK: storing 'shiftedTargetPdf / jacobianToPrev' in reservoir
            r.mSample.mSuffix.mVertex.pad1 = SafeDivide(shiftedTargetPdf, jacobianToPrev);
            // HACK: storing prev caustic reservoir's M in reservoir
            r.mSample.mPrefixPdf = shiftedTargetPdf > 0 ? gPathGenerator.LoadPrevCausticReservoir(newPixel).mM : 0;

            gPathGenerator.StoreCausticReservoir(id, r);
        }
    }
}

// Shift last frame's caustics to the current frame.
// Shifted reservoirs are added to the mCausticReservoirMap and merged in the main temporal reuse dispatch above
[shader("compute")]
[numthreads(8, 4, 1)]
void ShiftCaustics(uint3 index: SV_DispatchThreadID) {
    const uint2 id = index.xy;
    if (any(id >= gPathGenerator.mParams.mOutputDim)) return;
    gPathGenerator.DebugSetPixel(id);

    PathReservoir r = gUseCausticReservoirs ?
        gPathGenerator.LoadPrevCausticReservoir(id) :
        gPathGenerator.LoadPrevReservoir(id);

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

        // HACK: store jacobian and original target pdf in reservoir
        r.mSample.mSuffix.mVertex.pad1 = jacobian;
        r.mSample.mPrefixPdf = originalTargetPdf; // prefixPdf is not used (and always 1) for caustic paths

        const uint flatId = newId.y * gPathGenerator.mParams.mOutputDim.x + newId.x;
        gPathGenerator.mCausticReservoirMap.Insert(flatId, r);

        //if (gUseCausticReservoirs && any(id != newId))
        //    gPathGenerator.mLastCausticReservoirs[flatId].mM = 1;
    }
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

    TemporalReuse(id, sg, r, cr);

    if (gPathGenerator.mParams.mMCap > 0) r.mM = min(r.mM, gPathGenerator.mParams.mMCap);
    gPathGenerator.StoreReservoir(id, r);

    if (gUseCausticReservoirs) {
        if (gPathGenerator.mParams.mMCap > 0) cr.mM = min(cr.mM, gPathGenerator.mParams.mMCap);
        gPathGenerator.StoreCausticReservoir(id, cr);
    }
}

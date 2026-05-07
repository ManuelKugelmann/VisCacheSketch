/***************************************************************************
 # ReSTIR-PT path reservoir struct (restirpt_2d, Phase 1).
 #
 # Algorithmic parity target: `Source/RenderPasses/ReSTIRPTPass/PathReservoir.slang`
 # (DQLin reference). Field layout mirrors the reference so GRIS math
 # ports cleanly in Phase 2; helper organization is fresh, designed for
 # native Falcor PathTracer integration (no Falcor8Compat shim).
 #
 # v1 scope: non-BPR only (BPR = PathSamplingMode::PathReuse, deferred to
 # Phase 4). Lin 2026 §6.3 vector-valued resampling weights kept as a slot
 # for binary layout parity (was reverted in the reference per PORT_NOTES.md
 # §12 #4).
 **************************************************************************/
#pragma once

__exported import Scene.HitInfo;
import Utils.Math.PackedFormats;
import Utils.Sampling.SampleGenerator;

// -----------------------------------------------------------------------
// Static config (non-BPR, real-time). Phase 4 will gate BPR via
// PathSamplingMode::PathReuse define.
// -----------------------------------------------------------------------
static const int kRcAttrCount         = 1;     ///< 1 = non-BPR; 2 = BPR (deferred).
static const int kMaximumPathLength   = 15;    ///< Encoded in 4 bits inside ReSTIRPathFlags.
static const int kRcDataPathNum       = 6;     ///< Real-time PixelReconnectionData slots.
static const int kRcDataPadSize       = 1;     ///< Padding to 256-byte stride.

// -----------------------------------------------------------------------
// ReSTIRPathFlags — packed path-type / vertex-class indicator.
//   bits  0..3   : path length (0..15)
//   bits  4..7   : rcVertex length (0..15)
//   bit   8      : isDeltaEvent BEFORE rcVertex
//   bit   9      : isDeltaEvent AT rcVertex
//   bits 10..11  : isTransmissionEvent {before, at} rcVertex
//   bit  16      : last vertex sampled NEE
//   bit  17      : forced-NEE-as-rcVertex (Lin 2026 §6.2.3, deferred)
//   bits 18..19  : NEE light type (LightType enum)
//   bits 26..27  : isSpecularBounce {before, at} rcVertex
//   bits 30..31  : BPR rcLightType (BPR-only)
// -----------------------------------------------------------------------
struct ReSTIRPathFlags
{
    int flags = 0;

    [mutating] void insertPathLength(int n)        { flags = (flags & ~0xF)  | (n & 0xF); }
    [mutating] void insertRcVertexLength(int n)    { flags = (flags & ~0xF0) | ((n & 0xF) << 4); }
    int pathLength()                               { return  flags        & 0xF;  }
    int rcVertexLength()                           { return (flags >> 4)  & 0xF;  }

    [mutating] void insertIsDeltaEvent(bool v, bool beforeRc)
    {
        int bit = beforeRc ? 0x100 : 0x200;
        flags = v ? (flags | bit) : (flags & ~bit);
    }
    bool decodeIsDeltaEvent(bool beforeRc)         { return (flags & (beforeRc ? 0x100 : 0x200)) != 0; }

    [mutating] void insertIsTransmissionEvent(bool v, bool beforeRc)
    {
        int bit = beforeRc ? 0x400 : 0x800;
        flags = v ? (flags | bit) : (flags & ~bit);
    }
    bool decodeIsTransmissionEvent(bool beforeRc)  { return (flags & (beforeRc ? 0x400 : 0x800)) != 0; }

    [mutating] void insertIsSpecularBounce(bool v, bool beforeRc)
    {
        int bit = beforeRc ? 0x4000000 : 0x8000000;
        flags = v ? (flags | bit) : (flags & ~bit);
    }
    bool decodeIsSpecularBounce(bool beforeRc)     { return (flags & (beforeRc ? 0x4000000 : 0x8000000)) != 0; }

    [mutating] void insertLastVertexNEE(bool v)    { flags = v ? (flags | 0x10000) : (flags & ~0x10000); }
    bool lastVertexNEE()                           { return (flags & 0x10000) != 0; }

    [mutating] void insertIsForcedNEE(bool v)      { flags = v ? (flags | 0x20000) : (flags & ~0x20000); }
    bool isForcedNEE()                             { return (flags & 0x20000) != 0; }

    [mutating] void insertLightType(uint t)        { flags = (flags & ~0xC0000) | ((int(t) & 3) << 18); }
    uint lightType()                               { return uint((flags >> 18) & 3); }

    [mutating] void transferDeltaInformation(ReSTIRPathFlags src)
    {
        flags = (flags & ~0x300) | (src.flags & 0x300);
    }
    [mutating] void transferTransmissionInformation(ReSTIRPathFlags src)
    {
        flags = (flags & ~0xC00) | (src.flags & 0xC00);
    }
    [mutating] void transferSpecularBounceInformation(ReSTIRPathFlags src)
    {
        flags = (flags & ~0xC000000) | (src.flags & 0xC000000);
    }
};

// -----------------------------------------------------------------------
// TriMeshHitInfo — compact reconnection-vertex hit (instance + prim + barys).
// Reconstructs to a HitInfo for shading-data loads at shift time.
// -----------------------------------------------------------------------
struct TriMeshHitInfo
{
    uint   instanceID;       ///< 0xffffffff = invalid (no rcVertex stored).
    uint   primitiveIndex;
    float2 barycentrics;

    HitInfo getHitInfo()
    {
        if (instanceID == 0xffffffffu) return HitInfo();
        TriangleHit h;
        h.instanceID    = GeometryInstanceID(instanceID, 0);
        h.primitiveIndex = primitiveIndex;
        h.barycentrics  = barycentrics;
        return HitInfo(h);
    }

    [mutating] void initFromHitInfo(HitInfo h)
    {
        if (!h.isValid()) { instanceID = 0xffffffffu; return; }
        TriangleHit t   = h.getTriangleHit();
        instanceID      = t.instanceID.index;
        primitiveIndex  = t.primitiveIndex;
        barycentrics    = t.barycentrics;
    }

    bool isValid() { return instanceID != 0xffffffffu; }
};

// -----------------------------------------------------------------------
// ReconnectionData — captured at the previous vertex of rcVertex during the
// path-walk; needed by the hybrid-shift replay to pick up where the prefix
// random-replay leaves off. One per stored path (PixelReconnectionData
// holds kRcDataPathNum of these for path-reuse mode).
// -----------------------------------------------------------------------
struct ReconnectionData
{
    HitInfo rcPrevHit;        ///< 16 B  — hit at the vertex BEFORE rcVertex.
    float3  rcPrevWo;         ///< 12 B  — outgoing direction at that vertex.
    float3  pathThroughput;   ///< 12 B  — accumulated throughput up to that vertex.

    __init(HitInfo h, float3 wo, float3 thp) { rcPrevHit = h; rcPrevWo = wo; pathThroughput = thp; }

    [mutating] void Init()
    {
        rcPrevHit.data[0] = 0u;
        rcPrevHit.data[1] = 0u;
        rcPrevHit.data[2] = 0u;
        rcPrevHit.data[3] = 0u;
        rcPrevWo          = float3(0.f);
        pathThroughput    = float3(1.f);
    }
};

// -----------------------------------------------------------------------
// PixelReconnectionData — per-pixel buffer of reconnection data slots.
// Real-time = 6 paths × 40 B = 240 B + 16 B padding → 256 B stride.
// -----------------------------------------------------------------------
struct PixelReconnectionData
{
    ReconnectionData data[kRcDataPathNum];
    float4 padding[kRcDataPadSize];
};

// -----------------------------------------------------------------------
// PathReuseMISWeight — precomputed pairwise-MIS weights for BPR (Phase 4).
// -----------------------------------------------------------------------
struct PathReuseMISWeight
{
    float rcBSDFMISWeight;
    float rcNEEMISWeight;
};

// -----------------------------------------------------------------------
// PathReservoir — non-BPR layout (~100 B). Field order mirrors the DQLin
// reference for binary parity; method organization is fresh.
//
// `weight` semantics depend on lifecycle stage:
//   - During RIS streaming:        `weight` = w_sum (sum of w_i)
//   - After RIS finalization:      `weight` = 1 / (M · p̂(y)) · w_sum  (RIS estimator)
//
// `F` caches the integrand of the currently-selected path so the RIS
// resample target function can be re-evaluated at shift time without
// re-tracing.
// -----------------------------------------------------------------------
struct PathReservoir
{
    float            M             = 0.f;     ///< Sample count (fractional for temporal-history M-cap).
    float            weight        = 0.f;     ///< w_sum during RIS, RIS-estimator weight after finalize.
    ReSTIRPathFlags  pathFlags;                ///< Path topology + delta/transmission/specular flags.
    uint             rcRandomSeed  = 0u;      ///< RNG state captured AFTER rcVertex (hybrid-shift replay).
    float3           F             = float3(0.f); ///< Cached integrand of the currently-selected path.
    float3           weightVec     = float3(0.f); ///< Vector-valued weight slot (Lin 2026 §6.3, reverted in reference; kept for binary parity).
    float            lightPdf      = 0.f;     ///< NEE light pdf (may shift with transmission).
    float3           cachedJacobian = float3(0.f); ///< {prev_scatter_pdf, scatter_pdf, geometry_term} at rcVertex.
    uint             initRandomSeed = 0u;     ///< RNG state at first bounce (hybrid-shift random-distance threshold).
    TriMeshHitInfo   rcVertexHit;              ///< Reconnection-vertex hit (16 B).
    float3           rcVertexPosW       = float3(0.f);  ///< Cached world-space position of rcVertex (avoids gScene.getVertexData in shift kernel — too heavy for per-pixel × per-neighbor scene access).
    float3           rcVertexFaceN      = float3(0.f);  ///< Cached face normal at rcVertex (same reason).
    float3           primaryHitPosW     = float3(0.f);  ///< Cached primary-hit world position (used for cross-frame disocclusion rejection in temporal merge — no prev-frame V-buffer otherwise).
    float3           primaryHitFaceN    = float3(0.f);  ///< Cached primary-hit face normal (same purpose).
    float3           rcVertexWi[kRcAttrCount];        ///< Incident direction at rcVertex.
    float3           rcVertexIrradiance[kRcAttrCount];///< Sampled irradiance at rcVertex.

    [mutating] void init()
    {
        M              = 0.f;
        weight         = 0.f;
        pathFlags.flags = 0;
        pathFlags.insertRcVertexLength(kMaximumPathLength);
        F              = float3(0.f);
        weightVec      = float3(0.f);
        lightPdf       = 0.f;
        cachedJacobian = float3(0.f);
        rcRandomSeed   = 0u;
        initRandomSeed = 0u;
        rcVertexHit.instanceID = 0xffffffffu;   // invalid sentinel
        rcVertexPosW           = float3(0.f);
        rcVertexFaceN          = float3(0.f);
        primaryHitPosW         = float3(0.f);
        primaryHitFaceN        = float3(0.f);
        for (int i = 0; i < kRcAttrCount; ++i)
        {
            rcVertexWi[i]         = float3(0.f);
            rcVertexIrradiance[i] = float3(0.f);
        }
    }

    bool hasValidRcVertex() { return rcVertexHit.isValid(); }

    /// Apply Lambertian-cosine shift correction in-place. Encapsulates the
    /// field write into a method so Slang/DXC compiles it as part of the
    /// PathReservoir vtable rather than as a naked struct-field write —
    /// the latter triggers GPU TDR when its RHS is derived from ShadingData
    /// in the SpatialReuse compute pass.
    [mutating]
    void applyLambertianShiftInPlace(float cosDstAtPrimary, float jacobian)
    {
        float scale = (1.f / 3.14159265f) * cosDstAtPrimary;
        F      = F      * scale;
        weight = weight * scale * jacobian;
    }

    // NOTE: the trace-pass-only global `gRestirPTReservoirs` lives in
    // PathTracer.slang gated on USE_RESTIRPT, NOT here. Declaring it in
    // this shared header would import an unbound UAV into every other
    // pass that includes PathReservoir (e.g. PathReuseSpatial) and
    // segfault on dispatch.

    // -------------------------------------------------------------------
    // GRIS streaming-add helpers — algorithmically equivalent to the
    // reference at `Source/RenderPasses/ReSTIRPTPass/PathReservoir.slang`
    // lines 301-530. Non-BPR only (BPR deferred to Phase 4).
    // -------------------------------------------------------------------

    /// Luminance scalarization (Rec. 601 weights, mirrors the reference).
    static float toScalar(float3 color)
    {
        return dot(color, float3(0.299f, 0.587f, 0.114f));
    }

    static float computeWeight(float3 color, bool binarize = false)
    {
        float w = toScalar(color);
        if (binarize && w > 0.f) w = 1.f;
        return w;
    }

    /// RIS streaming-add: incorporate one new sample with target-pdf `p`.
    /// Returns true if `in_F` is the new survivor.
    [mutating]
    bool add<S : ISampleGenerator>(float3 in_F, float p, inout S sg)
    {
        M += 1.f;
        float w = toScalar(in_F) / p;
        if (isnan(w) || isinf(w) || w == 0.f) return false;

        weight    += w;
        weightVec += in_F / p;            // Lin 2026 §6.3 vector mirror

        if (sampleNext1D(sg) * weight <= w)
        {
            F = in_F;
            return true;
        }
        return false;
    }

    /// GRIS merge with constant MIS (RIS form — `inReservoir.M` factors into weight).
    [mutating]
    bool merge<S : ISampleGenerator>(float3 in_F, float in_Jacobian, PathReservoir inReservoir, inout S sg, float misWeight = 1.f, bool forceAdd = false)
    {
        float w = toScalar(in_F) * in_Jacobian * inReservoir.M * inReservoir.weight * misWeight;
        M += inReservoir.M;
        if (isnan(w) || isinf(w) || w == 0.f) return false;

        weight    += w;
        weightVec += in_F * in_Jacobian * inReservoir.M * inReservoir.weight * misWeight;

        if (forceAdd || sampleNext1D(sg) * weight <= w)
        {
            pathFlags             = inReservoir.pathFlags;
            rcRandomSeed          = inReservoir.rcRandomSeed;
            initRandomSeed        = inReservoir.initRandomSeed;
            cachedJacobian        = inReservoir.cachedJacobian;
            lightPdf              = inReservoir.lightPdf;
            rcVertexWi[0]         = inReservoir.rcVertexWi[0];
            rcVertexHit           = inReservoir.rcVertexHit;
            rcVertexIrradiance[0] = inReservoir.rcVertexIrradiance[0];
            F                     = in_F;
            return true;
        }
        return false;
    }

    /// GRIS merge with explicit resampling MIS weight (no `M` factor — already in misWeight).
    [mutating]
    bool mergeWithResamplingMIS<S : ISampleGenerator>(float3 in_F, float in_Jacobian, PathReservoir inReservoir, inout S sg, float misWeight = 1.f, bool forceAdd = false)
    {
        float w = toScalar(in_F) * in_Jacobian * inReservoir.weight * misWeight;
        M += inReservoir.M;
        if (isnan(w) || isinf(w) || w == 0.f) return false;

        weight    += w;
        weightVec += in_F * in_Jacobian * inReservoir.weight * misWeight;

        if (forceAdd || sampleNext1D(sg) * weight <= w)
        {
            pathFlags             = inReservoir.pathFlags;
            rcRandomSeed          = inReservoir.rcRandomSeed;
            initRandomSeed        = inReservoir.initRandomSeed;
            cachedJacobian        = inReservoir.cachedJacobian;
            lightPdf              = inReservoir.lightPdf;
            rcVertexWi[0]         = inReservoir.rcVertexWi[0];
            rcVertexHit           = inReservoir.rcVertexHit;
            rcVertexIrradiance[0] = inReservoir.rcVertexIrradiance[0];
            F                     = in_F;
            return true;
        }
        return false;
    }

    /// Same-pixel merge (no shift, no Jacobian — additive propagation across temporal/spatial samples at the same pixel).
    [mutating]
    bool mergeInSamplePixel<S : ISampleGenerator>(PathReservoir inReservoir, inout S sg)
    {
        float w = inReservoir.weight;
        M += inReservoir.M;
        if (isnan(w) || isinf(w) || w == 0.f) return false;

        weight    += w;
        weightVec += inReservoir.weightVec;

        if (sampleNext1D(sg) * weight <= w)
        {
            pathFlags             = inReservoir.pathFlags;
            rcRandomSeed          = inReservoir.rcRandomSeed;
            initRandomSeed        = inReservoir.initRandomSeed;
            cachedJacobian        = inReservoir.cachedJacobian;
            lightPdf              = inReservoir.lightPdf;
            rcVertexWi[0]         = inReservoir.rcVertexWi[0];
            rcVertexHit           = inReservoir.rcVertexHit;
            rcVertexIrradiance[0] = inReservoir.rcVertexIrradiance[0];
            F                     = inReservoir.F;
            return true;
        }
        return false;
    }

    /// Pre-merge multiplication: weight × p̂ × M to convert finalized RIS estimate
    /// back into a pre-merge w_sum form before cross-pixel merging.
    [mutating]
    void prepareMerging()
    {
        float scale = toScalar(F) * M;
        weight    *= scale;
        weightVec *= scale;
    }

    /// RIS finalization: weight = w_sum / (p̂ × M) — used when no resampling MIS is applied.
    [mutating]
    void finalizeRIS()
    {
        float p_hat = toScalar(F);
        if (p_hat == 0.f || M == 0.f)
        {
            weight    = 0.f;
            weightVec = float3(0.f);
        }
        else
        {
            float invDen = 1.f / (p_hat * M);
            weight    *= invDen;
            weightVec *= invDen;
        }
        if (isnan(weight) || isinf(weight) || weight < 0.f) weight = 0.f;
        if (any(isnan(weightVec)) || any(isinf(weightVec)) || any(weightVec < 0.f)) weightVec = float3(0.f);
    }

    /// GRIS finalization: weight = w_sum / p̂ — used when MIS already accounts for M.
    [mutating]
    void finalizeGRIS()
    {
        float p_hat = toScalar(F);
        if (p_hat == 0.f)
        {
            weight    = 0.f;
            weightVec = float3(0.f);
        }
        else
        {
            float invDen = 1.f / p_hat;
            weight    *= invDen;
            weightVec *= invDen;
        }
        if (isnan(weight) || isinf(weight) || weight < 0.f) weight = 0.f;
        if (any(isnan(weightVec)) || any(isinf(weightVec)) || any(weightVec < 0.f)) weightVec = float3(0.f);
    }
};

// NOTE: `gRestirPTReservoirs` global is declared in PathTracer.slang under
// `#if USE_RESTIRPT`, so only the trace pass sees it. Other compute passes
// (PathReuseSpatial.cs.slang, etc.) that import PathReservoir for the
// struct + GRIS math do NOT inherit a binding slot.


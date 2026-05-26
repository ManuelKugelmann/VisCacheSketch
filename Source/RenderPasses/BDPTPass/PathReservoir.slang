#include "BitfieldMacros.slangh"
import Utils.Sampling.SampleGenerator;
import Utils.Color.ColorHelpers;
import Utils.Math.Ray;
import Scene.HitInfo;

float  SafeDivide(const float a, const float b) { return abs(b) > 0 ? a / b : 0; }
float3 SafeDivide(const float3 a, const float3 b) { return float3(SafeDivide(a.x, b.x), SafeDivide(a.y, b.y), SafeDivide(a.z, b.z)); }

struct PathId {
    uint mSeed;
    uint mPackedId;

    property uint2 mId {
        get {
            return uint2(
                BF_GET(mPackedId, 0, 16),
                BF_GET(mPackedId, 16, 16));
        }
        set {
            BF_SET(mPackedId, newValue.x, 0, 16);
            BF_SET(mPackedId, newValue.y, 16, 16);
        }
    }

    __init(uint seed, const uint2 id) {
        mSeed = seed;
        mId = id;
    }
}

struct PackedPathVertex {
    PackedHitInfo mPackedHit = 0; ///< Packed hit information.
    float3 mRayOrigin = {};       ///< Origin of the incoming ray (or the outgoing ray for the first light subpath vertex)
    float  mRayDistance = {};     ///< Hit distance of the incoming ray (or the outgoing ray for the first light subpath vertex)
    float3 mRayDirection = {};    ///< Direction of the incoming ray (or the outgoing ray for the first light subpath vertex)
    float  pad1 = {};

    __init(const Ray ray, const HitInfo hit, const float hitDist) {
        mRayOrigin = ray.origin;
        mRayDistance = hitDist;
        mRayDirection = ray.dir;
        mPackedHit = hit.pack(); // [Falcor 8] HitInfo::getData() → HitInfo::pack()
    }

    bool IsFinite() { return HitInfo(mPackedHit).isValid(); }
};

struct LightSubpathData {
    PackedHitInfo mFirstVertex = {};
    PathId mId = {};
    uint mPackedBounces = 0;
    // product of solid-angle BSDF sampling pdfs, and the area-measure pdf of sampling the emissive vertex
    float mPdf = 0;

    property uint mVertexCount {
        get { return BF_GET(mPackedBounces, 0, 16); }
        set { BF_SET(mPackedBounces, newValue, 0, 16); }
    }

    property uint mDiffuseBounces {
        get { return BF_GET(mPackedBounces, 16, 16); }
        set { BF_SET(mPackedBounces, newValue, 16, 16); }
    }

    static LightSubpathData Create(
        const PackedHitInfo firstVertex,
        const PathId id,
        const uint vertexCount,
        const uint diffuseBounces,
        const float pdf) {
        LightSubpathData d = {};
        d.mFirstVertex = firstVertex;
        d.mId = id;
        d.mVertexCount = vertexCount;
        d.mDiffuseBounces = diffuseBounces;
        d.mPdf = pdf;
        return d;
    }
};

struct RecursiveMisState {
    float dVCM = 0;
    float dVC = 0;
    uint  flag = 0;
    uint  pad = 0;
};
struct ReconnectionMisState {
    float invFwdG_r = 0;
    float prod_ratio = 0;
    float prod_dVCM = 0;
    float sumProd_dVCM = 0;
    float end_coeff = 0;
    float end_dVCM = 0;
    float last_invPdf = 0;
};

struct MisEvalData {
    RecursiveMisState    lightSubpathMis = {};
    ReconnectionMisState reconnectionMis = {};

    float cameraScatterFwdPdfW = 0;
    float cameraScatterRevPdfW = 0;
    float lightScatterRevPdfW = 0;
    float lightScatterFwdPdfW = 0;

    float cosCam = 0;
    float cosLight = 0;
    float invDist2 = 0;

    float emissionPdfW = 0;
    float directPdfW = 0;
    float directPdfA = 0;
};
static const uint MisEvalDataSize = sizeof(MisEvalData);

struct PathSuffix {
    PackedPathVertex mVertex = {};          ///< First vertex in the suffix.
    float3           mContribution = 0;     ///< Contributions after the reconnection vertex.
    float            mCameraFwdPdf = 0;     ///< solid-angle sampling PDFs after the reconnection vertex.
    float3           mDirOut = 0;           ///< Outgoing direction from the reconnection vertex.
    float            mDist = 0;             ///< Geometry term between the prefix and the suffix.
    LightSubpathData mLightSubpath = {};    ///< Light subpath id


    float            mCos = 0;              ///< Geometry term between the prefix and the suffix.

    static PathSuffix Create(
        const float3              contribution,
        const float               pdf,
        const PackedPathVertex    reconnectionVertex,
        const float3              reconnectionDirOut,
        const float               reconnectionDistance,
        const float               reconnectionCos,
        const MisEvalData         misData,
        const LightSubpathData    lightSubpath ) {
        PathSuffix s = {};
        s.mVertex          = reconnectionVertex;
        s.mContribution    = contribution;
        s.mCameraFwdPdf    = pdf;
        s.mDirOut          = reconnectionDirOut;
        s.mDist            = reconnectionDistance;
        s.mLightSubpath    = lightSubpath;
        s.mCos             = reconnectionCos;
        return s;
    }
};

// Accumulator for radiance contributions over a pixel's samples-per-pixel loop.
// Single member by default so the compiler can collapse it to a float3; kept
// as a struct so derived/extending passes (ReSTIR, NRD, AOV split, etc.) can
// add fields without touching the BDPT call sites. PathTracerX could use the
// same shape.
struct PathContribution {
    float3 L = float3(0);

    [mutating] void add(float3 v) { L += v; }
}

enum PathFlags : uint {
    eNone                = 0,
    eCausticLightPath    = 1,
    eNonCausticLightPath = 2,
};

// Represents an unweighted path sample, which can be shifted between domains.
struct PathSample {
    PathId mId;
    uint   mPackedBounces = 0;
    uint   mFlags = 0;

    float3 mContribution = 0; ///< Full path contribution. This is the product of BSDFs from each vertex, and emission from the last vertex.
    float  mPrefixPdf = 0;    ///< Product of solid-angle sampling PDFs before the reconnection vertex (excluding the bounce which ends on the reconnection vertex).

    PathSuffix mSuffix = {};

    float mMisWeight = 0;

    // Number of bounces in the full path.
    property uint mBounces {
        get { return BF_GET(mPackedBounces, 0, 11); }
        set { BF_SET(mPackedBounces, newValue, 0, 11); }
    }

    // Number of bounces before the reconnection vertex.
    property uint mPrefixBounces {
        get { return BF_GET(mPackedBounces, 11, 11); }
        set { BF_SET(mPackedBounces, newValue, 11, 11); }
    }

    // Number of diffuse bounces before the reconnection vertex.
    property uint mPrefixDiffuseBounces {
        get { return BF_GET(mPackedBounces, 22, 10); }
        set { BF_SET(mPackedBounces, newValue, 22, 10); }
    }


    bool IsValid() { return any(mContribution > 0) && mPrefixPdf > 0; }
    bool HasFlag(const PathFlags flag) { return (mFlags & uint(flag)) != 0; };
    bool HasSuffix() { return mBounces > mPrefixBounces; }

    float GetTargetPdf() {
        //float p = max(max(mContribution.r, mContribution.g), mContribution.b);
        float p = luminance(mContribution);
        return p * mMisWeight;
    }

    static PathSample Create(
        const float3 contrib,
        const float misWeight,
        const uint bounces,
        const float prefixPdf,
        const uint prefixBounces,
        const uint prefixDiffuseBounces,
        const PathId id,
        const PathSuffix suffix,
        const PathFlags flags ) {
        PathSample ps = {};
        ps.mContribution = contrib;
        ps.mMisWeight = misWeight;
        ps.mPrefixPdf = prefixPdf;
        ps.mBounces = bounces;
        ps.mPrefixBounces = prefixBounces;
        ps.mPrefixDiffuseBounces = prefixDiffuseBounces;
        ps.mFlags = uint(flags);
        ps.mId = id;
        ps.mSuffix = suffix;
        return ps;
	}
};


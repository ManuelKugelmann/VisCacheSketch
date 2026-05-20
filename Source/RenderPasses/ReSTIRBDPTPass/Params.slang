#pragma once
#include "Utils/HostDeviceShared.slangh"

BEGIN_NAMESPACE_FALCOR

enum class RMISType {
    eConstant,
    ePairwise,
    eTalbot
};
FALCOR_ENUM_INFO(
    RMISType, {
        { RMISType::eConstant, "Constant" },
        { RMISType::ePairwise, "Pairwise" },
        { RMISType::eTalbot  , "Talbot" },
    }
);
FALCOR_ENUM_REGISTER(RMISType);

enum class DebugCounterType : uint {
    eScatterRays              = (1 << 0),
    eOcclusionRays            = (1 << 1),

    eTemporalShiftSuccesses   = (1 << 2),
    eSpatialShiftSuccesses    = (1 << 3),
    eCausticShiftSuccesses    = (1 << 4),

    eTemporalShiftFailures    = (1 << 5),
    eSpatialShiftFailures     = (1 << 6),
    eCausticShiftFailures     = (1 << 7),

    eTemporalReuseAcceptances = (1 << 8),
    eSpatialReuseAcceptances  = (1 << 9),
    eCausticReuseAcceptances  = (1 << 10),

    eMisWeightDebug           = (1 << 11),

    eRays                     = (1 << 0) | (1 << 1),
    eShiftSuccesses           = (1 << 2) | (1 << 3) | (1 << 4),
    eShiftFailures            = (1 << 5) | (1 << 6) | (1 << 7),
    eReuseAcceptances         = (1 << 8) | (1 << 9) | (1 << 10),
};
FALCOR_ENUM_INFO(
    DebugCounterType, {
        { (DebugCounterType)0, "None" },

        { DebugCounterType::eScatterRays, "Scatter rays" },
        { DebugCounterType::eOcclusionRays, "Occlusion rays" },
        { DebugCounterType::eRays, "Rays" },

        { DebugCounterType::eTemporalShiftSuccesses, "Temporal shift successes" },
        { DebugCounterType::eSpatialShiftSuccesses, "Spatial shift successes" },
        { DebugCounterType::eCausticShiftSuccesses, "Caustic shift successes" },
        { DebugCounterType::eShiftSuccesses, "Shift successes" },

        { DebugCounterType::eTemporalShiftFailures, "Temporal shift failures" },
        { DebugCounterType::eSpatialShiftFailures, "Spatial shift failures" },
        { DebugCounterType::eCausticShiftFailures, "Caustic shift failures" },
        { DebugCounterType::eShiftFailures, "Shift failures" },

        { DebugCounterType::eTemporalReuseAcceptances, "Temporal reuse acceptances" },
        { DebugCounterType::eSpatialReuseAcceptances, "Spatial reuse acceptances" },
        { DebugCounterType::eCausticReuseAcceptances, "Caustic reuse acceptances" },
        { DebugCounterType::eReuseAcceptances, "Reuse acceptances" },

        { DebugCounterType::eMisWeightDebug, "MIS weight debugging" },
    }
);
FALCOR_ENUM_REGISTER(DebugCounterType);


struct PathGeneratorParams {
    static const uint kMaxBounces = 0xFFFF; ///< reservoirs use 16 bits to store the number of bounces

    float4 mSceneSphere;

    uint2 mOutputDim;

    uint  mCanonicalSpp = 1;
    uint  mMaxBounces = 20;
    uint  mMaxDiffuseBounces = 8;
    float mTerminationProbability = .2f;
    uint  mLightSubpathCount = 1000000;

    float mReconnectionDistance  = 0.3f;
    float mReconnectionRoughness = 0.08f; ///< sqrt(kMinGGXAlpha)
    float mCausticReuseRadius = 0.f;      ///< in pixels. introduces bias.

    uint  mSpatialReuseSamples = 2;
    float mSpatialReuseRadius  = 30.f;
    uint  mMCap                = 20;
    float mEnvMapProb      = 0.5f; ///< Probability of sampling the environment map (instead of emissive triangles).

    int mDebugTotalVertices  = -1; ///< Only render paths with this many vertices.
    int mDebugLightVertices  = -1; ///< Only render paths with this many light vertices.
    int mDebugPrefixBounces  = -1; ///< Only render paths with this many prefix bounces.
    DebugCounterType mDebugCounter = DebugCounterType::eRays;
};

END_NAMESPACE_FALCOR

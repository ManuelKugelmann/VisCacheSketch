/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/
#pragma once
#include "Utils/HostDeviceShared.slangh"

BEGIN_NAMESPACE_FALCOR

/** Enumeration of the atomic counters used.
*/
enum class Counters
{
    // TODO: Better naming
    kGeneralPaths = 0,
    kGeneralPathsProcessed,
    kSpecularPaths,
    kSpecularPathsProcessed,
    kDeltaReflectionPaths,
    kDeltaReflectionPathsProcessed,
    kDeltaTransmissionPaths,
    kDeltaTransmissionPathsProcessed,

    kGeneralQueued,
    kGeneralQueuedProcessed,

    kThreadCountSpecular,
    kThreadCountGeneral,
    kThreadCountDeltaReflection,
    kThreadCountDeltaTransmission,

    // Must be last
    kCount
};

/** Per-sample color format.
*/
enum class ColorFormat
    // TODO: Remove the ifdefs and the include when Slang supports enum type specifiers.
#ifdef HOST_CODE
    : uint32_t
#endif
{
    RGBA32F = 0,
    LogLuvHDR = 1,
};

FALCOR_ENUM_INFO(ColorFormat, {
    { ColorFormat::RGBA32F, "RGBA32F" },
    { ColorFormat::LogLuvHDR, "LogLuvHDR" },
});
FALCOR_ENUM_REGISTER(ColorFormat);

enum class MISHeuristic
    // TODO: Remove the ifdefs and the include when Slang supports enum type specifiers.
#ifdef HOST_CODE
    : uint32_t
#endif
{
    Balance = 0,    ///< Balance heuristic.
    PowerTwo = 1,    ///< Power heuristic (exponent = 2.0).
    PowerExp = 2,    ///< Power heuristic (variable exponent).
};

FALCOR_ENUM_INFO(MISHeuristic, {
    { MISHeuristic::Balance, "Balance" },
    { MISHeuristic::PowerTwo, "PowerTwo" },
    { MISHeuristic::PowerExp, "PowerExp" },
});
FALCOR_ENUM_REGISTER(MISHeuristic);

// Define tile sizes in pixels.
// The frame is divided into tiles stored in scanline order, with pixels in tiles enumerated in Morton order.
static const uint2 kScreenTileDim = { 16, 16 };     ///< Screen-tile dimension in pixels.
static const uint2 kScreenTileBits = { 4, 4 };      ///< Bits needed to describe pixel position within a screen-tile.

// Define path configuration limits.
static const uint kMaxSamplesPerPixel = 64;         ///< Maximum supported sample count. We can use tiling to support large sample counts if needed.
static const uint kMaxFrameDimension = 4096;        ///< Maximum supported frame dimension in pixels along x or y. We can increase the bit allocation if needed.
static const uint kMaxBounces = 14;                ///< Maximum supported number of bounces per bounce category (value 255 is reserved for internal use). The resulting path length may be longer than this.
static const uint kMaxLightSamplesPerVertex = 8;    ///< Maximum number of shadow rays per path vertex for next-event estimation.

enum class ShiftMapping
#ifdef HOST_CODE
    : uint32_t
#endif
{
    Reconnection = 0,
    RandomReplay = 1,
    Hybrid = 2,
};

FALCOR_ENUM_INFO(ShiftMapping, {
    { ShiftMapping::Reconnection, "Reconnection" },
    { ShiftMapping::RandomReplay, "RandomReplay" },
    { ShiftMapping::Hybrid, "Hybrid" },
});
FALCOR_ENUM_REGISTER(ShiftMapping);

enum class LocalStrategy
#ifdef HOST_CODE
    : uint32_t
#endif
{
    None = 0x0,
    RoughnessCondition = 0x1,
    DistanceCondition = 0x2,
};

enum class ReSTIRMISKind
#ifdef HOST_CODE
    : uint32_t
#endif
{
    Constant = 0,
    Talbot = 1,
    Pairwise = 2,
    ConstantBinary = 3,
    ConstantBiased = 4
};

FALCOR_ENUM_INFO(ReSTIRMISKind, {
    { ReSTIRMISKind::Constant, "Constant" },
    { ReSTIRMISKind::Talbot, "Talbot" },
    { ReSTIRMISKind::Pairwise, "Pairwise" },
    { ReSTIRMISKind::ConstantBinary, "ConstantBinary" },
    { ReSTIRMISKind::ConstantBiased, "ConstantBiased" },
});
FALCOR_ENUM_REGISTER(ReSTIRMISKind);

enum class SpatialReusePattern
#ifdef HOST_CODE
    : uint32_t
#endif
{
    Default = 0, // same as in ScreenSpaceReSTIR
    SmallWindow = 1,
};

FALCOR_ENUM_INFO(SpatialReusePattern, {
    { SpatialReusePattern::Default, "Default" },
    { SpatialReusePattern::SmallWindow, "SmallWindow" },
});
FALCOR_ENUM_REGISTER(SpatialReusePattern);

enum class PathSamplingMode
{
    ReSTIR,
    PathReuse,
    PathTracing
};

FALCOR_ENUM_INFO(PathSamplingMode, {
    { PathSamplingMode::ReSTIR, "ReSTIR" },
    { PathSamplingMode::PathReuse, "PathReuse" },
    { PathSamplingMode::PathTracing, "PathTracing" },
});
FALCOR_ENUM_REGISTER(PathSamplingMode);

enum class PathReusePattern
{
    Block,
    NRooks,
    NRooksShift
};


// Import static specialization constants.
#ifndef HOST_CODE
__exported import StaticParams;
__exported import Utils.Math.BitTricks;
#endif

/** Path tracer parmeters shared between host/device code.
*/
struct RestirPathTracerParams
{
    int     useFixedSeed = false;       ///< Use fixed random seed. This is useful for debugging.
    uint    seed = 0;                   ///< Random seed. This will get updated from the host depending on settings.
    uint    fixedSeed = 1;              ///< The seed to use when 'useFixedSeed' is enabled.
    float   lodBias = 0.f;              ///< LOD bias applied to secondary hits.

    // Runtime values
    uint2   frameDim = { 0, 0 };        ///< Frame dimension in pixels.
    uint2   screenTiles = { 0, 0 };     ///< Number of screen-tiles. Screen tiles may extend outside the frame.

    uint    frameCount = 0;             ///< Frames rendered. This is used as random seed.
    uint    localStrategyType = (uint)LocalStrategy::RoughnessCondition | (uint)LocalStrategy::DistanceCondition;
    int     rejectShiftBasedOnJacobian = false; // can be helpful for dynamic geometry
    float   jacobianRejectionThreshold = 10.f;

    // params for roughness condition in mixed strategy
    float   specularRoughnessThreshold = 0.2f; ///< Specular reflection events are only classified as specular if the material's roughness value is equal or smaller than this threshold. Otherwise they are classified diffuse.
    // params for distance condition in mixed strategy
    // Interpreted as a fraction of `sceneRadius` (set in setScene); shaders
    // multiply by sceneRadius at use sites.
    float   nearFieldDistance = 0.03f;
    float   sceneRadius = 1.f;          ///< min(extent.x,y,z) of scene bounds, set by setScene().
    // §8 pathThpMax retired (Lin 2026 footprint criterion + RTXPT FireflyFilter
    // K make path-throughput clamping unnecessary). Slot kept for cbuffer ABI
    // stability; remove fully in the next ABI-breaking pass.
    float   _retiredField0 = 0.f;       // was pathThpMax
    // §15 chroma-preserving soft-clamp: ceiling = K × max-channel(DL).
    // Default 1e9 → branch never fires → effectively disabled. Disabled by
    // default because the GRIS resampling itself handles firefly suppression
    // structurally; the clamp adds bias (output magnitude truncation) for a
    // marginal RMSE win on low-firefly scenes. Same disabled-by-default
    // stance as the RTXDI BoilingFilter port. Set fireflyClampK ≈ 100-1000
    // via render_graph_ReSTIRPT(...) kwarg to engage.
    float   fireflyClampK = 1.e9f;

#ifndef HOST_CODE

    uint getReservoirOffset(const uint2 pixel)
    {
        uint2 tileID = pixel >> kScreenTileBits;

        uint stride = kScreenTileDim.x * kScreenTileDim.y;
        uint tileIdx = tileID.y * screenTiles.x + tileID.x;
        uint tileOffset = tileIdx * stride;

        uint tileBits = kScreenTileBits.x + kScreenTileBits.y;
        uint pixelIdx = interleave_16bit(pixel) & ((1 << tileBits) - 1); // TODO: Use interleave_8bit() if kScreenTileBits <= 4.
        return tileOffset + pixelIdx;
    }

#endif
};

END_NAMESPACE_FALCOR

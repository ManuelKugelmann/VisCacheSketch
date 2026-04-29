/***************************************************************************
 * VisCache.cpp
 *
 * Falcor 8.0 RenderPass implementation.
 * All GPU resources allocated here; hash table exposed to downstream
 * passes (PathTracer, RTXDIPass, ReSTIRPTPass) via InternalDictionary.
 ***************************************************************************/

#include "VisCache.h"
#include <algorithm>
#include <cstring>

// Entry size must match Slang struct VHFEntry (2x uint32 = 8 bytes)
static constexpr size_t kEntrySize = 8u;
// §9.4 Reservoir slot size must match Slang struct WSReservoir
// (8 fields × 4 bytes = 32 bytes — see WSReservoir.slang).
static constexpr size_t kWSReservoirSize = 32u;
/// Five atomic GPU counters, indexed by VisCache.slang's kStat* constants:
///   [0] inserts       — successful vhfInsert() calls (new samples accepted)
///   [1] evictions     — fingerprint overwrites (slot reuse under pressure)
///   [2] misses        — vhfLookup() calls that found no valid entry
///   [3] decayTriggers — decay passes that actually modified an entry (not yet wired)
///   [4] probeSumHi    — high-watermark of linear probe distance (not yet wired)
/// Counters 3-4 are reserved for upcoming diagnostics — buffer is pre-allocated
/// at the full size so adding them doesn't require a buffer resize.
static constexpr uint32_t kStatCount = 5u;

// Diagnostic heatmap output channel names
static const std::string kOutputAccumMeanVarMatCount  = "vcAccumMeanVarMatCount";
static const std::string kOutputFrameMeanVarMatSamplesRaw  = "vcFrameMeanVarMatSamplesRaw";
static const std::string kOutputFrameLevelProbesSamplesCold  = "vcFrameLevelProbesSamplesCold";
static const std::string kOutputFrameHashAHashBHashABRays  = "vcFrameHashAHashBHashABRays";
static const std::string kOutputAccumRaysNoiseErrorCold  = "vcAccumRaysNoiseErrorCold";

static const ChannelList kDiagOutputChannels = {
    { kOutputAccumMeanVarMatCount,  "", "Accumulated avg (R=variance*4, G=maturity, B=mean, A=count)",    true, ResourceFormat::RGBA32Float },
    { kOutputFrameMeanVarMatSamplesRaw,  "", "Frame (R=variance*4, G=maturity, B=mean, A=samplesRaw)",   true, ResourceFormat::RGBA32Float },
    { kOutputFrameLevelProbesSamplesCold,  "", "Frame (R=level, G=probeSteps, B=samples, A=coldmiss)",  true, ResourceFormat::RGBA32Float },
    { kOutputFrameHashAHashBHashABRays,  "", "Hash grid vis (R=posAHash, G=posBHash, B=combinedHash, A=raysTraced)",  true, ResourceFormat::RGBA32Float },
    { kOutputAccumRaysNoiseErrorCold,  "", "Accumulated (R=raysTraced, G=renderNoise, B=renderError, A=coldmiss)",  true, ResourceFormat::RGBA32Float },
};

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, VisCache>();
}

// ---------------------------------------------------------------------------
VisCache::VisCache(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    // Deserialise properties (from Python script or saved graph)
    if (props.has("tableCapacity"))    mParams.tableCapacity    = props["tableCapacity"];
    if (props.has("bootThreshold"))    mParams.bootThreshold    = props["bootThreshold"];
    if (props.has("matureThreshold"))  mParams.matureThreshold  = props["matureThreshold"];
    if (props.has("varThreshold"))     mParams.varThreshold     = props["varThreshold"];
    if (props.has("pMin"))             mParams.pMin             = props["pMin"];
    if (props.has("fireflyBudget"))    mParams.fireflyBudget    = props["fireflyBudget"];
    if (props.has("numLevels"))        mParams.numLevels        = props["numLevels"];
    // autoTuneCells FIRST so the explicit posACoarse below can force it
    // false at the end (variant-level quant choice wins over LEVELS_MULTI's
    // autoTuneCells=True default).
    if (props.has("autoTuneCells"))    mParams.autoTuneCells    = props["autoTuneCells"];
    if (props.has("quantSceneScale"))  mParams.quantSceneScale  = props["quantSceneScale"];
    if (props.has("posACoarse"))     { mParams.posACoarse       = props["posACoarse"];  mParams.autoTuneCells = false; }
    if (props.has("posBCoarse"))       mParams.posBCoarse       = props["posBCoarse"];
    if (props.has("dirBCoarse"))       mParams.dirBCoarse       = props["dirBCoarse"];
    if (props.has("distBCoarse"))      mParams.distBCoarse      = props["distBCoarse"];
    if (props.has("normalACoarse"))    mParams.normalACoarse    = props["normalACoarse"];
    if (props.has("diagAccumWindow"))  mParams.diagAccumWindow  = props["diagAccumWindow"];
    if (props.has("spp"))              mParams.spp              = props["spp"];
    if (props.has("decayPeriod"))      mParams.decayPeriod      = props["decayPeriod"];
    if (props.has("enableDecayAutoTune")) mParams.enableDecayAutoTune = props["enableDecayAutoTune"];

    // VisCache feature + ablation toggles
    if (props.has("enableVisCacheVisibilityCheck"))    mParams.enableVisCacheVisibilityCheck    = props["enableVisCacheVisibilityCheck"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
    if (props.has("jitterFilter"))                  mParams.jitterFilter                  = props["jitterFilter"];
    if (props.has("jitterCell"))                    mParams.jitterCell                    = props["jitterCell"];
    if (props.has("enableVisCacheAdaptivePMin"))   mParams.enableVisCacheAdaptivePMin   = props["enableVisCacheAdaptivePMin"];
    if (props.has("enableVisCacheNormalAddr"))    mParams.enableVisCacheNormalAddr     = props["enableVisCacheNormalAddr"];
    if (props.has("enableVisCacheDirDistAddr"))     mParams.enableVisCacheDirDistAddr     = props["enableVisCacheDirDistAddr"];
    if (props.has("enableVisCacheBootstrapBreak"))  mParams.enableVisCacheBootstrapBreak  = props["enableVisCacheBootstrapBreak"];
    if (props.has("enableVisCacheParentPreinit"))   mParams.enableVisCacheParentPreinit   = props["enableVisCacheParentPreinit"];
    if (props.has("bootThresholdFactorFootprintPx"))                mParams.bootThresholdFactorFootprintPx                = props["bootThresholdFactorFootprintPx"];
    if (props.has("forceDescendFootprintPx"))       mParams.forceDescendFootprintPx       = props["forceDescendFootprintPx"];
    if (props.has("cascadeWindowForward"))          mParams.cascadeWindowForward          = props["cascadeWindowForward"];
    if (props.has("stderrThreshold"))               mParams.stderrThreshold               = props["stderrThreshold"];
    if (props.has("enableHierarchicalConsistency")) mParams.enableHierarchicalConsistency = props["enableHierarchicalConsistency"];
    if (props.has("hierarchicalMuTolerance"))       mParams.hierarchicalMuTolerance       = props["hierarchicalMuTolerance"];
    if (props.has("accelDecayDisagreeThresh"))      mParams.accelDecayDisagreeThresh      = props["accelDecayDisagreeThresh"];
    if (props.has("bootThresholdFine"))             mParams.bootThresholdFine             = props["bootThresholdFine"];
    if (props.has("preinitAmbiguityCutoff"))        mParams.preinitAmbiguityCutoff        = props["preinitAmbiguityCutoff"];
    if (props.has("subframeN"))                     mParams.subframeN                     = props["subframeN"];
    if (props.has("warmupSlotsFirst"))              mParams.warmupSlotsFirst              = props["warmupSlotsFirst"];
    if (props.has("warmupSlotsRun"))                mParams.warmupSlotsRun                = props["warmupSlotsRun"];
    if (props.has("enableWSReservoirs"))            mParams.enableWSReservoirs            = props["enableWSReservoirs"];
    if (props.has("wsLevelOffset"))                 mParams.wsLevelOffset                 = props["wsLevelOffset"];
    if (props.has("wsReservoirCapacity"))           mParams.wsReservoirCapacity           = props["wsReservoirCapacity"];
    if (props.has("wsMCap"))                        mParams.wsMCap                        = props["wsMCap"];
    if (props.has("wsSpatialNeighbours"))           mParams.wsSpatialNeighbours           = props["wsSpatialNeighbours"];
    if (props.has("wsLightMuMin"))                  mParams.wsLightMuMin                  = props["wsLightMuMin"];
    if (props.has("enableDiagnostics"))             mEnableDiagnostics                   = props["enableDiagnostics"];
    if (props.has("diagMode"))                     { uint32_t m = props["diagMode"]; mDiagMode = DiagMode(m); }
    if (props.has("resetAccum"))                   mResetAccum                          = props["resetAccum"];
}

ref<VisCache> VisCache::create(ref<Device> pDevice,
                                          const Properties& props)
{
    return make_ref<VisCache>(pDevice, props);
}

// ---------------------------------------------------------------------------
void VisCache::setProperties(const Properties& props)
{
    if (props.has("tableCapacity"))    mParams.tableCapacity    = props["tableCapacity"];
    if (props.has("bootThreshold"))    mParams.bootThreshold    = props["bootThreshold"];
    if (props.has("matureThreshold"))  mParams.matureThreshold  = props["matureThreshold"];
    if (props.has("varThreshold"))     mParams.varThreshold     = props["varThreshold"];
    if (props.has("pMin"))             mParams.pMin             = props["pMin"];
    if (props.has("fireflyBudget"))    mParams.fireflyBudget    = props["fireflyBudget"];
    if (props.has("numLevels"))        mParams.numLevels        = props["numLevels"];
    // autoTuneCells FIRST so the explicit posACoarse below can force it
    // false at the end (variant-level quant choice wins over LEVELS_MULTI's
    // autoTuneCells=True default).
    if (props.has("autoTuneCells"))    mParams.autoTuneCells    = props["autoTuneCells"];
    if (props.has("quantSceneScale"))  mParams.quantSceneScale  = props["quantSceneScale"];
    if (props.has("posACoarse"))     { mParams.posACoarse       = props["posACoarse"];  mParams.autoTuneCells = false; }
    if (props.has("posBCoarse"))       mParams.posBCoarse       = props["posBCoarse"];
    if (props.has("dirBCoarse"))       mParams.dirBCoarse       = props["dirBCoarse"];
    if (props.has("distBCoarse"))      mParams.distBCoarse      = props["distBCoarse"];
    if (props.has("normalACoarse"))    mParams.normalACoarse    = props["normalACoarse"];
    if (props.has("diagAccumWindow"))  mParams.diagAccumWindow  = props["diagAccumWindow"];
    if (props.has("spp"))              mParams.spp              = props["spp"];
    if (props.has("decayPeriod"))      mParams.decayPeriod      = props["decayPeriod"];
    if (props.has("enableDecayAutoTune")) mParams.enableDecayAutoTune = props["enableDecayAutoTune"];

    if (props.has("enableVisCacheVisibilityCheck"))    mParams.enableVisCacheVisibilityCheck    = props["enableVisCacheVisibilityCheck"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
    if (props.has("jitterFilter"))                  mParams.jitterFilter                  = props["jitterFilter"];
    if (props.has("jitterCell"))                    mParams.jitterCell                    = props["jitterCell"];
    if (props.has("enableVisCacheAdaptivePMin"))   mParams.enableVisCacheAdaptivePMin   = props["enableVisCacheAdaptivePMin"];
    if (props.has("enableVisCacheNormalAddr"))    mParams.enableVisCacheNormalAddr     = props["enableVisCacheNormalAddr"];
    if (props.has("enableVisCacheDirDistAddr"))     mParams.enableVisCacheDirDistAddr     = props["enableVisCacheDirDistAddr"];
    if (props.has("enableVisCacheBootstrapBreak"))  mParams.enableVisCacheBootstrapBreak  = props["enableVisCacheBootstrapBreak"];
    if (props.has("enableVisCacheParentPreinit"))   mParams.enableVisCacheParentPreinit   = props["enableVisCacheParentPreinit"];
    if (props.has("bootThresholdFactorFootprintPx"))                mParams.bootThresholdFactorFootprintPx                = props["bootThresholdFactorFootprintPx"];
    if (props.has("forceDescendFootprintPx"))       mParams.forceDescendFootprintPx       = props["forceDescendFootprintPx"];
    if (props.has("cascadeWindowForward"))          mParams.cascadeWindowForward          = props["cascadeWindowForward"];
    if (props.has("stderrThreshold"))               mParams.stderrThreshold               = props["stderrThreshold"];
    if (props.has("enableHierarchicalConsistency")) mParams.enableHierarchicalConsistency = props["enableHierarchicalConsistency"];
    if (props.has("hierarchicalMuTolerance"))       mParams.hierarchicalMuTolerance       = props["hierarchicalMuTolerance"];
    if (props.has("accelDecayDisagreeThresh"))      mParams.accelDecayDisagreeThresh      = props["accelDecayDisagreeThresh"];
    if (props.has("bootThresholdFine"))             mParams.bootThresholdFine             = props["bootThresholdFine"];
    if (props.has("preinitAmbiguityCutoff"))        mParams.preinitAmbiguityCutoff        = props["preinitAmbiguityCutoff"];
    if (props.has("subframeN"))                     mParams.subframeN                     = props["subframeN"];
    if (props.has("warmupSlotsFirst"))              mParams.warmupSlotsFirst              = props["warmupSlotsFirst"];
    if (props.has("warmupSlotsRun"))                mParams.warmupSlotsRun                = props["warmupSlotsRun"];
    if (props.has("enableWSReservoirs"))            mParams.enableWSReservoirs            = props["enableWSReservoirs"];
    if (props.has("wsLevelOffset"))                 mParams.wsLevelOffset                 = props["wsLevelOffset"];
    if (props.has("wsReservoirCapacity"))           mParams.wsReservoirCapacity           = props["wsReservoirCapacity"];
    if (props.has("wsMCap"))                        mParams.wsMCap                        = props["wsMCap"];
    if (props.has("wsSpatialNeighbours"))           mParams.wsSpatialNeighbours           = props["wsSpatialNeighbours"];
    if (props.has("wsLightMuMin"))                  mParams.wsLightMuMin                  = props["wsLightMuMin"];
    if (props.has("enableDiagnostics"))             mEnableDiagnostics                   = props["enableDiagnostics"];
    if (props.has("diagMode"))                     { uint32_t m = props["diagMode"]; mDiagMode = DiagMode(m); }
    if (props.has("resetAccum"))                   mResetAccum                          = props["resetAccum"];
}

// ---------------------------------------------------------------------------
Properties VisCache::getProperties() const
{
    Properties p;
    p["tableCapacity"] = mParams.tableCapacity;
    p["bootThreshold"]   = mParams.bootThreshold;
    p["matureThreshold"] = mParams.matureThreshold;
    p["varThreshold"]    = mParams.varThreshold;
    p["pMin"]          = mParams.pMin;
    p["fireflyBudget"] = mParams.fireflyBudget;
    p["numLevels"]     = mParams.numLevels;
    p["posACoarse"]     = mParams.posACoarse;
    p["posBCoarse"]     = mParams.posBCoarse;
    p["dirBCoarse"]  = mParams.dirBCoarse;
    p["distBCoarse"]     = mParams.distBCoarse;
    p["normalACoarse"]   = mParams.normalACoarse;
    p["diagAccumWindow"] = mParams.diagAccumWindow;
    p["spp"]           = mParams.spp;
    p["autoTuneCells"] = mParams.autoTuneCells;
    p["quantSceneScale"] = mParams.quantSceneScale;
    p["decayPeriod"]   = mParams.decayPeriod;

    // VisCache feature + ablation toggles
    p["enableVisCacheVisibilityCheck"]    = mParams.enableVisCacheVisibilityCheck;
    p["enableVisCacheLightSelection"]  = mParams.enableVisCacheLightSelection;
    p["enableVisCacheVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    p["enableVisCacheWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    p["enableVisCacheDecay"]           = mParams.enableVisCacheDecay;
    p["enableVisCachePressureEvict"]   = mParams.enableVisCachePressureEvict;
    p["jitterFilter"]                  = mParams.jitterFilter;
    p["jitterCell"]                    = mParams.jitterCell;
    p["enableVisCacheAdaptivePMin"]    = mParams.enableVisCacheAdaptivePMin;
    p["enableVisCacheNormalAddr"]     = mParams.enableVisCacheNormalAddr;
    p["enableVisCacheDirDistAddr"]     = mParams.enableVisCacheDirDistAddr;
    p["enableVisCacheBootstrapBreak"]  = mParams.enableVisCacheBootstrapBreak;
    p["enableVisCacheParentPreinit"]   = mParams.enableVisCacheParentPreinit;
    p["bootThresholdFactorFootprintPx"]                = mParams.bootThresholdFactorFootprintPx;
    p["forceDescendFootprintPx"]       = mParams.forceDescendFootprintPx;
    p["stderrThreshold"]               = mParams.stderrThreshold;
    p["enableHierarchicalConsistency"] = mParams.enableHierarchicalConsistency;
    p["hierarchicalMuTolerance"]       = mParams.hierarchicalMuTolerance;
    p["accelDecayDisagreeThresh"]      = mParams.accelDecayDisagreeThresh;
    p["bootThresholdFine"]             = mParams.bootThresholdFine;
    p["preinitAmbiguityCutoff"]        = mParams.preinitAmbiguityCutoff;
    p["subframeN"]                     = mParams.subframeN;
    p["warmupSlotsFirst"]              = mParams.warmupSlotsFirst;
    p["warmupSlotsRun"]                = mParams.warmupSlotsRun;
    p["enableWSReservoirs"]            = mParams.enableWSReservoirs;
    p["wsLevelOffset"]                 = mParams.wsLevelOffset;
    p["wsReservoirCapacity"]           = mParams.wsReservoirCapacity;
    p["wsMCap"]                        = mParams.wsMCap;
    p["wsSpatialNeighbours"]           = mParams.wsSpatialNeighbours;
    p["wsLightMuMin"]                  = mParams.wsLightMuMin;
    p["enableDiagnostics"]             = mEnableDiagnostics;
    p["diagMode"]                      = uint32_t(mDiagMode);
    p["resetAccum"]                    = mResetAccum;
    return p;
}

// ---------------------------------------------------------------------------
RenderPassReflection VisCache::reflect(const CompileData&)
{
    RenderPassReflection r;
    // Diagnostic heatmap outputs (optional — connect to ColorMapPass).
    addRenderPassOutputs(r, kDiagOutputChannels);
    return r;
}

// ---------------------------------------------------------------------------
void VisCache::compile(RenderContext*, const CompileData& compileData)
{
    mFrameDims = compileData.defaultTexDims;
    allocateBuffers();

    // Decay pass
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/VisCache/VisCacheDecay.cs.slang")
            .csEntry("csDecay");
        DefineList defines;
        defines.add("USE_VISCACHE", "1");
        mpDecayPass = ComputePass::create(mpDevice, desc, defines);
    }

}

// ---------------------------------------------------------------------------
// allocateBuffers: create/recreate all GPU resources.
//
// Called from compile() (initial setup) and setScene() (scene change).
// The hash table capacity is rounded up to the next power-of-two because
// the GPU addressing uses bitwise AND (capacity-1) for slot indexing.
// ---------------------------------------------------------------------------
void VisCache::allocateBuffers()
{
    // Ensure capacity is power-of-two (required for fast modulo via bitmask).
    uint32_t cap = 1u;
    while (cap < mParams.tableCapacity) cap <<= 1;
    mParams.tableCapacity = cap;

    mpHashTable = mpDevice->createStructuredBuffer(
        kEntrySize,
        mParams.tableCapacity,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal,
        nullptr,
        /*createCounter=*/true
    );
    mpHashTable->setName("VHF_HashTable");
    mClearHashTable = true;  // Must clear to empty-slot sentinel (fingerprint=0) before first use

    // GPU params constant buffer — exported via dict for downstream passes.
    mpParamsBuffer = mpDevice->createBuffer(
        sizeof(GPUParams),
        ResourceBindFlags::Constant,
        MemoryType::Upload
    );
    mpParamsBuffer->setName("VHF_Params");

    // 5 atomic counters: inserts, evictions, misses, decayTriggers, probeSumHi
    mpStatsBuffer = mpDevice->createBuffer(
        kStatCount * sizeof(uint32_t),
        ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal
    );
    mpStatsBuffer->setName("VHF_Stats");

    mpStagingBuffer = mpDevice->createBuffer(
        kStatCount * sizeof(uint32_t),
        ResourceBindFlags::None,
        MemoryType::ReadBack
    );

    // §9.4 WS-reservoir buffer — only allocated when the toggle is on,
    // so the legacy path pays no GPU memory. Round capacity up to next pow2
    // so shaders can index via bitwise AND (capacity-1).
    if (mParams.enableWSReservoirs)
    {
        uint32_t wsCap = 1u;
        while (wsCap < std::max(1u, mParams.wsReservoirCapacity)) wsCap <<= 1;
        mParams.wsReservoirCapacity = wsCap;

        if (!mpWSReservoirs || mWSReservoirCapacityCommitted != wsCap)
        {
            mpWSReservoirs = mpDevice->createStructuredBuffer(
                kWSReservoirSize,
                wsCap,
                ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
                MemoryType::DeviceLocal,
                nullptr,
                /*createCounter=*/false
            );
            mpWSReservoirs->setName("VHF_WSReservoirs");
            mWSReservoirCapacityCommitted = wsCap;
        }
    }
    else
    {
        mpWSReservoirs = nullptr;
        mWSReservoirCapacityCommitted = 0u;
    }
}

// ---------------------------------------------------------------------------
// Auto-derive posACoarse (and dependent posBCoarse, distBCoarse) from
// scene bounds. dirBCoarse stays at the user-set default.
//
// Heuristic:
//   posACoarse  = sceneDiameter / 8
//   posBCoarse  = posACoarse * 2  (posB endpoint is coarser)
//   distBCoarse  = posACoarse * 8  (distance bins are much coarser)
//   dirBCoarse  left at user default (rotation-scale differs from position)
//
// Fine values are NOT set here — they are derived from coarse + numLevels
// at GPU upload time via deriveFine().
// ---------------------------------------------------------------------------
void VisCache::autoTuneCellSizes()
{
    static constexpr float kCoarseScale = 8.f;

    if (!mpScene) return;

    const auto& bounds = mpScene->getSceneBounds();
    float3 extent = bounds.extent();
    float sceneDiameter = std::max({extent.x, extent.y, extent.z});
    if (sceneDiameter <= 0.f) return;

    float coarse = sceneDiameter / kCoarseScale;

    mParams.posACoarse = coarse;
    mParams.posBCoarse = coarse * 2.f;
    mParams.distBCoarse = coarse * 8.f;
    // dirBCoarse stays at user default (mParams.dirBCoarse)
}

// ---------------------------------------------------------------------------
void VisCache::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    if (mParams.autoTuneCells && mpScene)
    {
        const auto& bounds = mpScene->getSceneBounds();
        float3 ext = bounds.extent();
        float sceneDiam = std::max({ext.x, ext.y, ext.z});
        autoTuneCellSizes();
        logInfo("[VisCache] Scene: diameter={:.2f} extent=({:.2f}, {:.2f}, {:.2f})",
                sceneDiam, ext.x, ext.y, ext.z);
        logInfo("[VisCache] Auto-tuned: posACoarse={:.4f} posBCoarse={:.4f} distBCoarse={:.4f} dirBCoarse={:.1f} (numLevels={})",
                mParams.posACoarse, mParams.posBCoarse, mParams.distBCoarse, mParams.dirBCoarse, mParams.numLevels);
    }
    allocateBuffers();
}

// ---------------------------------------------------------------------------
void VisCache::execute(RenderContext* pCtx, const RenderData& renderData)
{
    // ----------------------------------------------------------------
    // Upload GPU params and expose to downstream passes via dictionary.
    // Consumer binding is just two lines:
    //   rootVar["gVHFTable"]      = dict["vhfTable"];
    //   rootVar["VisCacheParams"] = dict["vhfParamsCB"];
    // ----------------------------------------------------------------
    // Parameter validation — clamp to safe ranges before GPU upload.
    mParams.numLevels     = std::max(1u, mParams.numLevels);
    mParams.bootThreshold   = std::clamp(mParams.bootThreshold, 1u, 0xFFFFu);

    // §9.4 WS-reservoir buffer: lazy (re)allocate to follow runtime toggle/capacity changes.
    {
        uint32_t wsCap = 1u;
        while (wsCap < std::max(1u, mParams.wsReservoirCapacity)) wsCap <<= 1;
        mParams.wsReservoirCapacity = wsCap;
        const bool needs = mParams.enableWSReservoirs && (!mpWSReservoirs || mWSReservoirCapacityCommitted != wsCap);
        if (needs)
        {
            mpWSReservoirs = mpDevice->createStructuredBuffer(
                kWSReservoirSize, wsCap,
                ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
                MemoryType::DeviceLocal, nullptr, /*createCounter=*/false);
            mpWSReservoirs->setName("VHF_WSReservoirs");
            mWSReservoirCapacityCommitted = wsCap;
            // Zero-init so fingerprint=0 (empty sentinel) holds across all slots.
            pCtx->clearUAV(mpWSReservoirs->getUAV().get(), uint4(0u));
        }
        else if (!mParams.enableWSReservoirs && mpWSReservoirs)
        {
            mpWSReservoirs = nullptr;
            mWSReservoirCapacityCommitted = 0u;
        }
    }
    mParams.matureThreshold = std::clamp(mParams.matureThreshold, mParams.bootThreshold, 0xFFFFu);
    if (mParams.varThreshold   <= 0.f) mParams.varThreshold   = 0.01f;
    if (mParams.posACoarse    <= 0.f) mParams.posACoarse    = 1.0f;
    if (mParams.posBCoarse    <= 0.f) mParams.posBCoarse    = 1.0f;
    if (mParams.dirBCoarse <= 0.f) mParams.dirBCoarse = 1.0f;
    if (mParams.distBCoarse    <= 0.f) mParams.distBCoarse    = 1.0f;
    if (mParams.normalACoarse  <= 0.f) mParams.normalACoarse  = 60.0f;
    if (mParams.pMin           <= 0.f) mParams.pMin           = 0.01f;

    // Scene-scale mode: treat user-supplied posA/posB/distB values as fractions
    // of a Cornell-box reference (average axis = 2 units). On Cornell, scale=1
    // so sizes are identical to the old absolute interpretation. On larger
    // scenes (Bistro, Sponza) cells grow proportionally so cell-count stays in
    // the same ballpark. Average axis (not longest) so a tall-thin scene like
    // a narrow hallway doesn't inflate cells beyond what its bulk dimension
    // warrants. Angular (dirB) and normal cells are unitless — never scaled.
    // autoTuneCells produces already-scaled values and overrides this.
    static constexpr float kCornellRefAxis = 2.0f;
    float sceneScale = 1.f;
    if (mParams.quantSceneScale && !mParams.autoTuneCells && mpScene)
    {
        float3 ext = mpScene->getSceneBounds().extent();
        float avgAxis = (ext.x + ext.y + ext.z) * (1.f / 3.f);
        if (avgAxis > 0.f) sceneScale = avgAxis / kCornellRefAxis;
    }
    const float posACoarseScaled = mParams.posACoarse  * sceneScale;
    const float posBCoarseScaled = mParams.posBCoarse  * sceneScale;
    const float distBCoarseScaled = mParams.distBCoarse * sceneScale;

    // Derive fine cell size from a constant per-level step factor (1.25 →
    // 25% smaller per level, the lower bound on cascade granularity user
    // wants — finer would create near-identical neighboring cells with
    // independent fingerprints, fragmenting samples). Upper bound 3.0 is
    // for sanity (larger jump would skip useful intermediate cell sizes).
    //
    // fine = coarse / 1.25^(N-1).
    //   N=16  → fine = coarse / 35       (4.5 bits of refinement)
    //   N=32  → fine = coarse / 1057     (10 bits — old default)
    //   N=64  → fine = coarse / 1.12e6   (20 bits — extra zoom headroom)
    //
    // Levels above N are clamped at fine; the analytical entry uses
    // ceil(log(target/coarse)/log(0.8) · (N-1)/(N-1)) = lvl directly, so
    // raw level number maps to a cell-size invariant of N (level 5 always
    // means cell ≈ coarse * 0.8^5 regardless of N).
    static constexpr float kStepFactor = 0.8f;  // = 1/1.25 per level
    // B-side ramp scale: how aggressively B-dimensions cascade vs A.
    // 1.0 = same as A (deepest level reaches stepFactor^(N-1) = 1/1200 at N=32).
    // 0.5 = half-rate; B's deepest level only reaches stepFactor^((N-1)/2) = 1/35.
    // Less-aggressive B avoids over-fragmenting light/direction discrimination
    // at deep cascade levels (where A needs sub-pixel posA but B doesn't need
    // sub-arcminute direction or sub-mm light position).
    static constexpr float kBRampScale = 0.5f;
    // Soft clamp: power-mean of fine_raw and floor — fine_raw >> floor stays
    // unclamped; fine_raw << floor smoothly approaches floor without abrupt
    // transition. k controls softness; k=4 is moderate.
    auto softMax = [](float a, float b, float k = 4.0f) -> float {
        if (b <= 0.0f) return a;
        float ak = std::pow(std::abs(a), k);
        float bk = std::pow(b, k);
        return std::pow(ak + bk, 1.0f / k);
    };
    auto deriveFine = [&](float coarse, uint32_t N, float floor = 0.0f, float rampScale = 1.0f) -> float {
        if (N <= 1u) return coarse;
        float effN = std::max(1.0f, float(N - 1) * rampScale);
        float fine = coarse * std::pow(kStepFactor, effN);
        return (floor > 0.0f) ? softMax(fine, floor) : fine;
    };
    // Per-dimension floors (soft-clamps deriveFine to sensible minima):
    //   dirB  : 1° — sub-degree direction cells fragment cache without
    //           benefit. Applies to BOTH dir+dist mode AND pos×pos env-
    //           routing (vhfQuantizeDirection in VisCache.slang) used for
    //           env+sun rays at infinity.
    //   distB : 0.05 world units (sceneScale-aware) — sub-cm light-distance
    //           resolution doesn't add cache discrimination.
    //   posB  : 0.001 world units (sceneScale-aware) — sub-mm light position
    //           resolution over-fragments without separating distinct lights.
    constexpr float kDirBFineFloor  = 1.0f;     // degrees
    constexpr float kDistBFineFloor = 0.05f;    // world units (sceneScale-aware)
    constexpr float kPosBFineFloor  = 0.001f;   // world units (sceneScale-aware)

    GPUParams gpu = {};
    gpu.tableCapacity  = mParams.tableCapacity;
    gpu.bootThreshold    = mParams.bootThreshold;
    gpu.matureThreshold  = mParams.matureThreshold;
    gpu.varThreshold     = mParams.varThreshold;
    gpu.pMin           = mParams.pMin;
    gpu.fireflyBudget  = mParams.fireflyBudget;
    gpu.numLevels      = mParams.numLevels;
    gpu.flags          = (mParams.enableVisCacheAdaptivePMin ? 1u : 0u)
                       | (mParams.enableVisCacheNormalAddr ? 2u : 0u)
                       | (mParams.enableVisCacheBootstrapBreak ? 4u : 0u)
                       | (mParams.enableVisCacheParentPreinit ? 8u : 0u);
    gpu.bootThresholdFactorFootprintPx = mParams.bootThresholdFactorFootprintPx;
    gpu.forceDescendFootprintPx = mParams.forceDescendFootprintPx;
    gpu.cascadeWindowForward    = mParams.cascadeWindowForward;
    gpu.stderrThreshold = mParams.stderrThreshold;
    gpu.enableHierarchicalConsistency = mParams.enableHierarchicalConsistency ? 1u : 0u;
    gpu.hierarchicalMuTolerance = mParams.hierarchicalMuTolerance;
    gpu.accelDecayDisagreeThresh = mParams.accelDecayDisagreeThresh;
    gpu.bootThresholdFine = mParams.bootThresholdFine;
    gpu.jitterFilter   = mParams.jitterFilter;
    gpu.jitterCell     = mParams.jitterCell;
    gpu.posACoarse    = posACoarseScaled;
    gpu.posAFine      = (mParams.numLevels > 1) ? deriveFine(posACoarseScaled, mParams.numLevels) : posACoarseScaled;
    gpu.posBCoarse    = posBCoarseScaled;
    // posBFine: keep full ramp (no kBRampScale) — Sponza/multi-light scenes
    // need posB to descend as aggressively as posA so adjacent lights remain
    // separable at deep cascade levels. Just clamp via floor.
    gpu.posBFine      = (mParams.numLevels > 1) ? deriveFine(posBCoarseScaled, mParams.numLevels, kPosBFineFloor * sceneScale) : posBCoarseScaled;
    gpu.dirBCoarse = mParams.dirBCoarse;
    // dir/dist: less-aggressive ramp — sub-degree direction and sub-mm
    // distance over-fragment without separating distinct lights.
    gpu.dirBFine   = (mParams.numLevels > 1) ? deriveFine(mParams.dirBCoarse, mParams.numLevels, kDirBFineFloor, kBRampScale) : mParams.dirBCoarse;
    gpu.distBCoarse    = distBCoarseScaled;
    gpu.distBFine      = (mParams.numLevels > 1) ? deriveFine(distBCoarseScaled, mParams.numLevels, kDistBFineFloor * sceneScale, kBRampScale) : distBCoarseScaled;
    gpu.normalACoarse  = mParams.normalACoarse;
    gpu.normalAFine    = (mParams.numLevels > 1) ? deriveFine(mParams.normalACoarse, mParams.numLevels) : mParams.normalACoarse;
    gpu.diagAccumWindow = mParams.diagAccumWindow;
    gpu.frameCount      = mFrameCount;
    gpu.spp             = std::max(1u, mParams.spp);

    // Camera footprint estimation: pixel world-space size at unit depth.
    // Falcor's |cameraU| = focalDistance * tan(fovY/2) * aspectRatio (Camera.cpp:180),
    // so divide by focalDistance to get the per-pixel angular extent at unit depth:
    // pixelSize1 = 2 * tan(fovY/2) * aspect / frameDim.x
    //            = 2 * |cameraU| / focalDistance / frameDim.x
    if (mpScene && mpScene->getCamera())
    {
        const auto& cam = mpScene->getCamera()->getData();
        float3 posW = cam.posW;
        gpu.cameraPosW[0] = posW.x;
        gpu.cameraPosW[1] = posW.y;
        gpu.cameraPosW[2] = posW.z;
        float cameraULen = length(cam.cameraU);
        uint32_t dimX = renderData.getDefaultTextureDims().x;
        uint32_t frameDimX = dimX > 0u ? dimX : 1u;
        float focalDist = std::max(cam.focalDistance, 1e-3f);
        gpu.pixelSize1 = 2.f * cameraULen / focalDist / float(frameDimX);
    }
    else
    {
        gpu.cameraPosW[0] = gpu.cameraPosW[1] = gpu.cameraPosW[2] = 0.f;
        gpu.pixelSize1 = 0.001f;  // Safe fallback
    }
    gpu.subframeN        = std::max(1u, mParams.subframeN);
    gpu.warmupSlotsFirst = mParams.warmupSlotsFirst;
    gpu.warmupSlotsRun   = mParams.warmupSlotsRun;

    // §9.4 WS-reservoir params. Capacity is rounded up to next pow2 for bitmask indexing.
    uint32_t wsCap = 1u;
    while (wsCap < std::max(1u, mParams.wsReservoirCapacity)) wsCap <<= 1;
    mParams.wsReservoirCapacity = wsCap;
    gpu.wsEnable             = mParams.enableWSReservoirs ? 1u : 0u;
    gpu.wsLevelOffset        = mParams.wsLevelOffset;
    gpu.wsCapacity           = wsCap;
    gpu.wsMCap               = mParams.wsMCap;
    gpu.wsSpatialNeighbours  = std::min(4u, mParams.wsSpatialNeighbours);
    gpu.wsLightMuMin         = mParams.wsLightMuMin;

    std::memcpy(mpParamsBuffer->map(), &gpu, sizeof(gpu));
    mpParamsBuffer->unmap();

    // Log params on first frame for debugging.
    if (mFrameCount == 0u)
    {
        logInfo("[VisCache] tableCapacity={} bootThreshold={} matureThreshold={} varThreshold={:.3f} pMin={:.3f} fireflyBudget={:.3f}",
                mParams.tableCapacity, mParams.bootThreshold, mParams.matureThreshold, mParams.varThreshold, mParams.pMin, mParams.fireflyBudget);
        if (mParams.quantSceneScale && !mParams.autoTuneCells)
            logInfo("[VisCache] quantSceneScale={:.3f} (Cornell ref = avgAxis/2)", sceneScale);
        logInfo("[VisCache] posA: coarse={:.4f} fine={:.4f} numLevels={} pixelSize1={:.6f} forceFd={} cascWindow={}",
                gpu.posACoarse, gpu.posAFine, gpu.numLevels, gpu.pixelSize1, gpu.forceDescendFootprintPx, gpu.cascadeWindowForward);
        logInfo("[VisCache] posB: coarse={:.4f} fine={:.4f}", gpu.posBCoarse, gpu.posBFine);
        logInfo("[VisCache] dirB: coarse={:.1f}{} fine={:.1f}{}", gpu.dirBCoarse, "\xC2\xB0", gpu.dirBFine, "\xC2\xB0");
        logInfo("[VisCache] distB: coarse={:.4f} fine={:.4f}", gpu.distBCoarse, gpu.distBFine);
        logInfo("[VisCache] visCheck={} lightSel={} warpRed={} varGate={} decay={} pressEvict={} jitterFilter={:.3f} jitterCell={:.3f} adaptPMin={} dirDistAddr={} bootThresholdFactorFootprintPx={:.3f} bootstrapBreak={} parentPreinit={}",
                mParams.enableVisCacheVisibilityCheck, mParams.enableVisCacheLightSelection,
                mParams.enableVisCacheWarpReduction, mParams.enableVisCacheVarianceGate,
                mParams.enableVisCacheDecay, mParams.enableVisCachePressureEvict,
                mParams.jitterFilter, mParams.jitterCell, mParams.enableVisCacheAdaptivePMin,
                mParams.enableVisCacheDirDistAddr, mParams.bootThresholdFactorFootprintPx,
                mParams.enableVisCacheBootstrapBreak, mParams.enableVisCacheParentPreinit);
        logInfo("[VisCache] subframeN={} warmupFirst={} warmupRun={}",
                gpu.subframeN, mParams.warmupSlotsFirst, mParams.warmupSlotsRun);
        logInfo("[VisCache] diagnostics={} diagMode={}",
                mEnableDiagnostics, uint32_t(mDiagMode));
    }

    // Clear hash table to empty-slot sentinel (fingerprint=0) on first use
    // or after reallocation. GPU memory is NOT zeroed on allocation.
    // TODO: Clear hash table to empty sentinel. clearUAV on StructuredBuffer
    // may cause TDR on some drivers — needs investigation.
    // if (mClearHashTable)
    // {
    //     pCtx->clearUAV(mpHashTable->getUAV().get(), uint4(0u));
    //     mClearHashTable = false;
    // }

    auto& dict = renderData.getDictionary();
    dict["vhfTable"]       = mpHashTable;
    dict["vhfParamsCB"]    = mpParamsBuffer;  // kept for backward compat; prefer per-member binding below

    // Per-member cbuffer values — downstream passes bind these individually
    // because Falcor 8 ParameterBlock::setBuffer() doesn't support cbuffer binding.
    dict["vhfParam_tableCapacity"]  = mParams.tableCapacity;
    dict["vhfParam_bootThreshold"]    = mParams.bootThreshold;
    dict["vhfParam_matureThreshold"] = mParams.matureThreshold;
    dict["vhfParam_varThreshold"]    = mParams.varThreshold;
    dict["vhfParam_pMin"]           = mParams.pMin;
    dict["vhfParam_fireflyBudget"]  = mParams.fireflyBudget;
    dict["vhfParam_numLevels"]      = mParams.numLevels;
    dict["vhfParam_jitterFilter"]   = mParams.jitterFilter;
    dict["vhfParam_jitterCell"]     = mParams.jitterCell;
    dict["vhfParam_flags"]         = gpu.flags;
    dict["vhfParam_posACoarse"]    = gpu.posACoarse;
    dict["vhfParam_posAFine"]      = gpu.posAFine;
    dict["vhfParam_posBCoarse"]    = gpu.posBCoarse;
    dict["vhfParam_posBFine"]      = gpu.posBFine;
    dict["vhfParam_dirBCoarse"] = gpu.dirBCoarse;
    dict["vhfParam_dirBFine"]   = gpu.dirBFine;
    dict["vhfParam_distBCoarse"]    = gpu.distBCoarse;
    dict["vhfParam_distBFine"]      = gpu.distBFine;
    dict["vhfParam_normalACoarse"]  = gpu.normalACoarse;
    dict["vhfParam_normalAFine"]    = gpu.normalAFine;
    dict["vhfParam_diagAccumWindow"] = mParams.diagAccumWindow;

    // Feature + ablation toggles — downstream passes read these
    dict["vhfEnableVisibilityCheck"] = mParams.enableVisCacheVisibilityCheck;
    dict["vhfEnableLightSelection"]  = mParams.enableVisCacheLightSelection;
    dict["vhfEnableWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    dict["vhfEnableVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    dict["vhfEnableDecay"]           = mParams.enableVisCacheDecay;
    dict["vhfEnablePressureEvict"]   = mParams.enableVisCachePressureEvict;
    dict["vhfJitterFilter"]          = mParams.jitterFilter;
    dict["vhfJitterCell"]            = mParams.jitterCell;
    dict["vhfEnableDirDistAddr"]     = mParams.enableVisCacheDirDistAddr;
    dict["vhfEnableBootstrapBreak"]  = mParams.enableVisCacheBootstrapBreak;
    dict["vhfEnableParentPreinit"]   = mParams.enableVisCacheParentPreinit;
    dict["vhfParam_bootThresholdFactorFootprintPx"]  = mParams.bootThresholdFactorFootprintPx;
    dict["vhfParam_forceDescendFootprintPx"]         = mParams.forceDescendFootprintPx;
    dict["vhfParam_cascadeWindowForward"]            = mParams.cascadeWindowForward;
    dict["vhfParam_stderrThreshold"]                 = mParams.stderrThreshold;
    dict["vhfParam_enableHierarchicalConsistency"]   = mParams.enableHierarchicalConsistency ? 1u : 0u;
    dict["vhfParam_hierarchicalMuTolerance"]         = mParams.hierarchicalMuTolerance;
    dict["vhfParam_accelDecayDisagreeThresh"]        = mParams.accelDecayDisagreeThresh;
    dict["vhfParam_bootThresholdFine"]               = mParams.bootThresholdFine;
    dict["vhfParam_frameCount"]                      = mFrameCount;
    dict["vhfParam_spp"]                             = std::max(1u, mParams.spp);
    dict["vhfParam_cameraPosX"]                      = gpu.cameraPosW[0];
    dict["vhfParam_cameraPosY"]                      = gpu.cameraPosW[1];
    dict["vhfParam_cameraPosZ"]                      = gpu.cameraPosW[2];
    dict["vhfParam_pixelSize1"]                      = gpu.pixelSize1;
    dict["vhfParam_subframeN"]                       = std::max(1u, mParams.subframeN);
    dict["vhfParam_warmupFirst"]                     = mParams.warmupSlotsFirst;
    dict["vhfParam_warmupRun"]                       = mParams.warmupSlotsRun;
    dict["vhfSubframeN"]        = std::max(1u, mParams.subframeN);
    dict["vhfWarmupSlotsFirst"] = mParams.warmupSlotsFirst;
    dict["vhfWarmupSlotsRun"]   = mParams.warmupSlotsRun;

    // §9.4 WS-reservoir export — buffer + per-field cbuffer values for downstream binding.
    dict["wsReservoirBuffer"]        = mpWSReservoirs;
    dict["vhfEnableWSReservoirs"]    = mParams.enableWSReservoirs;
    dict["vhfParam_wsEnable"]        = mParams.enableWSReservoirs ? 1u : 0u;
    dict["vhfParam_wsLevelOffset"]   = mParams.wsLevelOffset;
    dict["vhfParam_wsCapacity"]      = mParams.wsReservoirCapacity;
    dict["vhfParam_wsMCap"]          = mParams.wsMCap;
    dict["vhfParam_wsSpatialNeighbours"] = std::min(4u, mParams.wsSpatialNeighbours);
    dict["vhfParam_wsLightMuMin"]    = mParams.wsLightMuMin;

    // Stats (readback with ~4-frame delay, updated every 16 frames)
    dict["vhfHitRate"]      = mStats.hitRate;
    dict["vhfRaySavings"]   = mStats.raySavings;
    dict["vhfEvictRate"]    = mStats.evictRate;

    // ----------------------------------------------------------------
    // Diagnostic heatmap textures — allocate/expose, then clear.
    // VisCache runs BEFORE downstream passes, so we expose textures
    // via dictionary and downstream passes write directly to them.
    // ----------------------------------------------------------------
    {
        // Helper to create textures
        auto makeRGBA = [&](const char* name) {
            auto t = mpDevice->createTexture2D(
                mFrameDims.x, mFrameDims.y, ResourceFormat::RGBA32Float, 1, 1,
                nullptr, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
            t->setName(name);
            return t;
        };
        auto makeR32U = [&](const char* name) {
            auto t = mpDevice->createTexture2D(
                mFrameDims.x, mFrameDims.y, ResourceFormat::R32Uint, 1, 1,
                nullptr, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
            t->setName(name);
            return t;
        };

        // --- Per-frame diag textures (prefer graph-allocated, fallback to internal) ---
        ref<Texture> accumMeanVarMatCountTex, frameMeanVarMatSamplesRawTex, frameLevelProbesSamplesColdTex, frameHashTex;
        ref<Texture> accumRaysNoiseErrorColdTex;

        if (auto p = renderData[kOutputAccumMeanVarMatCount])  accumMeanVarMatCountTex  = p->asTexture();
        if (auto p = renderData[kOutputFrameMeanVarMatSamplesRaw])  frameMeanVarMatSamplesRawTex  = p->asTexture();
        if (auto p = renderData[kOutputFrameLevelProbesSamplesCold])  frameLevelProbesSamplesColdTex  = p->asTexture();
        if (auto p = renderData[kOutputFrameHashAHashBHashABRays])  frameHashTex  = p->asTexture();
        if (auto p = renderData[kOutputAccumRaysNoiseErrorCold])  accumRaysNoiseErrorColdTex  = p->asTexture();

        bool needInternal = mEnableDiagnostics && mFrameDims.x > 0 && mFrameDims.y > 0;
        if (needInternal)
        {
            bool needRealloc = !mpAccumMeanVarMatCountTex || mpAccumMeanVarMatCountTex->getWidth() != mFrameDims.x
                                                     || mpAccumMeanVarMatCountTex->getHeight() != mFrameDims.y;
            if (needRealloc)
            {
                mpAccumMeanVarMatCountTex   = makeRGBA("VC_AccumMeanVarMatCount");
                mpFrameMeanVarMatSamplesRawTex   = makeRGBA("VC_FrameMeanVarMatSamplesRaw");
                mpFrameLevelProbesSamplesColdTex   = makeRGBA("VC_FrameLevelProbesSamplesCold");
                mpFrameHashAHashBHashABRaysTex   = makeRGBA("VC_FrameHashAHashBHashABRays");
                mpAccumRaysNoiseErrorColdTex   = makeRGBA("VC_AccumRaysNoiseErrorCold");
                mResetAccum = true;  // accum textures need realloc too

                // Clear snapshot textures on allocation so unwritten pixels
                // (background, specular) start at cold/zero instead of GPU garbage.
                // FrameLevelProbesSamplesCold.A=1 marks unqueried pixels as coldmiss.
                pCtx->clearUAV(mpFrameMeanVarMatSamplesRawTex->getUAV().get(), float4(0.f));
                pCtx->clearUAV(mpFrameLevelProbesSamplesColdTex->getUAV().get(), float4(0.f, 0.f, 0.f, 1.f));
                pCtx->clearUAV(mpFrameHashAHashBHashABRaysTex->getUAV().get(), float4(0.f));
            }
            if (!accumMeanVarMatCountTex)  accumMeanVarMatCountTex  = mpAccumMeanVarMatCountTex;
            if (!frameMeanVarMatSamplesRawTex)  frameMeanVarMatSamplesRawTex  = mpFrameMeanVarMatSamplesRawTex;
            if (!frameLevelProbesSamplesColdTex)  frameLevelProbesSamplesColdTex  = mpFrameLevelProbesSamplesColdTex;
            if (!frameHashTex)  frameHashTex  = mpFrameHashAHashBHashABRaysTex;
            if (!accumRaysNoiseErrorColdTex)  accumRaysNoiseErrorColdTex  = mpAccumRaysNoiseErrorColdTex;
        }

        // --- Accumulated textures (persistent, only cleared on reset) ---
        if (mFrameDims.x > 0 && mFrameDims.y > 0)
        {
            bool needAccumRealloc = !mpAccumSaved
                || mpAccumSaved->getWidth() != mFrameDims.x
                || mpAccumSaved->getHeight() != mFrameDims.y;
            if (needAccumRealloc)
            {
                mpAccumSaved = makeR32U("VHF_AccumSaved");
                mpAccumTotal = makeR32U("VHF_AccumTotal");
                mResetAccum = true;
            }
            if (mResetAccum)
            {
                pCtx->clearUAV(mpAccumSaved->getUAV().get(), uint4(0u));
                pCtx->clearUAV(mpAccumTotal->getUAV().get(), uint4(0u));
                // Clear accumulated diagnostic textures so the
                // averaging window starts fresh.
                if (accumMeanVarMatCountTex)
                    pCtx->clearUAV(accumMeanVarMatCountTex->getUAV().get(), float4(0.f));
                if (accumRaysNoiseErrorColdTex)
                    pCtx->clearUAV(accumRaysNoiseErrorColdTex->getUAV().get(), float4(0.f));
                // Clear snapshot textures too so stale data from the previous
                // warmup phase doesn't leak into the averaging window.
                if (frameMeanVarMatSamplesRawTex)
                    pCtx->clearUAV(frameMeanVarMatSamplesRawTex->getUAV().get(), float4(0.f));
                if (frameLevelProbesSamplesColdTex)
                    pCtx->clearUAV(frameLevelProbesSamplesColdTex->getUAV().get(), float4(0.f, 0.f, 0.f, 1.f));
                if (frameHashTex)
                    pCtx->clearUAV(frameHashTex->getUAV().get(), float4(0.f));
                mResetAccum = false;
            }
            dict["vhfAccumSaved"] = mpAccumSaved;
            dict["vhfAccumTotal"] = mpAccumTotal;
        }

        // Per-frame clear: frame textures must be zeroed every frame so the
        // firstBounce detection (hash R+G==0) works and stale data doesn't persist.
        if (frameMeanVarMatSamplesRawTex)
            pCtx->clearUAV(frameMeanVarMatSamplesRawTex->getUAV().get(), float4(0.f));
        if (frameLevelProbesSamplesColdTex)
            pCtx->clearUAV(frameLevelProbesSamplesColdTex->getUAV().get(), float4(0.f, 0.f, 0.f, 1.f));
        if (frameHashTex)
            pCtx->clearUAV(frameHashTex->getUAV().get(), float4(0.f));

        auto expose = [&](ref<Texture>& tex, const char* key) {
            if (tex) dict[key] = tex;
        };
        // Per-frame snapshots
        expose(frameMeanVarMatSamplesRawTex,  "vhfFrameMeanVarMatSamplesRaw");
        expose(frameLevelProbesSamplesColdTex,  "vhfFrameLevelProbesSamplesCold");
        expose(frameHashTex,  "vhfFrameHashAHashBHashABRays");
        // Accumulated (NOT cleared per frame — running averages)
        expose(accumMeanVarMatCountTex,  "vhfAccumMeanVarMatCount");
        expose(accumRaysNoiseErrorColdTex,  "vhfAccumRaysNoiseErrorCold");

        dict["vhfDiagEnabled"] = (accumMeanVarMatCountTex != nullptr);
        dict["vhfDiagMode"]    = uint32_t(mDiagMode);
    }

    // ----------------------------------------------------------------
    // Background decay sweep (1/decayPeriod of table per frame)
    // ----------------------------------------------------------------
    if (mParams.enableVisCacheDecay && mParams.decayPeriod > 0)
    {
        runDecayPass(pCtx);
    }

    // ----------------------------------------------------------------
    // Readback stats every 16 frames; auto-tune decayPeriod
    // ----------------------------------------------------------------
    if (mFrameCount % 16u == 0u && mpStagingBuffer)
    {
        readbackStats(pCtx);
        // Primary decay rate is the user's `decayPeriod` setting; PI auto-tune
        // is opt-in secondary adjustment under load. When off (default), the
        // user's setting is canonical and persists across frames.
        if (mParams.enableDecayAutoTune)
            autoTuneDecayPeriod();
    }

    // Subframe gate: advance logical frameCount only after a full Bayer cycle (N²).
    const uint32_t kSubframeCount = std::max(1u, mParams.subframeN) * std::max(1u, mParams.subframeN);
    mSubframeIdx++;
    if (mSubframeIdx >= kSubframeCount)
    {
        mSubframeIdx = 0;
        mFrameCount++;
    }
}

// ---------------------------------------------------------------------------
// runDecayPass: dispatch the VisCacheDecay.cs.slang compute shader.
//
// Each frame processes one slice of the hash table (stride = capacity/decayPeriod).
// The offset advances by stride each frame, so the full table is swept once
// every decayPeriod frames. See VisCacheDecay.cs.slang for the per-entry logic.
// ---------------------------------------------------------------------------
void VisCache::runDecayPass(RenderContext* pCtx)
{
    uint32_t stride = std::max(1u, mParams.tableCapacity / mParams.decayPeriod);
    uint32_t offset = (mFrameCount % mParams.decayPeriod) * stride;

    auto vars = mpDecayPass->getRootVar();
    vars["DecayCB"]["gDecayOffset"] = offset;
    vars["DecayCB"]["gDecayStride"] = stride;
    vars["gVHFTable"] = mpHashTable;
    // Derive fine values from coarse + numLevels (same formula as execute()).
    static constexpr float kMaxRatio = 4.f;
    auto deriveFine = [&](float coarse, uint32_t N) -> float {
        return coarse / std::pow(kMaxRatio, std::sqrt(float(N - 1)));
    };
    uint32_t N = std::max(1u, mParams.numLevels);

    vars["VisCacheParams"]["gTableCapacity"]  = mParams.tableCapacity;
    vars["VisCacheParams"]["gBootThreshold"]    = mParams.bootThreshold;
    vars["VisCacheParams"]["gMatureThreshold"] = mParams.matureThreshold;
    vars["VisCacheParams"]["gVarThreshold"]    = mParams.varThreshold;
    vars["VisCacheParams"]["gPMin"]           = mParams.pMin;
    vars["VisCacheParams"]["gFireflyBudget"]  = mParams.fireflyBudget;
    vars["VisCacheParams"]["gNumLevels"]      = N;
    vars["VisCacheParams"]["gFlags"]          = (mParams.enableVisCacheAdaptivePMin ? 1u : 0u)
                                                | (mParams.enableVisCacheNormalAddr ? 2u : 0u)
                                                | (mParams.enableVisCacheBootstrapBreak ? 4u : 0u)
                                                | (mParams.enableVisCacheParentPreinit ? 8u : 0u);
    vars["VisCacheParams"]["gPosACoarse"]    = mParams.posACoarse;
    vars["VisCacheParams"]["gPosAFine"]      = (N > 1) ? deriveFine(mParams.posACoarse, N) : mParams.posACoarse;
    vars["VisCacheParams"]["gPosBCoarse"]    = mParams.posBCoarse;
    vars["VisCacheParams"]["gPosBFine"]      = (N > 1) ? deriveFine(mParams.posBCoarse, N) : mParams.posBCoarse;
    vars["VisCacheParams"]["gDirBCoarse"] = mParams.dirBCoarse;
    vars["VisCacheParams"]["gDirBFine"]   = (N > 1) ? deriveFine(mParams.dirBCoarse, N) : mParams.dirBCoarse;
    vars["VisCacheParams"]["gDistBCoarse"]    = mParams.distBCoarse;
    vars["VisCacheParams"]["gDistBFine"]      = (N > 1) ? deriveFine(mParams.distBCoarse, N) : mParams.distBCoarse;
    vars["VisCacheParams"]["gNormalACoarse"]  = mParams.normalACoarse;
    vars["VisCacheParams"]["gNormalAFine"]    = (N > 1) ? deriveFine(mParams.normalACoarse, N) : mParams.normalACoarse;
    vars["VisCacheParams"]["gDiagAccumWindow"] = mParams.diagAccumWindow;

    mpDecayPass->execute(pCtx, stride, 1u, 1u);
}

// ---------------------------------------------------------------------------
// readbackStats: copy GPU atomic counters to CPU for UI display and PI controller.
//
// Uses a staging buffer with readback memory type. The ~4 frame latency from
// GPU→CPU copy is acceptable for UI display and the slow PI controller loop.
// After reading, counters are cleared to zero for the next accumulation period.
// ---------------------------------------------------------------------------
void VisCache::readbackStats(RenderContext* pCtx)
{
    // Copy GPU counters → staging → CPU (4-frame latency is acceptable)
    pCtx->copyResource(mpStagingBuffer.get(), mpStatsBuffer.get());
    pCtx->submit(false);

    const uint32_t* data =
        reinterpret_cast<const uint32_t*>(mpStagingBuffer->map());
    if (!data) return;

    uint32_t inserts    = data[0];
    uint32_t evictions  = data[1];
    uint32_t misses     = data[2];
    uint32_t queries    = inserts + misses;

    mStats.hitRate    = queries > 0 ? float(queries - misses) / float(queries) : 0.f;
    mStats.raySavings = queries > 0 ? float(queries - inserts) / float(queries) : 0.f;
    mStats.evictRate  = inserts > 0 ? float(evictions) / float(inserts) : 0.f;

    mpStagingBuffer->unmap();

    // Reset GPU counters
    pCtx->clearUAV(mpStatsBuffer->getUAV().get(), uint4(0u));
}

// ---------------------------------------------------------------------------
// autoTuneDecayPeriod: PI controller adjusts decay speed based on load pressure.
//
// When eviction rate exceeds the target (table is under pressure), decay speeds
// up to free stale entries. When pressure is low, decay slows down to preserve
// cache history (better visibility estimates from more samples).
//
// The controller is one-sided: it never slows decay past decayPeriodMax, and
// never goes below 15 frames (hard lower bound for aggressive decay scenes).
//
// Quality parameters (varThreshold, pMin) are NEVER auto-tuned — this ensures
// the user retains full control over the quality/performance tradeoff.
// ---------------------------------------------------------------------------
void VisCache::autoTuneDecayPeriod()
{
    // PI controller: target eviction/insert ratio = mTargetLoadPressure
    // One-sided: only speeds up decay under load, never slows past user max.
    float error     = mStats.evictRate - mTargetLoadPressure;
    mPIIntegral    += error * 0.1f;                        // I term
    float output    = error * 2.0f + mPIIntegral;          // P+I

    int32_t newPeriod = int32_t(mParams.decayPeriod) - int32_t(output * 10.f);
    newPeriod = std::clamp(newPeriod, 15,
                           int32_t(mParams.decayPeriodMax));
    mParams.decayPeriod = uint32_t(newPeriod);
}

// ---------------------------------------------------------------------------
void VisCache::renderUI(Gui::Widgets& widget)
{
    widget.text(fmt::format("Hit rate:        {:.1f}%", mStats.hitRate * 100.f));
    widget.text(fmt::format("Ray savings:     {:.1f}%", mStats.raySavings * 100.f));
    widget.text(fmt::format("Eviction rate:   {:.2f}", mStats.evictRate));
    widget.text(fmt::format("Decay period:    {} frames (auto)", mParams.decayPeriod));
    widget.separator();

    widget.var("Use threshold",    mParams.bootThreshold,   1u, 0xFFFFu);
    widget.var("Mature threshold", mParams.matureThreshold, 1u, 0xFFFFu);
    widget.var("pMin",             mParams.pMin,           0.01f, 0.5f,  0.005f);
    widget.var("Var threshold",    mParams.varThreshold,   0.01f, 0.5f,  0.01f);
    widget.var("Firefly budget",   mParams.fireflyBudget,  0.001f, 1.0f, 0.005f);
    widget.separator();
    widget.var("Num LOD levels",   mParams.numLevels,      1u, 1024u);

    // Cell sizes (coarse only — fine auto-derived from coarse + numLevels)
    if (auto g = widget.group("Cell sizes"))
    {
        g.var("Pos A coarse",            mParams.posACoarse,    0.01f, 100.0f, 0.01f);
        g.var("Pos B coarse",            mParams.posBCoarse,    0.01f, 100.0f, 0.01f);
        g.var("Dir B coarse (deg)",      mParams.dirBCoarse, 1.0f, 360.0f, 1.0f);
        g.var("Dist B coarse",           mParams.distBCoarse,    0.01f, 100.0f, 0.1f);
        g.var("Diag accum window",       mParams.diagAccumWindow, 0u, 1024u);
    }

    widget.var("Decay period max", mParams.decayPeriodMax, 15u, 2000u);
    widget.separator();

    widget.checkbox("VisCache visibility check",       mParams.enableVisCacheVisibilityCheck);
    widget.checkbox("VisCache light selection (S11.1)", mParams.enableVisCacheLightSelection);
    widget.checkbox("VisCache warp reduction",         mParams.enableVisCacheWarpReduction);
    widget.separator();

    if (auto g = widget.group("§9.4 WS-ReSTIR DI", /*open=*/false))
    {
        g.checkbox("Enable WS reservoirs", mParams.enableWSReservoirs);
        g.var("wsLevelOffset (cells coarser than vis)", mParams.wsLevelOffset, 0u, 8u);
        g.var("wsReservoirCapacity (slots, pow2)", mParams.wsReservoirCapacity, 1u << 12, 1u << 24);
        g.var("wsMCap", mParams.wsMCap, 1.f, 200.f, 1.f);
        g.var("wsSpatialNeighbours", mParams.wsSpatialNeighbours, 0u, 4u);
        g.var("wsLightMuMin (ε floor)", mParams.wsLightMuMin, 0.f, 1.f, 0.01f);
    }
    widget.separator();

    // Ablation toggles
    if (auto g = widget.group("Ablation toggles", /*open=*/false))
    {
        g.checkbox("B: Variance-gated depth", mParams.enableVisCacheVarianceGate);
        g.checkbox("C: Warp reduction",       mParams.enableVisCacheWarpReduction);
        g.checkbox("D: Inline CAS decay",     mParams.enableVisCacheDecay);
        g.checkbox("E: Pressure eviction",    mParams.enableVisCachePressureEvict);
        g.var("F: jitterFilter (0=off)", mParams.jitterFilter, 0.f, 4.f, 0.05f);
        g.var("F: jitterCell (0=off)",   mParams.jitterCell,   0.f, 4.f, 0.05f);
        g.checkbox("§5: bootstrap-break", mParams.enableVisCacheBootstrapBreak);
        g.checkbox("§5: parent-preinit",  mParams.enableVisCacheParentPreinit);
        g.checkbox("G: Dir+dist addressing", mParams.enableVisCacheDirDistAddr);
        g.var("K: bootThresholdFactorFootprintPx (0=off)", mParams.bootThresholdFactorFootprintPx, 0.f, 8.f, 0.1f);
        g.var("forceDescend cellPx (0=off)", mParams.forceDescendFootprintPx, 0u, 1u << 16);
        g.var("stderrThreshold (0=off)", mParams.stderrThreshold, 0.f, 1.f, 0.01f);
        g.checkbox("Hierarchical consistency check", mParams.enableHierarchicalConsistency);
        g.var("hierarchical μ tolerance", mParams.hierarchicalMuTolerance, 0.f, 1.f, 0.05f);
        g.var("accelDecay |Δ| thresh (0=off)", mParams.accelDecayDisagreeThresh, 0.f, 1.f, 0.05f);
        g.var("bootThresholdFine (0=uniform)", mParams.bootThresholdFine, 0u, 256u);
        g.var("preinit ambiguity cutoff (0=always preinit)", mParams.preinitAmbiguityCutoff, 0.f, 0.5f, 0.05f);
        g.var("M: Subframe N (1 = off)",  mParams.subframeN,        1u, 8u);
        g.var("L: warmupSlots (frame 0)", mParams.warmupSlotsFirst, 0u, 64u);
        g.var("L: warmupSlots (running)", mParams.warmupSlotsRun,   0u, 64u);
    }

    widget.separator();

    static const Gui::DropdownList kHeatmapModes = {
        {uint32_t(DiagMode::Off),             "Off"},
        {uint32_t(DiagMode::CachedMu),        "Cached Mu (visibility)"},
        {uint32_t(DiagMode::Variance),        "Variance (uncertainty)"},
        {uint32_t(DiagMode::LODLevel),        "LOD Level"},
        {uint32_t(DiagMode::RaySaved),        "Ray Saved"},
    };
    widget.dropdown("Heatmap", kHeatmapModes, reinterpret_cast<uint32_t&>(mDiagMode));
    mEnableDiagnostics = (mDiagMode != DiagMode::Off);
}

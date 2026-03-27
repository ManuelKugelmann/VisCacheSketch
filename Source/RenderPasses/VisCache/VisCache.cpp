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
    if (props.has("tableCapacity"))  mParams.tableCapacity  = props["tableCapacity"];
    if (props.has("bootThreshold"))  mParams.bootThreshold  = props["bootThreshold"];
    if (props.has("varThreshold"))   mParams.varThreshold   = props["varThreshold"];
    if (props.has("pMin"))           mParams.pMin           = props["pMin"];
    if (props.has("fireflyBudget"))  mParams.fireflyBudget  = props["fireflyBudget"];
    if (props.has("numLevels"))      mParams.numLevels      = props["numLevels"];
    if (props.has("cellACoarse"))  { mParams.cellACoarse    = props["cellACoarse"];  mParams.autoTuneCells = false; }
    if (props.has("cellBCoarse"))    mParams.cellBCoarse    = props["cellBCoarse"];
    if (props.has("angularBCoarse")) mParams.angularBCoarse = props["angularBCoarse"];
    if (props.has("distBCoarse"))    mParams.distBCoarse    = props["distBCoarse"];
    if (props.has("normalBCoarse")) mParams.normalBCoarse  = props["normalBCoarse"];
    if (props.has("diagAccumWindow"))  mParams.diagAccumWindow  = props["diagAccumWindow"];
    if (props.has("autoTuneCells"))  mParams.autoTuneCells  = props["autoTuneCells"];
    if (props.has("decayPeriod"))    mParams.decayPeriod    = props["decayPeriod"];

    // VisCache feature + ablation toggles
    if (props.has("enableVisCacheVisibilityCheck"))    mParams.enableVisCacheVisibilityCheck    = props["enableVisCacheVisibilityCheck"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
    if (props.has("enableVisCacheJitterA"))         mParams.enableVisCacheJitterA         = props["enableVisCacheJitterA"];
    if (props.has("enableVisCacheJitterB"))         mParams.enableVisCacheJitterB         = props["enableVisCacheJitterB"];
    if (props.has("enableVisCacheAdaptivePMin"))   mParams.enableVisCacheAdaptivePMin   = props["enableVisCacheAdaptivePMin"];
    if (props.has("enableVisCacheNormalAddr"))    mParams.enableVisCacheNormalAddr     = props["enableVisCacheNormalAddr"];
    if (props.has("enableVisCacheDirDistAddr"))     mParams.enableVisCacheDirDistAddr     = props["enableVisCacheDirDistAddr"];
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
    if (props.has("tableCapacity"))  mParams.tableCapacity  = props["tableCapacity"];
    if (props.has("bootThreshold"))  mParams.bootThreshold  = props["bootThreshold"];
    if (props.has("varThreshold"))   mParams.varThreshold   = props["varThreshold"];
    if (props.has("pMin"))           mParams.pMin           = props["pMin"];
    if (props.has("fireflyBudget"))  mParams.fireflyBudget  = props["fireflyBudget"];
    if (props.has("numLevels"))      mParams.numLevels      = props["numLevels"];
    if (props.has("cellACoarse"))  { mParams.cellACoarse    = props["cellACoarse"];  mParams.autoTuneCells = false; }
    if (props.has("cellBCoarse"))    mParams.cellBCoarse    = props["cellBCoarse"];
    if (props.has("angularBCoarse")) mParams.angularBCoarse = props["angularBCoarse"];
    if (props.has("distBCoarse"))    mParams.distBCoarse    = props["distBCoarse"];
    if (props.has("normalBCoarse")) mParams.normalBCoarse  = props["normalBCoarse"];
    if (props.has("diagAccumWindow"))  mParams.diagAccumWindow  = props["diagAccumWindow"];
    if (props.has("autoTuneCells"))  mParams.autoTuneCells  = props["autoTuneCells"];
    if (props.has("decayPeriod"))    mParams.decayPeriod    = props["decayPeriod"];

    if (props.has("enableVisCacheVisibilityCheck"))    mParams.enableVisCacheVisibilityCheck    = props["enableVisCacheVisibilityCheck"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
    if (props.has("enableVisCacheJitterA"))         mParams.enableVisCacheJitterA         = props["enableVisCacheJitterA"];
    if (props.has("enableVisCacheJitterB"))         mParams.enableVisCacheJitterB         = props["enableVisCacheJitterB"];
    if (props.has("enableVisCacheAdaptivePMin"))   mParams.enableVisCacheAdaptivePMin   = props["enableVisCacheAdaptivePMin"];
    if (props.has("enableVisCacheNormalAddr"))    mParams.enableVisCacheNormalAddr     = props["enableVisCacheNormalAddr"];
    if (props.has("enableVisCacheDirDistAddr"))     mParams.enableVisCacheDirDistAddr     = props["enableVisCacheDirDistAddr"];
    if (props.has("enableDiagnostics"))             mEnableDiagnostics                   = props["enableDiagnostics"];
    if (props.has("diagMode"))                     { uint32_t m = props["diagMode"]; mDiagMode = DiagMode(m); }
    if (props.has("resetAccum"))                   mResetAccum                          = props["resetAccum"];
}

// ---------------------------------------------------------------------------
Properties VisCache::getProperties() const
{
    Properties p;
    p["tableCapacity"] = mParams.tableCapacity;
    p["bootThreshold"] = mParams.bootThreshold;
    p["varThreshold"]  = mParams.varThreshold;
    p["pMin"]          = mParams.pMin;
    p["fireflyBudget"] = mParams.fireflyBudget;
    p["numLevels"]     = mParams.numLevels;
    p["cellACoarse"]     = mParams.cellACoarse;
    p["cellBCoarse"]     = mParams.cellBCoarse;
    p["angularBCoarse"]  = mParams.angularBCoarse;
    p["distBCoarse"]     = mParams.distBCoarse;
    p["normalBCoarse"]   = mParams.normalBCoarse;
    p["diagAccumWindow"] = mParams.diagAccumWindow;
    p["autoTuneCells"] = mParams.autoTuneCells;
    p["decayPeriod"]   = mParams.decayPeriod;

    // VisCache feature + ablation toggles
    p["enableVisCacheVisibilityCheck"]    = mParams.enableVisCacheVisibilityCheck;
    p["enableVisCacheLightSelection"]  = mParams.enableVisCacheLightSelection;
    p["enableVisCacheVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    p["enableVisCacheWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    p["enableVisCacheDecay"]           = mParams.enableVisCacheDecay;
    p["enableVisCachePressureEvict"]   = mParams.enableVisCachePressureEvict;
    p["enableVisCacheJitterA"]         = mParams.enableVisCacheJitterA;
    p["enableVisCacheJitterB"]         = mParams.enableVisCacheJitterB;
    p["enableVisCacheAdaptivePMin"]    = mParams.enableVisCacheAdaptivePMin;
    p["enableVisCacheNormalAddr"]     = mParams.enableVisCacheNormalAddr;
    p["enableVisCacheDirDistAddr"]     = mParams.enableVisCacheDirDistAddr;
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
}

// ---------------------------------------------------------------------------
// Auto-derive cellACoarse (and dependent cellBCoarse, distBCoarse) from
// scene bounds. angularBCoarse stays at the user-set default.
//
// Heuristic:
//   cellACoarse  = sceneDiameter / 16
//   cellBCoarse  = cellACoarse * 2  (posB endpoint is coarser)
//   distBCoarse  = cellACoarse * 8  (distance bins are much coarser)
//   angularBCoarse  left at user default (rotation-scale differs from position)
//
// Fine values are NOT set here — they are derived from coarse + numLevels
// at GPU upload time via deriveFine().
// ---------------------------------------------------------------------------
void VisCache::autoTuneCellSizes()
{
    static constexpr float kCoarseScale = 16.f;

    if (!mpScene) return;

    const auto& bounds = mpScene->getSceneBounds();
    float3 extent = bounds.extent();
    float sceneDiameter = std::max({extent.x, extent.y, extent.z});
    if (sceneDiameter <= 0.f) return;

    float coarse = sceneDiameter / kCoarseScale;

    mParams.cellACoarse = coarse;
    mParams.cellBCoarse = coarse * 2.f;
    mParams.distBCoarse = coarse * 8.f;
    // angularBCoarse stays at user default (mParams.angularBCoarse)
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
        logInfo("[VisCache] Auto-tuned: cellACoarse={:.4f} cellBCoarse={:.4f} distBCoarse={:.4f} angularBCoarse={:.1f} (numLevels={})",
                mParams.cellACoarse, mParams.cellBCoarse, mParams.distBCoarse, mParams.angularBCoarse, mParams.numLevels);
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
    mParams.bootThreshold = std::clamp(mParams.bootThreshold, 1u, 0xFFFFu);
    if (mParams.varThreshold   <= 0.f) mParams.varThreshold   = 0.01f;
    if (mParams.cellACoarse    <= 0.f) mParams.cellACoarse    = 1.0f;
    if (mParams.cellBCoarse    <= 0.f) mParams.cellBCoarse    = 1.0f;
    if (mParams.angularBCoarse <= 0.f) mParams.angularBCoarse = 1.0f;
    if (mParams.distBCoarse    <= 0.f) mParams.distBCoarse    = 1.0f;
    if (mParams.pMin           <= 0.f) mParams.pMin           = 0.01f;

    // Derive fine values from coarse + numLevels
    static constexpr float kMaxRatio = 4.f;
    auto deriveFine = [&](float coarse, uint32_t N) -> float {
        return coarse / std::pow(kMaxRatio, std::sqrt(float(N - 1)));
    };

    GPUParams gpu = {};
    gpu.tableCapacity  = mParams.tableCapacity;
    gpu.bootThreshold  = mParams.bootThreshold;
    gpu.varThreshold   = mParams.varThreshold;
    gpu.pMin           = mParams.pMin;
    gpu.fireflyBudget  = mParams.fireflyBudget;
    gpu.numLevels      = mParams.numLevels;
    gpu.flags          = (mParams.enableVisCacheJitterA ? 1u : 0u)
                       | (mParams.enableVisCacheJitterB ? 2u : 0u)
                       | (mParams.enableVisCacheAdaptivePMin ? 4u : 0u)
                       | (mParams.enableVisCacheNormalAddr ? 8u : 0u);
    gpu.cellACoarse    = mParams.cellACoarse;
    gpu.cellAFine      = (mParams.numLevels > 1) ? deriveFine(mParams.cellACoarse, mParams.numLevels) : mParams.cellACoarse;
    gpu.cellBCoarse    = mParams.cellBCoarse;
    gpu.cellBFine      = (mParams.numLevels > 1) ? deriveFine(mParams.cellBCoarse, mParams.numLevels) : mParams.cellBCoarse;
    gpu.angularBCoarse = mParams.angularBCoarse;
    gpu.angularBFine   = (mParams.numLevels > 1) ? deriveFine(mParams.angularBCoarse, mParams.numLevels) : mParams.angularBCoarse;
    gpu.distBCoarse    = mParams.distBCoarse;
    gpu.distBFine      = (mParams.numLevels > 1) ? deriveFine(mParams.distBCoarse, mParams.numLevels) : mParams.distBCoarse;
    gpu.normalBCoarse  = mParams.normalBCoarse;
    gpu.normalBFine    = (mParams.numLevels > 1) ? deriveFine(mParams.normalBCoarse, mParams.numLevels) : mParams.normalBCoarse;
    gpu.diagAccumWindow = mParams.diagAccumWindow;
    std::memcpy(mpParamsBuffer->map(), &gpu, sizeof(gpu));
    mpParamsBuffer->unmap();

    // Log params on first frame for debugging.
    if (mFrameCount == 0u)
    {
        logInfo("[VisCache] tableCapacity={} bootThreshold={} varThreshold={:.3f} pMin={:.3f} fireflyBudget={:.3f}",
                mParams.tableCapacity, mParams.bootThreshold, mParams.varThreshold, mParams.pMin, mParams.fireflyBudget);
        logInfo("[VisCache] cellA: coarse={:.4f} fine={:.4f}", gpu.cellACoarse, gpu.cellAFine);
        logInfo("[VisCache] cellB: coarse={:.4f} fine={:.4f}", gpu.cellBCoarse, gpu.cellBFine);
        logInfo("[VisCache] angularB: coarse={:.1f}{} fine={:.1f}{}", gpu.angularBCoarse, "\xC2\xB0", gpu.angularBFine, "\xC2\xB0");
        logInfo("[VisCache] distB: coarse={:.4f} fine={:.4f}", gpu.distBCoarse, gpu.distBFine);
        logInfo("[VisCache] visCheck={} lightSel={} warpRed={} varGate={} decay={} pressEvict={} jitterA={} jitterB={} adaptPMin={} dirDistAddr={}",
                mParams.enableVisCacheVisibilityCheck, mParams.enableVisCacheLightSelection,
                mParams.enableVisCacheWarpReduction, mParams.enableVisCacheVarianceGate,
                mParams.enableVisCacheDecay, mParams.enableVisCachePressureEvict,
                mParams.enableVisCacheJitterA, mParams.enableVisCacheJitterB, mParams.enableVisCacheAdaptivePMin,
                mParams.enableVisCacheDirDistAddr);
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
    dict["vhfTable"]    = mpHashTable;
    dict["vhfParamsCB"] = mpParamsBuffer;  // kept for backward compat; prefer per-member binding below

    // Per-member cbuffer values — downstream passes bind these individually
    // because Falcor 8 ParameterBlock::setBuffer() doesn't support cbuffer binding.
    dict["vhfParam_tableCapacity"]  = mParams.tableCapacity;
    dict["vhfParam_bootThreshold"]  = mParams.bootThreshold;
    dict["vhfParam_varThreshold"]   = mParams.varThreshold;
    dict["vhfParam_pMin"]           = mParams.pMin;
    dict["vhfParam_fireflyBudget"]  = mParams.fireflyBudget;
    dict["vhfParam_numLevels"]      = mParams.numLevels;
    dict["vhfParam_enableJitterA"]  = mParams.enableVisCacheJitterA ? 1u : 0u;
    dict["vhfParam_enableJitterB"]  = mParams.enableVisCacheJitterB ? 1u : 0u;
    dict["vhfParam_flags"]         = gpu.flags;
    dict["vhfParam_cellACoarse"]    = gpu.cellACoarse;
    dict["vhfParam_cellAFine"]      = gpu.cellAFine;
    dict["vhfParam_cellBCoarse"]    = gpu.cellBCoarse;
    dict["vhfParam_cellBFine"]      = gpu.cellBFine;
    dict["vhfParam_angularBCoarse"] = gpu.angularBCoarse;
    dict["vhfParam_angularBFine"]   = gpu.angularBFine;
    dict["vhfParam_distBCoarse"]    = gpu.distBCoarse;
    dict["vhfParam_distBFine"]      = gpu.distBFine;
    dict["vhfParam_normalBCoarse"]  = gpu.normalBCoarse;
    dict["vhfParam_normalBFine"]    = gpu.normalBFine;
    dict["vhfParam_diagAccumWindow"] = mParams.diagAccumWindow;

    // Feature + ablation toggles — downstream passes read these
    dict["vhfEnableVisibilityCheck"] = mParams.enableVisCacheVisibilityCheck;
    dict["vhfEnableLightSelection"]  = mParams.enableVisCacheLightSelection;
    dict["vhfEnableWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    dict["vhfEnableVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    dict["vhfEnableDecay"]           = mParams.enableVisCacheDecay;
    dict["vhfEnablePressureEvict"]   = mParams.enableVisCachePressureEvict;
    dict["vhfEnableJitterA"]         = mParams.enableVisCacheJitterA;
    dict["vhfEnableJitterB"]         = mParams.enableVisCacheJitterB;
    dict["vhfEnableDirDistAddr"]     = mParams.enableVisCacheDirDistAddr;

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
        autoTuneDecayPeriod();
    }

    mFrameCount++;
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
    vars["VisCacheParams"]["gBootThreshold"]  = mParams.bootThreshold;
    vars["VisCacheParams"]["gVarThreshold"]   = mParams.varThreshold;
    vars["VisCacheParams"]["gPMin"]           = mParams.pMin;
    vars["VisCacheParams"]["gFireflyBudget"]  = mParams.fireflyBudget;
    vars["VisCacheParams"]["gNumLevels"]      = N;
    vars["VisCacheParams"]["gFlags"]          = (mParams.enableVisCacheJitterA ? 1u : 0u)
                                                | (mParams.enableVisCacheJitterB ? 2u : 0u)
                                                | (mParams.enableVisCacheAdaptivePMin ? 4u : 0u)
                       | (mParams.enableVisCacheNormalAddr ? 8u : 0u);
    vars["VisCacheParams"]["gCellACoarse"]    = mParams.cellACoarse;
    vars["VisCacheParams"]["gCellAFine"]      = (N > 1) ? deriveFine(mParams.cellACoarse, N) : mParams.cellACoarse;
    vars["VisCacheParams"]["gCellBCoarse"]    = mParams.cellBCoarse;
    vars["VisCacheParams"]["gCellBFine"]      = (N > 1) ? deriveFine(mParams.cellBCoarse, N) : mParams.cellBCoarse;
    vars["VisCacheParams"]["gAngularBCoarse"] = mParams.angularBCoarse;
    vars["VisCacheParams"]["gAngularBFine"]   = (N > 1) ? deriveFine(mParams.angularBCoarse, N) : mParams.angularBCoarse;
    vars["VisCacheParams"]["gDistBCoarse"]    = mParams.distBCoarse;
    vars["VisCacheParams"]["gDistBFine"]      = (N > 1) ? deriveFine(mParams.distBCoarse, N) : mParams.distBCoarse;
    vars["VisCacheParams"]["gNormalBCoarse"]  = mParams.normalBCoarse;
    vars["VisCacheParams"]["gNormalBFine"]    = (N > 1) ? deriveFine(mParams.normalBCoarse, N) : mParams.normalBCoarse;
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

    widget.var("pMin",             mParams.pMin,           0.01f, 0.5f,  0.005f);
    widget.var("Var threshold",    mParams.varThreshold,   0.01f, 0.5f,  0.01f);
    widget.var("Firefly budget",   mParams.fireflyBudget,  0.001f, 1.0f, 0.005f);
    widget.separator();
    widget.var("Num LOD levels",   mParams.numLevels,      1u, 16u);

    // Cell sizes (coarse only — fine auto-derived from coarse + numLevels)
    if (auto g = widget.group("Cell sizes"))
    {
        g.var("Cell A coarse",           mParams.cellACoarse,    0.01f, 100.0f, 0.01f);
        g.var("Cell B coarse",           mParams.cellBCoarse,    0.01f, 100.0f, 0.01f);
        g.var("Angular B coarse (deg)",  mParams.angularBCoarse, 1.0f, 360.0f, 1.0f);
        g.var("Dist B coarse",           mParams.distBCoarse,    0.01f, 100.0f, 0.1f);
        g.var("Diag accum window",       mParams.diagAccumWindow, 0u, 1024u);
    }

    widget.var("Decay period max", mParams.decayPeriodMax, 15u, 2000u);
    widget.separator();

    widget.checkbox("VisCache visibility check",       mParams.enableVisCacheVisibilityCheck);
    widget.checkbox("VisCache light selection (S11.1)", mParams.enableVisCacheLightSelection);
    widget.checkbox("VisCache warp reduction",         mParams.enableVisCacheWarpReduction);
    widget.separator();

    // Ablation toggles
    if (auto g = widget.group("Ablation toggles", /*open=*/false))
    {
        g.checkbox("B: Variance-gated depth", mParams.enableVisCacheVarianceGate);
        g.checkbox("C: Warp reduction",       mParams.enableVisCacheWarpReduction);
        g.checkbox("D: Inline CAS decay",     mParams.enableVisCacheDecay);
        g.checkbox("E: Pressure eviction",    mParams.enableVisCachePressureEvict);
        g.checkbox("F: Jitter posA",  mParams.enableVisCacheJitterA);
        g.checkbox("F: Jitter posB",  mParams.enableVisCacheJitterB);
        g.checkbox("G: Dir+dist addressing", mParams.enableVisCacheDirDistAddr);
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

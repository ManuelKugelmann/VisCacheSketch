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
static const std::string kOutputDiag           = "vcDiag";
static const std::string kOutputDiagError      = "vcDiagError";
static const std::string kOutputDiagComposite  = "vcDiagComposite";
static const std::string kOutputDiagComposite2 = "vcDiagComposite2";
static const std::string kOutputRaySavedRatio  = "vcRaySavedRatio";
static const std::string kOutputNoise          = "vcNoise";

static const ChannelList kDiagOutputChannels = {
    { kOutputDiag,           "", "VisCache diagnostics (R=mu, G=var, B=level, A=raySaved)",  true, ResourceFormat::RGBA32Float },
    { kOutputDiagError,      "", "VisCache prediction error |mu - V|",                       true, ResourceFormat::R32Float },
    { kOutputDiagComposite,  "", "VisCache composite heatmap (R=var, G=maturity, B=level)",  true, ResourceFormat::RGBA32Float },
    { kOutputDiagComposite2, "", "VisCache composite heatmap (R=var, G=maturity, B=mu)",     true, ResourceFormat::RGBA32Float },
    { kOutputRaySavedRatio,  "", "Per-pixel ray savings ratio [0,1] (accumulated)",          true, ResourceFormat::R32Float },
    { kOutputNoise,          "", "Per-pixel noise estimate (variance EMA)",                   true, ResourceFormat::R32Float },
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
    if (props.has("cellCoarse"))   { mParams.cellCoarse     = props["cellCoarse"];   mParams.autoTuneCells = false; }
    if (props.has("cellFine"))     { mParams.cellFine       = props["cellFine"];     mParams.autoTuneCells = false; }
    if (props.has("autoTuneCells"))  mParams.autoTuneCells  = props["autoTuneCells"];
    if (props.has("decayPeriod"))    mParams.decayPeriod    = props["decayPeriod"];

    // VisCache feature + ablation toggles
    if (props.has("enableVisCacheVisibilityCheck"))    mParams.enableVisCacheVisibilityCheck    = props["enableVisCacheVisibilityCheck"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
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
Properties VisCache::getProperties() const
{
    Properties p;
    p["tableCapacity"] = mParams.tableCapacity;
    p["bootThreshold"] = mParams.bootThreshold;
    p["varThreshold"]  = mParams.varThreshold;
    p["pMin"]          = mParams.pMin;
    p["fireflyBudget"] = mParams.fireflyBudget;
    p["numLevels"]     = mParams.numLevels;
    p["cellCoarse"]    = mParams.cellCoarse;
    p["cellFine"]      = mParams.cellFine;
    p["autoTuneCells"] = mParams.autoTuneCells;
    p["decayPeriod"]   = mParams.decayPeriod;

    // VisCache feature + ablation toggles
    p["enableVisCacheVisibilityCheck"]    = mParams.enableVisCacheVisibilityCheck;
    p["enableVisCacheLightSelection"]  = mParams.enableVisCacheLightSelection;
    p["enableVisCacheVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    p["enableVisCacheWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    p["enableVisCacheDecay"]           = mParams.enableVisCacheDecay;
    p["enableVisCachePressureEvict"]   = mParams.enableVisCachePressureEvict;
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
// Auto-derive cellCoarse / cellFine from scene bounds + camera.
//
// Heuristic:
//   viewDist   = min(camera.farPlane, sceneDiameter)
//   cellCoarse = viewDist / 10
//   cellFine   = cellCoarse / R^sqrt(N-1)
//
// The sqrt exponent means adding levels primarily improves smoothness
// of the cascade (smaller per-level ratio) rather than pushing the
// finest cell to extremes:
//
//   R=4: N=2 → /4     N=3 → /6.3   N=5 → /8    N=8 → /11
//
// Compare naive R^(N-1):
//   R=4: N=2 → /4     N=3 → /16    N=5 → /256  N=8 → /16384
//
// The total coarse-to-fine range grows with more levels, but gently.
// Additional levels fill in the intermediate resolution gaps.
// ---------------------------------------------------------------------------
void VisCache::autoTuneCellSizes()
{
    static constexpr float kMaxRatio = 4.f;  // base refinement factor

    if (!mpScene) return;

    const auto& bounds = mpScene->getSceneBounds();
    float3 extent = bounds.extent();
    float sceneDiameter = std::max({extent.x, extent.y, extent.z});
    if (sceneDiameter <= 0.f) return;

    float farPlane = 1000.f;
    if (mpScene->getCamera())
        farPlane = mpScene->getCamera()->getFarPlane();

    float viewDist = std::min(farPlane, sceneDiameter);
    float coarse = viewDist / 10.f;
    float fine   = coarse / std::pow(kMaxRatio, std::sqrt(float(mParams.numLevels - 1)));

    mParams.cellCoarse = coarse;
    mParams.cellFine   = fine;
}

// ---------------------------------------------------------------------------
void VisCache::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    if (mParams.autoTuneCells && mpScene)
        autoTuneCellSizes();
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
    if (mParams.varThreshold  <= 0.f) mParams.varThreshold  = 0.01f;
    if (mParams.cellCoarse    <= 0.f) mParams.cellCoarse    = 1.0f;
    if (mParams.cellFine      <= 0.f) mParams.cellFine      = 0.01f;
    if (mParams.pMin          <= 0.f) mParams.pMin          = 0.01f;

    GPUParams gpu;
    gpu.tableCapacity = mParams.tableCapacity;
    gpu.bootThreshold = mParams.bootThreshold;
    gpu.varThreshold  = mParams.varThreshold;
    gpu.pMin          = mParams.pMin;
    gpu.fireflyBudget = mParams.fireflyBudget;
    gpu.numLevels     = mParams.numLevels;
    gpu.cellCoarse    = mParams.cellCoarse;
    gpu.cellFine      = mParams.cellFine;
    std::memcpy(mpParamsBuffer->map(), &gpu, sizeof(gpu));
    mpParamsBuffer->unmap();

    auto& dict = renderData.getDictionary();
    dict["vhfTable"]    = mpHashTable;
    dict["vhfParamsCB"] = mpParamsBuffer;

    // Feature + ablation toggles — downstream passes read these
    dict["vhfEnableVisibilityCheck"] = mParams.enableVisCacheVisibilityCheck;
    dict["vhfEnableLightSelection"]  = mParams.enableVisCacheLightSelection;
    dict["vhfEnableWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    dict["vhfEnableVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    dict["vhfEnableDecay"]           = mParams.enableVisCacheDecay;
    dict["vhfEnablePressureEvict"]   = mParams.enableVisCachePressureEvict;

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
        auto makeR32F = [&](const char* name) {
            auto t = mpDevice->createTexture2D(
                mFrameDims.x, mFrameDims.y, ResourceFormat::R32Float, 1, 1,
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
        ref<Texture> diagTex, diagErrorTex, diagCompositeTex, diagComposite2Tex;
        ref<Texture> raySavedRatioTex, noiseTex;

        if (auto p = renderData[kOutputDiag])           diagTex           = p->asTexture();
        if (auto p = renderData[kOutputDiagError])      diagErrorTex      = p->asTexture();
        if (auto p = renderData[kOutputDiagComposite])  diagCompositeTex  = p->asTexture();
        if (auto p = renderData[kOutputDiagComposite2]) diagComposite2Tex = p->asTexture();
        if (auto p = renderData[kOutputRaySavedRatio])  raySavedRatioTex  = p->asTexture();
        if (auto p = renderData[kOutputNoise])          noiseTex          = p->asTexture();

        bool needInternal = mEnableDiagnostics && mFrameDims.x > 0 && mFrameDims.y > 0;
        if (needInternal)
        {
            bool needRealloc = !mpDiagTex || mpDiagTex->getWidth() != mFrameDims.x
                                          || mpDiagTex->getHeight() != mFrameDims.y;
            if (needRealloc)
            {
                mpDiagTex           = makeRGBA("VHF_Diag");
                mpDiagCompositeTex  = makeRGBA("VHF_DiagComposite");
                mpDiagComposite2Tex = makeRGBA("VHF_DiagComposite2");
                mpDiagErrorTex      = makeR32F("VHF_DiagError");
                mpRaySavedRatioTex  = makeR32F("VHF_RaySavedRatio");
                mpNoiseTex          = makeR32F("VHF_Noise");
                mResetAccum = true;  // accum textures need realloc too
            }
            if (!diagTex)           diagTex           = mpDiagTex;
            if (!diagErrorTex)      diagErrorTex      = mpDiagErrorTex;
            if (!diagCompositeTex)  diagCompositeTex  = mpDiagCompositeTex;
            if (!diagComposite2Tex) diagComposite2Tex = mpDiagComposite2Tex;
            if (!raySavedRatioTex)  raySavedRatioTex  = mpRaySavedRatioTex;
            if (!noiseTex)          noiseTex          = mpNoiseTex;
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
                if (noiseTex)
                    pCtx->clearUAV(noiseTex->getUAV().get(), float4(0.f));
                mResetAccum = false;
            }
            dict["vhfAccumSaved"] = mpAccumSaved;
            dict["vhfAccumTotal"] = mpAccumTotal;
        }

        // Clear per-frame textures and expose via dictionary
        auto clearAndExpose = [&](ref<Texture>& tex, const char* key) {
            if (tex) { pCtx->clearUAV(tex->getUAV().get(), float4(0.f)); dict[key] = tex; }
        };
        clearAndExpose(diagTex,           "vhfDiag");
        clearAndExpose(diagErrorTex,      "vhfDiagError");
        clearAndExpose(diagCompositeTex,  "vhfDiagComposite");
        clearAndExpose(diagComposite2Tex, "vhfDiagComposite2");

        // Ratio + noise: cleared per frame (downstream passes write updated values)
        clearAndExpose(raySavedRatioTex,  "vhfRaySavedRatio");
        clearAndExpose(noiseTex,          "vhfNoise");

        dict["vhfDiagEnabled"] = (diagTex != nullptr);
        dict["vhfDiagMode"]    = uint32_t(mDiagMode);
    }

    // ----------------------------------------------------------------
    // Background decay sweep (1/decayPeriod of table per frame)
    // ----------------------------------------------------------------
    if (mParams.enableVisCacheDecay && mParams.decayPeriod > 0 &&
        (mFrameCount % mParams.decayPeriod) == 0u)
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
    vars["gVHFTable"]    = mpHashTable;
    vars["gTableCapacity"] = mParams.tableCapacity;

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
    widget.var("Cell coarse (m)",  mParams.cellCoarse,     0.1f, 100.0f, 0.5f);
    widget.var("Cell fine (m)",    mParams.cellFine,       0.01f, 10.0f, 0.01f);
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
    }

    widget.separator();

    static const Gui::DropdownList kHeatmapModes = {
        {uint32_t(DiagMode::Off),             "Off"},
        {uint32_t(DiagMode::CachedMu),        "Cached Mu (visibility)"},
        {uint32_t(DiagMode::Variance),        "Variance (uncertainty)"},
        {uint32_t(DiagMode::LODLevel),        "LOD Level"},
        {uint32_t(DiagMode::RaySaved),        "Ray Saved"},
        {uint32_t(DiagMode::PredictionError), "Prediction Error |mu-V|"},
    };
    widget.dropdown("Heatmap", kHeatmapModes, reinterpret_cast<uint32_t&>(mDiagMode));
    mEnableDiagnostics = (mDiagMode != DiagMode::Off);
}

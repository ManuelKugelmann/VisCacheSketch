/***************************************************************************
 * VisCache.cpp
 *
 * Falcor 8.0 RenderPass implementation.
 * All GPU resources allocated here; hash table exposed to downstream
 * passes (PathTracer, RTXDIPass, ReSTIRPTPass) via InternalDictionary.
 ***************************************************************************/

#include "VisCache.h"

// Entry size must match Slang struct VHFEntry (2x uint32 = 8 bytes)
static constexpr size_t kEntrySize = 8u;
static constexpr uint32_t kStatCount = 5u; // inserts, evictions, misses, decay, probeSum (last two accumulated but not read back yet)

// Diagnostic heatmap output channel names
static const std::string kOutputDiag      = "vcDiag";
static const std::string kOutputDiagError = "vcDiagError";

static const ChannelList kDiagOutputChannels = {
    { kOutputDiag,      "", "VisCache diagnostics (R=mu, G=var, B=level, A=raySaved)", true, ResourceFormat::RGBA32Float },
    { kOutputDiagError, "", "VisCache prediction error |mu - V|",                      true, ResourceFormat::R32Float },
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
    if (props.has("cellCoarse"))     mParams.cellCoarse     = props["cellCoarse"];
    if (props.has("cellFine"))       mParams.cellFine       = props["cellFine"];
    if (props.has("decayPeriod"))    mParams.decayPeriod    = props["decayPeriod"];

    // VisCache feature + ablation toggles
    if (props.has("enableVisCacheRevalidation"))    mParams.enableVisCacheRevalidation    = props["enableVisCacheRevalidation"];
    if (props.has("enableVisCacheLightSelection"))  mParams.enableVisCacheLightSelection  = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheVarianceGate"))    mParams.enableVisCacheVarianceGate    = props["enableVisCacheVarianceGate"];
    if (props.has("enableVisCacheWarpReduction"))   mParams.enableVisCacheWarpReduction   = props["enableVisCacheWarpReduction"];
    if (props.has("enableVisCacheDecay"))           mParams.enableVisCacheDecay           = props["enableVisCacheDecay"];
    if (props.has("enableVisCachePressureEvict"))   mParams.enableVisCachePressureEvict   = props["enableVisCachePressureEvict"];
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
    p["decayPeriod"]   = mParams.decayPeriod;

    // VisCache feature + ablation toggles
    p["enableVisCacheRevalidation"]    = mParams.enableVisCacheRevalidation;
    p["enableVisCacheLightSelection"]  = mParams.enableVisCacheLightSelection;
    p["enableVisCacheVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    p["enableVisCacheWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    p["enableVisCacheDecay"]           = mParams.enableVisCacheDecay;
    p["enableVisCachePressureEvict"]   = mParams.enableVisCachePressureEvict;
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
        mpDecayPass = ComputePass::create(mpDevice, desc);
    }
}

// ---------------------------------------------------------------------------
void VisCache::allocateBuffers()
{
    // Ensure capacity is power-of-two
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
void VisCache::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    // Nothing scene-specific needed — hash table is world-space.
    // Trigger a re-allocation if scene changes require table resize.
    allocateBuffers();
}

// ---------------------------------------------------------------------------
void VisCache::execute(RenderContext* pCtx, const RenderData& renderData)
{
    // ----------------------------------------------------------------
    // Expose hash table to downstream passes via InternalDictionary.
    // PathTracer, RTXDIPass, and ReSTIRPTPass retrieve these.
    // ----------------------------------------------------------------
    auto& dict = renderData.getDictionary();
    dict["vhfTable"]        = mpHashTable;
    dict["vhfCapacity"]     = mParams.tableCapacity;
    dict["vhfVarThreshold"] = mParams.varThreshold;
    dict["vhfPMin"]         = mParams.pMin;
    dict["vhfBootThreshold"]= mParams.bootThreshold;
    dict["vhfFireflyBudget"]= mParams.fireflyBudget;
    dict["vhfNumLevels"]    = mParams.numLevels;
    dict["vhfCellCoarse"]   = mParams.cellCoarse;
    dict["vhfCellFine"]     = mParams.cellFine;

    // Feature + ablation toggles — downstream passes read these
    dict["vhfEnableRevalidation"]    = mParams.enableVisCacheRevalidation;
    dict["vhfEnableLightSelection"]  = mParams.enableVisCacheLightSelection;
    dict["vhfEnableWarpReduction"]   = mParams.enableVisCacheWarpReduction;
    dict["vhfEnableVarianceGate"]    = mParams.enableVisCacheVarianceGate;
    dict["vhfEnableDecay"]           = mParams.enableVisCacheDecay;
    dict["vhfEnablePressureEvict"]   = mParams.enableVisCachePressureEvict;

    // ----------------------------------------------------------------
    // Diagnostic heatmap textures — allocate/expose, then clear.
    // VisCache runs BEFORE downstream passes, so we expose textures
    // via dictionary and downstream passes write directly to them.
    //
    // Strategy:
    //   - If render graph outputs are connected, expose those directly.
    //   - Otherwise if diagnostics enabled, use internal textures.
    //   - Downstream passes retrieve from dict keys "vhfDiag"/"vhfDiagError".
    // ----------------------------------------------------------------
    {
        ref<Texture> diagTex;
        ref<Texture> diagErrorTex;

        // Prefer graph-allocated output textures (avoids extra copy)
        if (auto pOut = renderData[kOutputDiag])
            diagTex = pOut->asTexture();
        if (auto pOut = renderData[kOutputDiagError])
            diagErrorTex = pOut->asTexture();

        // Fall back to internal textures when outputs not connected
        bool needInternal = mEnableDiagnostics && (!diagTex || !diagErrorTex);
        if (needInternal && mFrameDims.x > 0 && mFrameDims.y > 0)
        {
            if (!mpDiagTex || mpDiagTex->getWidth() != mFrameDims.x
                           || mpDiagTex->getHeight() != mFrameDims.y)
            {
                mpDiagTex = mpDevice->createTexture2D(
                    mFrameDims.x, mFrameDims.y, ResourceFormat::RGBA32Float, 1, 1,
                    nullptr, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess
                );
                mpDiagTex->setName("VHF_Diag");

                mpDiagErrorTex = mpDevice->createTexture2D(
                    mFrameDims.x, mFrameDims.y, ResourceFormat::R32Float, 1, 1,
                    nullptr, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess
                );
                mpDiagErrorTex->setName("VHF_DiagError");
            }
            if (!diagTex)      diagTex      = mpDiagTex;
            if (!diagErrorTex) diagErrorTex = mpDiagErrorTex;
        }

        // Clear and expose via dictionary for downstream passes
        if (diagTex)
        {
            pCtx->clearUAV(diagTex->getUAV().get(), float4(0.f));
            dict["vhfDiag"] = diagTex;
        }
        if (diagErrorTex)
        {
            pCtx->clearUAV(diagErrorTex->getUAV().get(), float4(0.f));
            dict["vhfDiagError"] = diagErrorTex;
        }
        dict["vhfDiagEnabled"] = (diagTex != nullptr);
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

    widget.checkbox("VisCache revalidation (S11.3)",   mParams.enableVisCacheRevalidation);
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
    widget.checkbox("Enable heatmap diagnostics", mEnableDiagnostics);
    if (mEnableDiagnostics)
    {
        widget.text("Connect vcDiag output to ColorMapPass.");
        widget.text("  R = cached mu      (visibility prediction)");
        widget.text("  G = variance        (cache uncertainty)");
        widget.text("  B = LOD level+1   (0=miss, 1=L0, ...)");
        widget.text("  A = ray saved       (1=skipped, 0=traced)");
        widget.text("Connect vcDiagError to ColorMapPass.");
        widget.text("  R = |mu - V|         (prediction error)");
    }
}

/***************************************************************************
 * VisCache.cpp
 *
 * Falcor 8.0 RenderPass implementation.
 * All GPU resources allocated here; hash table exposed to downstream
 * passes (PathTracer, RTXDIPass, ReSTIRGIPass) via InternalDictionary.
 ***************************************************************************/

#include "VisCache.h"

// Entry size must match Slang struct VHFEntry (2x uint32 = 8 bytes)
static constexpr size_t kEntrySize = 8u;
static constexpr uint32_t kStatCount = 5u; // inserts, evictions, misses, decay, probeSum

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
    if (props.has("decayPeriod"))    mParams.decayPeriod    = props["decayPeriod"];
    if (props.has("minLevel"))       mParams.minLevel       = props["minLevel"];
    if (props.has("maxLevel"))       mParams.maxLevel       = props["maxLevel"];
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
    p["decayPeriod"]   = mParams.decayPeriod;
    p["minLevel"]      = mParams.minLevel;
    p["maxLevel"]      = mParams.maxLevel;
    return p;
}

// ---------------------------------------------------------------------------
RenderPassReflection VisCache::reflect(const CompileData&)
{
    // No texture inputs or outputs — the hash table is passed via
    // InternalDictionary, not through the render graph edge system.
    RenderPassReflection r;
    return r;
}

// ---------------------------------------------------------------------------
void VisCache::compile(RenderContext*, const CompileData&)
{
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
    // PathTracer, RTXDIPass, and ReSTIRGIPass retrieve these.
    // ----------------------------------------------------------------
    auto& dict = renderData.getDictionary();
    dict["vhfTable"]        = mpHashTable;
    dict["vhfCapacity"]     = mParams.tableCapacity;
    dict["vhfVarThreshold"] = mParams.varThreshold;
    dict["vhfPMin"]         = mParams.pMin;
    dict["vhfBootThreshold"]= mParams.bootThreshold;
    dict["vhfFireflyBudget"]= mParams.fireflyBudget;
    dict["vhfMinLevel"]     = mParams.minLevel;
    dict["vhfMaxLevel"]     = mParams.maxLevel;

    // ----------------------------------------------------------------
    // Background decay sweep (1/decayPeriod of table per frame)
    // ----------------------------------------------------------------
    if (mParams.enableDecay && mParams.decayPeriod > 0 &&
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
    vars["DecayCB"]["gDecayFactor"] = 0.875f;
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
    widget.var("Decay period max", mParams.decayPeriodMax, 15u, 2000u);
    widget.separator();

    widget.checkbox("GI revalidation",   mParams.enableGIRevalidation);
    widget.checkbox("Light selection",   mParams.enableLightSelection);
    widget.checkbox("Warp reduction",    mParams.enableWarpReduction);
    widget.separator();

    // Ablation toggles
    if (auto g = widget.group("Ablation toggles", /*open=*/false))
    {
        g.checkbox("A: Distance-gated LOD",   mParams.enableDistanceLOD);
        g.checkbox("B: Variance-gated depth", mParams.enableVarianceGate);
        g.checkbox("C: Warp reduction",       mParams.enableWarpReduction);
        g.checkbox("D: Inline CAS decay",     mParams.enableDecay);
        g.checkbox("E: Pressure eviction",    mParams.enablePressureEvict);
        g.var("Min LOD level", mParams.minLevel, 0, 2);
        g.var("Max LOD level", mParams.maxLevel, 0, 2);
    }
}

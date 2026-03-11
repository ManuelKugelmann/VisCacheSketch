/***************************************************************************
 * ReSTIRPTPass.cpp
 *
 * Falcor 8.0 — ReSTIR PT (multi-bounce path reuse) with VisCache.
 *
 * Structure mirrors ReSTIRGIPass but extends initial sampling to trace
 * multi-bounce paths and stores reconnection vertex at the chosen depth.
 * VisCache features are independently toggleable for ablation.
 ***************************************************************************/

#include "ReSTIRPTPass.h"

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, ReSTIRPTPass>();
}

// ============================================================================
ReSTIRPTPass::ReSTIRPTPass(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    if (props.has("maxBounces"))            mParams.maxBounces           = props["maxBounces"];
    if (props.has("numSpatialNeighbors"))   mParams.numSpatialNeighbors  = props["numSpatialNeighbors"];
    if (props.has("spatialRadius"))         mParams.spatialRadius        = props["spatialRadius"];
    if (props.has("enableTemporalReuse"))   mParams.enableTemporalReuse  = props["enableTemporalReuse"];
    if (props.has("enableSpatialReuse"))    mParams.enableSpatialReuse   = props["enableSpatialReuse"];
    if (props.has("enableMIS"))             mParams.enableMIS            = props["enableMIS"];

    if (props.has("enableVisCacheLightSelection"))  mVisCacheFlags.enableVisCacheLightSelection = props["enableVisCacheLightSelection"];
    if (props.has("enableVisCacheRevalidation"))    mVisCacheFlags.enableVisCacheRevalidation   = props["enableVisCacheRevalidation"];
    if (props.has("enableCVRRRRevalidation"))       mVisCacheFlags.enableCVRRRRevalidation      = props["enableCVRRRRevalidation"];
    if (props.has("visCacheContribThreshold"))       mVisCacheFlags.contribThreshold             = props["visCacheContribThreshold"];
    if (props.has("visCachePMin"))                   mVisCacheFlags.pMin                         = props["visCachePMin"];
}

ref<ReSTIRPTPass> ReSTIRPTPass::create(ref<Device> pDevice, const Properties& props)
{
    return make_ref<ReSTIRPTPass>(pDevice, props);
}

// ============================================================================
Properties ReSTIRPTPass::getProperties() const
{
    Properties p;
    p["maxBounces"]            = mParams.maxBounces;
    p["numSpatialNeighbors"]   = mParams.numSpatialNeighbors;
    p["spatialRadius"]         = mParams.spatialRadius;
    p["enableTemporalReuse"]   = mParams.enableTemporalReuse;
    p["enableSpatialReuse"]    = mParams.enableSpatialReuse;
    p["enableMIS"]             = mParams.enableMIS;

    p["enableVisCacheLightSelection"] = mVisCacheFlags.enableVisCacheLightSelection;
    p["enableVisCacheRevalidation"]   = mVisCacheFlags.enableVisCacheRevalidation;
    p["enableCVRRRRevalidation"]      = mVisCacheFlags.enableCVRRRRevalidation;
    p["visCacheContribThreshold"]     = mVisCacheFlags.contribThreshold;
    p["visCachePMin"]                 = mVisCacheFlags.pMin;
    return p;
}

// ============================================================================
RenderPassReflection ReSTIRPTPass::reflect(const CompileData& compileData)
{
    RenderPassReflection r;
    r.addInput("vbuffer", "Visibility buffer (packed hit info)");
    r.addInput("motionVectors", "Motion vectors for temporal reuse")
        .flags(RenderPassReflection::Field::Flags::Optional);
    r.addOutput("color", "Path-traced illumination").format(ResourceFormat::RGBA32Float);
    return r;
}

// ============================================================================
void ReSTIRPTPass::compile(RenderContext* pCtx, const CompileData& compileData)
{
    mFrameDim = compileData.defaultTexDims;
    createPasses();

    uint32_t pixelCount = mFrameDim.x * mFrameDim.y;

    mpReservoirBuffer = mpDevice->createStructuredBuffer(
        kReservoirSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal);
    mpReservoirBuffer->setName("ReSTIRPT_Reservoirs");

    mpPrevReservoirBuffer = mpDevice->createStructuredBuffer(
        kReservoirSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal);
    mpPrevReservoirBuffer->setName("ReSTIRPT_PrevReservoirs");

    mpSecondaryHitBuffer = mpDevice->createStructuredBuffer(
        kSecondaryHitSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal);
    mpSecondaryHitBuffer->setName("ReSTIRPT_SecondaryHits");
}

// ============================================================================
void ReSTIRPTPass::createPasses()
{
    DefineList defines;
    defines.add("MAX_BOUNCES", std::to_string(mParams.maxBounces));
    defines.add("NUM_SPATIAL_NEIGHBORS", std::to_string(mParams.numSpatialNeighbors));
    defines.add("USE_VISCACHE", isVisCacheActive() ? "1" : "0");
    defines.add("USE_VISCACHE_LIGHTSEL", mVisCacheFlags.enableVisCacheLightSelection ? "1" : "0");
    defines.add("USE_VISCACHE_REVAL", mVisCacheFlags.enableVisCacheRevalidation ? "1" : "0");
    defines.add("USE_LOCAL_REVAL", mVisCacheFlags.enableCVRRRRevalidation ? "1" : "0");
    defines.add("USE_TEMPORAL_REUSE", mParams.enableTemporalReuse ? "1" : "0");
    defines.add("USE_SPATIAL_REUSE", mParams.enableSpatialReuse ? "1" : "0");
    defines.add("USE_MIS", mParams.enableMIS ? "1" : "0");

    // Reuse the same shader files as ReSTIRGIPass — the MAX_BOUNCES define
    // controls whether multi-bounce paths are traced in initial sampling.
    // When MAX_BOUNCES=1, this is identical to ReSTIRGIPass (single-bounce GI).
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRPTPass/InitialSampling.cs.slang")
            .csEntry("csInitialSampling");
        mpInitialSamplingPass = ComputePass::create(mpDevice, desc, defines);
    }
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRPTPass/TemporalReuse.cs.slang")
            .csEntry("csTemporalReuse");
        mpTemporalReusePass = ComputePass::create(mpDevice, desc, defines);
    }
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRPTPass/SpatialReuse.cs.slang")
            .csEntry("csSpatialReuse");
        mpSpatialReusePass = ComputePass::create(mpDevice, desc, defines);
    }
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRPTPass/FinalShading.cs.slang")
            .csEntry("csFinalShading");
        mpFinalShadingPass = ComputePass::create(mpDevice, desc, defines);
    }
}

// ============================================================================
void ReSTIRPTPass::execute(RenderContext* pCtx, const RenderData& rd)
{
    if (!mpScene) return;

    auto pVBuffer     = rd.getTexture("vbuffer");
    auto pMotionVec   = rd.getTexture("motionVectors");
    auto pColorOutput = rd.getTexture("color");
    if (!pVBuffer || !pColorOutput) return;

    float3 camPos = mpScene->getCamera()->getPosition();
    retrieveVisCacheBuffers(rd);

    // Pass 1: Initial multi-bounce path sampling
    {
        auto vars = mpInitialSamplingPass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]       = pVBuffer;
        vars["gReservoirs"]    = mpReservoirBuffer;
        vars["gSecondaryHits"] = mpSecondaryHitBuffer;
        vars["PerFrameCB"]["gFrameCount"] = mFrameCount;
        vars["PerFrameCB"]["gFrameDim"]   = mFrameDim;
        vars["PerFrameCB"]["gCamPos"]     = camPos;
        mpInitialSamplingPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // Pass 2: Temporal reuse
    if (mParams.enableTemporalReuse && mFrameCount > 0 && pMotionVec)
    {
        auto vars = mpTemporalReusePass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]        = pVBuffer;
        vars["gReservoirs"]     = mpReservoirBuffer;
        vars["gPrevReservoirs"] = mpPrevReservoirBuffer;
        vars["gMotionVectors"]  = pMotionVec;
        vars["PerFrameCB"]["gFrameDim"]   = mFrameDim;
        vars["PerFrameCB"]["gFrameCount"] = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]     = camPos;
        mpTemporalReusePass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // Pass 3: Spatial reuse (CV+RRR integration point)
    if (mParams.enableSpatialReuse)
    {
        auto vars = mpSpatialReusePass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]        = pVBuffer;
        vars["gReservoirs"]     = mpReservoirBuffer;
        vars["gSecondaryHits"]  = mpSecondaryHitBuffer;
        vars["PerFrameCB"]["gFrameDim"]       = mFrameDim;
        vars["PerFrameCB"]["gSpatialRadius"]  = mParams.spatialRadius;
        vars["PerFrameCB"]["gFrameCount"]     = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]         = camPos;

        if (mVisCacheFlags.enableVisCacheRevalidation && mpVisCacheTable)
            bindVisCacheToPass(mpSpatialReusePass);

        // Local CV+RRR bindings (no hash table, uses reservoir-local mu)
        if (mVisCacheFlags.enableCVRRRRevalidation)
        {
            vars["LocalRevalCB"]["gLocalRevalContribThreshold"] = mVisCacheFlags.contribThreshold;
            vars["LocalRevalCB"]["gLocalRevalPMin"]             = mVisCacheFlags.pMin;
        }

        mpSpatialReusePass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // Pass 4: Final shading
    {
        auto vars = mpFinalShadingPass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]        = pVBuffer;
        vars["gReservoirs"]     = mpReservoirBuffer;
        vars["gSecondaryHits"]  = mpSecondaryHitBuffer;
        vars["gColorOutput"]    = pColorOutput;
        vars["PerFrameCB"]["gFrameDim"]   = mFrameDim;
        vars["PerFrameCB"]["gFrameCount"] = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]     = camPos;
        mpFinalShadingPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    std::swap(mpReservoirBuffer, mpPrevReservoirBuffer);
    mFrameCount++;
}

// ============================================================================
void ReSTIRPTPass::retrieveVisCacheBuffers(const RenderData& rd)
{
    const auto& dict = rd.getDictionary();

    if (isVisCacheActive() &&
        dict.keyExists("vhfTable") && dict.keyExists("vhfCapacity"))
    {
        mpVisCacheTable        = dict["vhfTable"];
        mVisCacheCapacity      = dict["vhfCapacity"];
        mVisCacheVarThreshold  = dict.keyExists("vhfVarThreshold")
            ? dict["vhfVarThreshold"].operator float() : 0.1f;
        mVisCachePMin          = dict.keyExists("vhfPMin")
            ? dict["vhfPMin"].operator float() : 0.05f;
        mVisCacheBootThreshold = dict.keyExists("vhfBootThreshold")
            ? dict["vhfBootThreshold"].operator uint32_t() : 32u;
        mVisCacheFireflyBudget = dict.keyExists("vhfFireflyBudget")
            ? dict["vhfFireflyBudget"].operator float() : 0.05f;

        // VisCache pass is authoritative for feature flags — override local
        if (dict.keyExists("vhfEnableRevalidation"))
            mVisCacheFlags.enableVisCacheRevalidation = dict["vhfEnableRevalidation"];
        if (dict.keyExists("vhfEnableLightSelection"))
            mVisCacheFlags.enableVisCacheLightSelection = dict["vhfEnableLightSelection"];
    }
    else
    {
        mpVisCacheTable   = nullptr;
        mVisCacheCapacity = 0u;
    }
}

// ============================================================================
void ReSTIRPTPass::bindVisCacheToPass(const ref<ComputePass>& pass)
{
    auto vars = pass->getRootVar();
    vars["gVHFTable"]                          = mpVisCacheTable;
    vars["VisCacheParams"]["gTableCapacity"]    = mVisCacheCapacity;
    vars["VisCacheParams"]["gBootThreshold"]     = mVisCacheBootThreshold;
    vars["VisCacheParams"]["gVarThreshold"]      = mVisCacheVarThreshold;
    vars["VisCacheParams"]["gPMin"]              = mVisCachePMin;
    vars["VisCacheParams"]["gFireflyBudget"]     = mVisCacheFireflyBudget;
}

// ============================================================================
void ReSTIRPTPass::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    mFrameCount = 0u;
}

// ============================================================================
void ReSTIRPTPass::renderUI(Gui::Widgets& widget)
{
    widget.text("ReSTIR PT (Multi-Bounce) + VisCache");
    widget.separator();

    bool dirty = false;

    dirty |= widget.var("Max bounces", mParams.maxBounces, 1u, 8u);
    dirty |= widget.var("Spatial neighbors (k)", mParams.numSpatialNeighbors, 1u, 16u);
    dirty |= widget.var("Spatial radius (px)", mParams.spatialRadius, 5.0f, 100.0f, 1.0f);
    dirty |= widget.checkbox("Temporal reuse", mParams.enableTemporalReuse);
    dirty |= widget.checkbox("Spatial reuse", mParams.enableSpatialReuse);
    dirty |= widget.checkbox("Talbot MIS", mParams.enableMIS);
    widget.separator();

    widget.text("VisCache Integration (toggleable for ablation)");
    dirty |= widget.checkbox("VisCache CV+RRR revalidation (S11.3)",     mVisCacheFlags.enableVisCacheRevalidation);
    dirty |= widget.checkbox("CV+RRR revalidation (reservoir mu, no hash table)", mVisCacheFlags.enableCVRRRRevalidation);
    dirty |= widget.checkbox("VisCache light selection (S11.1)",          mVisCacheFlags.enableVisCacheLightSelection);
    if (isVisCacheActive() || mVisCacheFlags.enableCVRRRRevalidation)
    {
        widget.var("Contrib threshold",   mVisCacheFlags.contribThreshold, 0.001f, 0.5f, 0.005f);
        widget.var("pMin (RR floor)",     mVisCacheFlags.pMin,             0.01f,  0.5f, 0.005f);
    }

    if (dirty) createPasses();
}

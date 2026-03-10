/***************************************************************************
 * ReSTIRGIPass.cpp
 *
 * Falcor 8.0 implementation — ReSTIR GI with VisCache revalidation.
 *
 * Port of DQLin/ReSTIR_PT (Falcor 5.2) to Falcor 8.0. The core
 * reservoir logic (initial sampling, temporal reuse, spatial reuse,
 * final shading) follows DQLin's original structure. The VisCache
 * integration replaces unconditional V(P,Q) shadow rays in spatial
 * reuse with CV+RRR gated calls (§11.3 / §12).
 *
 * DQLin/ReSTIR_PT paper: "Generalized Resampled Importance Sampling:
 * Foundations of ReSTIR" (Lin et al., SIGGRAPH 2022).
 ***************************************************************************/

#include "ReSTIRGIPass.h"

// ============================================================================
// Plugin registration (Falcor 8.0)
// ============================================================================
extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, ReSTIRGIPass>();
}

// ============================================================================
// Construction
// ============================================================================
ReSTIRGIPass::ReSTIRGIPass(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    // Deserialise ReSTIR params
    if (props.has("numSpatialNeighbors")) mReSTIRParams.numSpatialNeighbors = props["numSpatialNeighbors"];
    if (props.has("spatialRadius"))       mReSTIRParams.spatialRadius       = props["spatialRadius"];
    if (props.has("numTemporalSamples"))  mReSTIRParams.numTemporalSamples  = props["numTemporalSamples"];
    if (props.has("enableTemporalReuse")) mReSTIRParams.enableTemporalReuse = props["enableTemporalReuse"];
    if (props.has("enableSpatialReuse"))  mReSTIRParams.enableSpatialReuse  = props["enableSpatialReuse"];
    if (props.has("enableMIS"))           mReSTIRParams.enableMIS           = props["enableMIS"];

    // Deserialise VisCache params (independently toggleable for ablation)
    if (props.has("visCacheRevalidation"))    mVisCacheParams.enableRevalidation   = props["visCacheRevalidation"];
    if (props.has("visCacheLightSelection")) mVisCacheParams.enableLightSelection = props["visCacheLightSelection"];
    if (props.has("visCacheContribThreshold")) mVisCacheParams.contribThreshold    = props["visCacheContribThreshold"];
    if (props.has("visCachePMin"))             mVisCacheParams.pMin                = props["visCachePMin"];
    if (props.has("visCacheSymmetricCells"))   mVisCacheParams.symmetricCells      = props["visCacheSymmetricCells"];
}

ref<ReSTIRGIPass> ReSTIRGIPass::create(ref<Device> pDevice, const Properties& props)
{
    return make_ref<ReSTIRGIPass>(pDevice, props);
}

// ============================================================================
// Properties (serialise for Python scripting / saved graphs)
// ============================================================================
Properties ReSTIRGIPass::getProperties() const
{
    Properties p;
    p["numSpatialNeighbors"] = mReSTIRParams.numSpatialNeighbors;
    p["spatialRadius"]       = mReSTIRParams.spatialRadius;
    p["numTemporalSamples"]  = mReSTIRParams.numTemporalSamples;
    p["enableTemporalReuse"] = mReSTIRParams.enableTemporalReuse;
    p["enableSpatialReuse"]  = mReSTIRParams.enableSpatialReuse;
    p["enableMIS"]           = mReSTIRParams.enableMIS;

    p["visCacheRevalidation"]     = mVisCacheParams.enableRevalidation;
    p["visCacheLightSelection"]   = mVisCacheParams.enableLightSelection;
    p["visCacheContribThreshold"] = mVisCacheParams.contribThreshold;
    p["visCachePMin"]             = mVisCacheParams.pMin;
    p["visCacheSymmetricCells"]   = mVisCacheParams.symmetricCells;
    return p;
}

// ============================================================================
// Reflect: declare I/O channels for render graph
// ============================================================================
RenderPassReflection ReSTIRGIPass::reflect(const CompileData& compileData)
{
    RenderPassReflection r;

    // Inputs from GBuffer / PathTracer
    r.addInput("vbuffer", "Visibility buffer (packed hit info)");
    r.addInput("motionVectors", "Motion vectors for temporal reuse").flags(RenderPassReflection::Field::Flags::Optional);

    // Output
    r.addOutput("color", "Indirect illumination").format(ResourceFormat::RGBA32Float);

    return r;
}

// ============================================================================
// Compile: create GPU passes and allocate reservoir buffers
// ============================================================================
void ReSTIRGIPass::compile(RenderContext* pCtx, const CompileData& compileData)
{
    mFrameDim = compileData.defaultTexDims;
    createPasses();

    uint32_t pixelCount = mFrameDim.x * mFrameDim.y;

    // Reservoir double-buffer for temporal reuse
    mpReservoirBuffer = mpDevice->createStructuredBuffer(
        kReservoirSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal
    );
    mpReservoirBuffer->setName("ReSTIRGI_Reservoirs");

    mpPrevReservoirBuffer = mpDevice->createStructuredBuffer(
        kReservoirSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal
    );
    mpPrevReservoirBuffer->setName("ReSTIRGI_PrevReservoirs");

    mpSecondaryHitBuffer = mpDevice->createStructuredBuffer(
        kSecondaryHitSize, pixelCount,
        ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess,
        MemoryType::DeviceLocal
    );
    mpSecondaryHitBuffer->setName("ReSTIRGI_SecondaryHits");
}

// ============================================================================
// Create compute passes from Slang shaders
// ============================================================================
void ReSTIRGIPass::createPasses()
{
    DefineList defines;
    defines.add("NUM_SPATIAL_NEIGHBORS", std::to_string(mReSTIRParams.numSpatialNeighbors));
    defines.add("USE_VISCACHE", isVisCacheActive() ? "1" : "0");
    defines.add("USE_VISCACHE_REVAL", mVisCacheParams.enableRevalidation ? "1" : "0");
    defines.add("USE_VISCACHE_LIGHTSEL", mVisCacheParams.enableLightSelection ? "1" : "0");
    defines.add("USE_TEMPORAL_REUSE", mReSTIRParams.enableTemporalReuse ? "1" : "0");
    defines.add("USE_SPATIAL_REUSE", mReSTIRParams.enableSpatialReuse ? "1" : "0");
    defines.add("USE_MIS", mReSTIRParams.enableMIS ? "1" : "0");

    // Initial path trace sampling
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRGIPass/InitialSampling.cs.slang")
            .csEntry("csInitialSampling");
        mpInitialSamplingPass = ComputePass::create(mpDevice, desc, defines);
    }

    // Temporal reuse
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRGIPass/TemporalReuse.cs.slang")
            .csEntry("csTemporalReuse");
        mpTemporalReusePass = ComputePass::create(mpDevice, desc, defines);
    }

    // Spatial reuse (VisCache integration point — CV+RRR replaces V(P,Q))
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRGIPass/SpatialReuse.cs.slang")
            .csEntry("csSpatialReuse");
        mpSpatialReusePass = ComputePass::create(mpDevice, desc, defines);
    }

    // Final shading
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRGIPass/FinalShading.cs.slang")
            .csEntry("csFinalShading");
        mpFinalShadingPass = ComputePass::create(mpDevice, desc, defines);
    }
}

// ============================================================================
// Execute: main render loop
// ============================================================================
void ReSTIRGIPass::execute(RenderContext* pCtx, const RenderData& rd)
{
    if (!mpScene) return;

    auto pVBuffer      = rd.getTexture("vbuffer");
    auto pMotionVec    = rd.getTexture("motionVectors");
    auto pColorOutput  = rd.getTexture("color");

    if (!pVBuffer || !pColorOutput) return;

    // Camera position for VisCache LOD and distance calculations
    float3 camPos = mpScene->getCamera()->getPosition();

    // ----------------------------------------------------------------
    // Retrieve VisCache buffers from InternalDictionary (if available)
    // VisCache must run before this pass in the render graph.
    // ----------------------------------------------------------------
    retrieveVisCacheBuffers(rd);

    // ----------------------------------------------------------------
    // Pass 1: Initial path trace sampling
    // Trace one secondary ray per pixel, store in reservoir + hit data
    // ----------------------------------------------------------------
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

    // ----------------------------------------------------------------
    // Pass 2: Temporal reuse
    // ----------------------------------------------------------------
    if (mReSTIRParams.enableTemporalReuse && mFrameCount > 0 && pMotionVec)
    {
        auto vars = mpTemporalReusePass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]            = pVBuffer;
        vars["gReservoirs"]         = mpReservoirBuffer;
        vars["gPrevReservoirs"]     = mpPrevReservoirBuffer;
        vars["gSecondaryHits"]      = mpSecondaryHitBuffer;
        vars["gMotionVectors"]      = pMotionVec;
        vars["PerFrameCB"]["gFrameDim"]   = mFrameDim;
        vars["PerFrameCB"]["gFrameCount"] = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]     = camPos;

        mpTemporalReusePass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // ----------------------------------------------------------------
    // Pass 3: Spatial reuse (VisCache integration — §11.3)
    //
    // For each of k neighbors, DQLin traces an unconditional V(P,Q).
    // With VisCache enabled, evalRevalidationCV() replaces this:
    //   - Lookup cached mu for (P, Q)
    //   - RR with p = clamp(residual / threshold, pMin, 1.0)
    //   - Traces only when RR fires → ~0.5–1.0 rays/pixel vs. k=5.0
    // ----------------------------------------------------------------
    if (mReSTIRParams.enableSpatialReuse)
    {
        auto vars = mpSpatialReusePass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]                = pVBuffer;
        vars["gReservoirs"]             = mpReservoirBuffer;
        vars["gSecondaryHits"]          = mpSecondaryHitBuffer;
        vars["PerFrameCB"]["gFrameDim"]       = mFrameDim;
        vars["PerFrameCB"]["gSpatialRadius"]  = mReSTIRParams.spatialRadius;
        vars["PerFrameCB"]["gFrameCount"]     = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]         = camPos;

        // VisCache bindings (ignored if USE_VISCACHE == 0)
        if (isVisCacheActive() && mpVisCacheTable)
        {
            bindVisCacheToPass(mpSpatialReusePass);
        }

        mpSpatialReusePass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // ----------------------------------------------------------------
    // Pass 4: Final shading — evaluate selected sample, write output
    // ----------------------------------------------------------------
    {
        auto vars = mpFinalShadingPass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gVBuffer"]            = pVBuffer;
        vars["gReservoirs"]         = mpReservoirBuffer;
        vars["gSecondaryHits"]      = mpSecondaryHitBuffer;
        vars["gColorOutput"]        = pColorOutput;
        vars["PerFrameCB"]["gFrameDim"]   = mFrameDim;
        vars["PerFrameCB"]["gFrameCount"] = mFrameCount;
        vars["PerFrameCB"]["gCamPos"]     = camPos;

        mpFinalShadingPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // ----------------------------------------------------------------
    // Swap reservoir buffers for next frame's temporal reuse
    // ----------------------------------------------------------------
    std::swap(mpReservoirBuffer, mpPrevReservoirBuffer);
    mFrameCount++;
}

// ============================================================================
// Retrieve VisCache hash table from InternalDictionary
// ============================================================================
void ReSTIRGIPass::retrieveVisCacheBuffers(const RenderData& rd)
{
    const auto& dict = rd.getDictionary();

    // Dictionary keys match VisCache.cpp::execute() exports
    if (isVisCacheActive() &&
        dict.keyExists("vhfTable") && dict.keyExists("vhfCapacity"))
    {
        mpVisCacheTable       = dict["vhfTable"];
        mVisCacheCapacity     = dict["vhfCapacity"];
        mVisCacheVarThreshold = dict.keyExists("vhfVarThreshold")
            ? dict["vhfVarThreshold"].operator float() : mVisCacheParams.contribThreshold;
        mVisCachePMin         = dict.keyExists("vhfPMin")
            ? dict["vhfPMin"].operator float() : mVisCacheParams.pMin;
        mVisCacheBootThreshold = dict.keyExists("vhfBootThreshold")
            ? dict["vhfBootThreshold"].operator uint32_t() : 32u;
        mVisCacheFireflyBudget = dict.keyExists("vhfFireflyBudget")
            ? dict["vhfFireflyBudget"].operator float() : mVisCacheParams.contribThreshold;
    }
    else
    {
        mpVisCacheTable        = nullptr;
        mVisCacheCapacity      = 0u;
        mVisCacheVarThreshold  = 0.1f;
        mVisCachePMin          = 0.05f;
        mVisCacheBootThreshold = 32u;
        mVisCacheFireflyBudget = 0.05f;
        if (isVisCacheActive())
            logWarning("ReSTIRGIPass: VisCache buffers not found in dictionary. "
                       "Ensure VisCache runs before ReSTIRGIPass in the render graph.");
    }
}

// ============================================================================
// Bind VisCache buffers to the spatial reuse pass
// ============================================================================
void ReSTIRGIPass::bindVisCacheToPass(const ref<ComputePass>& pass)
{
    // Binding names must match VisCache.slang declarations:
    //   RWStructuredBuffer<VHFEntry> gVHFTable;
    //   cbuffer VisCacheParams { gTableCapacity, gBootThreshold,
    //       gVarThreshold, gPMin, gFireflyBudget, ... };
    auto vars = pass->getRootVar();
    vars["gVHFTable"]                              = mpVisCacheTable;
    vars["VisCacheParams"]["gTableCapacity"]        = mVisCacheCapacity;
    vars["VisCacheParams"]["gBootThreshold"]         = mVisCacheBootThreshold;
    vars["VisCacheParams"]["gVarThreshold"]          = mVisCacheVarThreshold;
    vars["VisCacheParams"]["gPMin"]                  = mVisCachePMin;
    vars["VisCacheParams"]["gFireflyBudget"]         = mVisCacheFireflyBudget;
}

// ============================================================================
// Scene binding
// ============================================================================
void ReSTIRGIPass::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    mFrameCount = 0u;
}

// ============================================================================
// UI
// ============================================================================
void ReSTIRGIPass::renderUI(Gui::Widgets& widget)
{
    widget.text("ReSTIR GI + VisCache Revalidation");
    widget.separator();

    bool dirty = false;

    // ReSTIR params
    dirty |= widget.var("Spatial neighbors (k)", mReSTIRParams.numSpatialNeighbors, 1u, 16u);
    dirty |= widget.var("Spatial radius (px)",   mReSTIRParams.spatialRadius, 5.0f, 100.0f, 1.0f);
    dirty |= widget.checkbox("Temporal reuse",   mReSTIRParams.enableTemporalReuse);
    dirty |= widget.checkbox("Spatial reuse",    mReSTIRParams.enableSpatialReuse);
    dirty |= widget.checkbox("Talbot MIS",       mReSTIRParams.enableMIS);
    widget.separator();

    // VisCache integration — independently toggleable for ablation
    widget.text("VisCache (ablation toggles)");
    dirty |= widget.checkbox("CV+RRR revalidation (S11.3)", mVisCacheParams.enableRevalidation);
    dirty |= widget.checkbox("Light selection (S11.1)",      mVisCacheParams.enableLightSelection);
    if (isVisCacheActive())
    {
        widget.var("Contrib threshold",   mVisCacheParams.contribThreshold, 0.001f, 0.5f, 0.005f);
        widget.var("pMin (RR floor)",     mVisCacheParams.pMin,             0.01f,  0.5f, 0.005f);
        widget.checkbox("Symmetric cells (GI)", mVisCacheParams.symmetricCells);
    }

    if (dirty) createPasses();  // recompile with updated defines
}

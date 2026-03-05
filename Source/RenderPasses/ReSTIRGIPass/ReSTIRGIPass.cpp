/***************************************************************************
 * ReSTIRGIPass.cpp
 *
 * Falcor 8.0 implementation — ReSTIR GI with VisCache revalidation.
 *
 * This is a port sketch of DQLin/ReSTIR_PT to Falcor 8.0. The core
 * reservoir logic (initial sampling, temporal reuse, spatial reuse,
 * final shading) follows DQLin's original structure. The VisCache
 * integration replaces unconditional V(P,Q) shadow rays in spatial
 * reuse with CV+RRR gated calls (§11.3 / §12).
 *
 * TODO: Copy the full DQLin/ReSTIR_PT source into this skeleton.
 *       The upstream repo uses Falcor 5.2 — apply the API migration
 *       from docs/PORTING.md (global search-replace, ~30 min).
 ***************************************************************************/

#include "ReSTIRGIPass.h"

// Reservoir struct size: must match Slang PathReservoir (see DQLin source)
// secondaryHit (posW:12, N:12, Lo:12, invPDF:4) + reservoir (W:4, M:4, ...) = 64 bytes
static constexpr size_t kReservoirSize = 64u;

// Secondary hit data: posW:12, N:12, Lo:12, pad:28 = 64 bytes
static constexpr size_t kSecondaryHitSize = 64u;

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

    // Deserialise VisCache params
    if (props.has("visCacheEnabled"))         mVisCacheParams.enabled          = props["visCacheEnabled"];
    if (props.has("visCacheContribThreshold")) mVisCacheParams.contribThreshold = props["visCacheContribThreshold"];
    if (props.has("visCachePMin"))             mVisCacheParams.pMin             = props["visCachePMin"];
    if (props.has("visCacheSymmetricCells"))   mVisCacheParams.symmetricCells   = props["visCacheSymmetricCells"];
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

    p["visCacheEnabled"]          = mVisCacheParams.enabled;
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
    r.addInput("vbuffer", "Visibility buffer (hit data)");
    r.addInput("motionVectors", "Motion vectors for temporal reuse");

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
    defines.add("USE_VISCACHE", mVisCacheParams.enabled ? "1" : "0");
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

        mpInitialSamplingPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // ----------------------------------------------------------------
    // Pass 2: Temporal reuse
    // ----------------------------------------------------------------
    if (mReSTIRParams.enableTemporalReuse && mFrameCount > 0)
    {
        auto vars = mpTemporalReusePass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gReservoirs"]         = mpReservoirBuffer;
        vars["gPrevReservoirs"]     = mpPrevReservoirBuffer;
        vars["gSecondaryHits"]      = mpSecondaryHitBuffer;
        vars["gMotionVectors"]      = pMotionVec;
        vars["PerFrameCB"]["gFrameDim"] = mFrameDim;

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
        vars["gReservoirs"]         = mpReservoirBuffer;
        vars["gSecondaryHits"]      = mpSecondaryHitBuffer;
        vars["PerFrameCB"]["gFrameDim"]       = mFrameDim;
        vars["PerFrameCB"]["gSpatialRadius"]  = mReSTIRParams.spatialRadius;
        vars["PerFrameCB"]["gFrameCount"]     = mFrameCount;

        // VisCache bindings (ignored if USE_VISCACHE == 0)
        if (mVisCacheParams.enabled && mpVisCacheTable)
        {
            vars["gVisCacheTable"]      = mpVisCacheTable;
            vars["gTableCapacity"] = mVisCacheCapacity;
            vars["gVarThreshold"]  = mVisCacheParams.contribThreshold;
            vars["gPMin"]          = mVisCacheParams.pMin;
            vars["gFireflyBudget"] = mVisCacheParams.contribThreshold;
        }

        mpSpatialReusePass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
    }

    // ----------------------------------------------------------------
    // Pass 4: Final shading — evaluate selected sample, write output
    // ----------------------------------------------------------------
    {
        auto vars = mpFinalShadingPass->getRootVar();
        mpScene->bindShaderData(vars["gScene"]);
        vars["gReservoirs"]         = mpReservoirBuffer;
        vars["gSecondaryHits"]      = mpSecondaryHitBuffer;
        vars["gColorOutput"]        = pColorOutput;
        vars["PerFrameCB"]["gFrameDim"] = mFrameDim;

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

    if (mVisCacheParams.enabled &&
        dict.keyExists("vhfTable") && dict.keyExists("vhfCapacity"))
    {
        mpVisCacheTable   = dict["vhfTable"];
        mVisCacheCapacity = dict["vhfCapacity"];
    }
    else
    {
        mpVisCacheTable   = nullptr;
        mVisCacheCapacity = 0u;
        if (mVisCacheParams.enabled)
            logWarning("ReSTIRGIPass: VisCache buffers not found in dictionary. "
                       "Ensure VisCache runs before ReSTIRGIPass in the render graph.");
    }
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

    // VisCache integration
    widget.checkbox("VisCache revalidation", mVisCacheParams.enabled);
    if (mVisCacheParams.enabled)
    {
        widget.var("Contrib threshold",   mVisCacheParams.contribThreshold, 0.001f, 0.5f, 0.005f);
        widget.var("pMin (RR floor)",     mVisCacheParams.pMin,             0.01f,  0.5f, 0.005f);
        widget.checkbox("Symmetric cells (GI)", mVisCacheParams.symmetricCells);
    }

    if (dirty) createPasses();  // recompile with updated defines
}

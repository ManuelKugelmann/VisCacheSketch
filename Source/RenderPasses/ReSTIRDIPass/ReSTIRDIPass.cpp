/***************************************************************************
 * ReSTIRDIPass.cpp
 *
 * Falcor 8.0 implementation — ReSTIR DI via RTXDI with VisCache modes.
 *
 * Three modes:
 *   Vanilla:  Delegates entirely to Falcor's RTXDI. Bit-identical to
 *             RTXDIPass — serves as reference baseline.
 *   VisCache: Final shading shadow rays gated by CV+RRR (§11.3).
 *             RTXDI runs normally; only the V(P,L) query changes.
 *   LightSel: RTXDI target function weighted by cached mu (§11.1),
 *             plus CV+RRR gated shadow rays.
 *
 * The mode is controlled by a single enum property and UI toggle.
 ***************************************************************************/

#include "ReSTIRDIPass.h"

// ============================================================================
// Plugin registration
// ============================================================================
extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, ReSTIRDIPass>();
}

// ============================================================================
// Construction
// ============================================================================
ReSTIRDIPass::ReSTIRDIPass(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    if (props.has("mode")) mMode = Mode(props["mode"].operator uint32_t());
}

ref<ReSTIRDIPass> ReSTIRDIPass::create(ref<Device> pDevice, const Properties& props)
{
    return make_ref<ReSTIRDIPass>(pDevice, props);
}

// ============================================================================
// Properties
// ============================================================================
Properties ReSTIRDIPass::getProperties() const
{
    Properties p;
    p["mode"] = uint32_t(mMode);
    return p;
}

// ============================================================================
// Reflect: same I/O as Falcor's RTXDIPass
// ============================================================================
RenderPassReflection ReSTIRDIPass::reflect(const CompileData& compileData)
{
    RenderPassReflection r;
    r.addInput("vbuffer", "Visibility buffer (packed hit info)");
    r.addInput("motionVectors", "Motion vectors for temporal reuse")
        .flags(RenderPassReflection::Field::Flags::Optional);
    r.addOutput("color", "Direct illumination").format(ResourceFormat::RGBA32Float);
    return r;
}

// ============================================================================
// Compile
// ============================================================================
void ReSTIRDIPass::compile(RenderContext* pCtx, const CompileData& compileData)
{
    mFrameDim = compileData.defaultTexDims;

    DefineList defines;
    defines.add("USE_VISCACHE", (mMode != Mode::Vanilla) ? "1" : "0");
    defines.add("USE_VISCACHE_LIGHTSEL", (mMode == Mode::LightSel) ? "1" : "0");

    // PrepareSurfaceData pass — sets up surface info for RTXDI
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRDIPass/PrepareSurfaceData.cs.slang")
            .csEntry("csPrepareSurfaceData");
        mpPrepareSurfaceDataPass = ComputePass::create(mpDevice, desc, defines);
    }

    // Final shading pass — evaluates selected light sample with BSDF + visibility
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/ReSTIRDIPass/FinalShading.cs.slang")
            .csEntry("csFinalShading");
        mpFinalShadingPass = ComputePass::create(mpDevice, desc, defines);
    }
}

// ============================================================================
// Execute
// ============================================================================
void ReSTIRDIPass::execute(RenderContext* pCtx, const RenderData& rd)
{
    if (!mpScene || !mpRTXDI) return;

    auto pVBuffer = rd.getTexture("vbuffer");
    auto pColor   = rd.getTexture("color");
    if (!pVBuffer || !pColor) return;

    // Retrieve VisCache buffers if in VisCache/LightSel mode
    if (mMode != Mode::Vanilla)
        retrieveVisCacheBuffers(rd);

    // Step 1: Prepare surface data for RTXDI
    prepareSurfaceData(pCtx, pVBuffer);

    // Step 2: Run RTXDI (initial candidates, temporal reuse, spatial reuse)
    // This is Falcor's built-in RTXDI pipeline — vanilla ReSTIR DI.
    mpRTXDI->update(pCtx, rd.getTexture("motionVectors"));

    // Step 3: Final shading (evaluate BSDF * Li * V for selected samples)
    // In VisCache mode, V(P,L) is replaced by CV+RRR gated visibility.
    finalShading(pCtx, pVBuffer, rd);
}

// ============================================================================
void ReSTIRDIPass::prepareSurfaceData(RenderContext* pCtx, const ref<Texture>& pVBuffer)
{
    FALCOR_ASSERT(mpPrepareSurfaceDataPass && mpRTXDI);

    auto vars = mpPrepareSurfaceDataPass->getRootVar();
    mpScene->bindShaderData(vars["gScene"]);
    vars["gVBuffer"] = pVBuffer;
    mpRTXDI->setShaderData(vars);

    mpPrepareSurfaceDataPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
}

// ============================================================================
void ReSTIRDIPass::finalShading(RenderContext* pCtx, const ref<Texture>& pVBuffer,
                                 const RenderData& rd)
{
    FALCOR_ASSERT(mpFinalShadingPass && mpRTXDI);

    auto vars = mpFinalShadingPass->getRootVar();
    mpScene->bindShaderData(vars["gScene"]);
    vars["gVBuffer"]     = pVBuffer;
    vars["gColorOutput"] = rd.getTexture("color");
    mpRTXDI->setShaderData(vars);

    vars["PerFrameCB"]["gFrameDim"] = mFrameDim;

    // Bind VisCache if enabled
    if (mMode != Mode::Vanilla && mpVisCacheTable)
        bindVisCacheToPass(mpFinalShadingPass);

    mpFinalShadingPass->execute(pCtx, mFrameDim.x, mFrameDim.y, 1u);
}

// ============================================================================
void ReSTIRDIPass::retrieveVisCacheBuffers(const RenderData& rd)
{
    const auto& dict = rd.getDictionary();

    if (dict.keyExists("vhfTable") && dict.keyExists("vhfCapacity"))
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
    }
    else
    {
        mpVisCacheTable = nullptr;
        mVisCacheCapacity = 0u;
        if (mMode != Mode::Vanilla)
            logWarning("ReSTIRDIPass: VisCache buffers not found. "
                       "Ensure VisCache runs before ReSTIRDIPass.");
    }
}

// ============================================================================
void ReSTIRDIPass::bindVisCacheToPass(const ref<ComputePass>& pass)
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
void ReSTIRDIPass::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    if (mpScene)
        mpRTXDI = std::make_unique<RTXDI>(mpScene, mRTXDIOptions);
    else
        mpRTXDI.reset();
}

// ============================================================================
void ReSTIRDIPass::renderUI(Gui::Widgets& widget)
{
    widget.text("ReSTIR DI (RTXDI) + VisCache");
    widget.separator();

    // Mode selector
    static const Gui::DropdownList kModes = {
        {0, "Vanilla (no VisCache)"},
        {1, "VisCache (CV+RRR shadow gating)"},
        {2, "VisCache + Light Selection"},
    };
    uint32_t mode = uint32_t(mMode);
    if (widget.dropdown("Mode", kModes, mode))
    {
        mMode = Mode(mode);
        mOptionsChanged = true;
    }

    widget.separator();

    // RTXDI options (delegated to Falcor's RTXDI UI)
    if (mpRTXDI)
    {
        bool changed = false;
        mpRTXDI->renderUI(widget, changed);
        mOptionsChanged |= changed;
    }
}

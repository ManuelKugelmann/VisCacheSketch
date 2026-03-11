/***************************************************************************
 * ReSTIRDIPass.h
 *
 * Falcor 8.0 RenderPass — ReSTIR DI with optional VisCache integration.
 *
 * Wraps Falcor's built-in RTXDI module. Three modes:
 *   1. Vanilla:   Standard RTXDI (ReSTIR DI) — no VisCache.
 *   2. VisCache:  Shadow rays in final shading gated by CV+RRR (§11.3).
 *   3. LightSel:  RTXDI target function uses cached mu for light
 *                 candidate weighting (§11.1), plus CV+RRR shadow gating.
 *
 * Vanilla mode mirrors Falcor's RTXDIPass pipeline — useful as a
 * reference baseline for ablation studies.
 ***************************************************************************/

#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "Rendering/RTXDI/RTXDI.h"

using namespace Falcor;

class ReSTIRDIPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ReSTIRDIPass, "ReSTIRDIPass",
                        "ReSTIR DI (RTXDI) with optional VisCache integration");

    static ref<ReSTIRDIPass> create(ref<Device> pDevice, const Properties& props);

    // RenderPass interface (Falcor 8.0)
    Properties           getProperties() const override;
    RenderPassReflection reflect(const CompileData& compileData) override;
    void                 compile(RenderContext* pCtx, const CompileData& compileData) override;
    void                 execute(RenderContext* pCtx, const RenderData& rd) override;
    void                 renderUI(Gui::Widgets& widget) override;
    void                 setScene(RenderContext* pCtx, const ref<Scene>& pScene) override;

    // -----------------------------------------------------------------------
    // VisCache integration — individually toggleable for ablation
    // -----------------------------------------------------------------------
    struct VisCacheFlags
    {
        bool enableVisCacheRevalidation    = false;  ///< CV+RRR shadow ray gating (§11.3)
        bool enableVisCacheLightSelection  = false;  ///< Cached mu in target function (§11.1)
    };

    bool isVisCacheActive() const { return mVisCacheFlags.enableVisCacheRevalidation || mVisCacheFlags.enableVisCacheLightSelection; }

    ReSTIRDIPass(ref<Device> pDevice, const Properties& props);

private:
    void prepareSurfaceData(RenderContext* pCtx, const ref<Texture>& pVBuffer);
    void finalShading(RenderContext* pCtx, const ref<Texture>& pVBuffer, const RenderData& rd);
    void retrieveVisCacheBuffers(const RenderData& rd);
    void bindVisCacheToPass(const ref<ComputePass>& pass);

    // -----------------------------------------------------------------------
    // RTXDI (Falcor's built-in ReSTIR DI implementation)
    // -----------------------------------------------------------------------
    std::unique_ptr<RTXDI>  mpRTXDI;
    RTXDI::Options          mRTXDIOptions;

    ref<ComputePass>  mpPrepareSurfaceDataPass;
    ref<ComputePass>  mpFinalShadingPass;

    // -----------------------------------------------------------------------
    // VisCache integration
    // -----------------------------------------------------------------------
    VisCacheFlags     mVisCacheFlags;
    ref<Buffer>       mpVisCacheTable;
    uint32_t          mVisCacheCapacity      = 0u;
    float             mVisCacheVarThreshold  = 0.1f;
    float             mVisCachePMin          = 0.05f;
    uint32_t          mVisCacheBootThreshold = 32u;
    float             mVisCacheFireflyBudget = 0.05f;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    ref<Scene>        mpScene;
    uint2             mFrameDim = { 0, 0 };
    bool              mOptionsChanged = false;
};

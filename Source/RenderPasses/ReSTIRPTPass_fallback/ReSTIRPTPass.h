/***************************************************************************
 * ReSTIRPTPass.h
 *
 * Falcor 8.0 RenderPass — ReSTIR PT (path tracing with path reuse).
 *
 * Extends ReSTIRGIPass from single-bounce to multi-bounce path reuse,
 * following DQLin's "Generalized Resampled Importance Sampling:
 * Foundations of ReSTIR" (SIGGRAPH 2022).
 *
 * Key difference from ReSTIRGIPass:
 *   - GI: stores one secondary hit, reconnects at bounce 1.
 *   - PT: stores a reconnection vertex at any bounce depth,
 *         carries full path prefix throughput.
 *
 * VisCache modes (independently toggleable for ablation):
 *   - Vanilla:           No VisCache. Standard ReSTIR PT.
 *   - LightSel:          Cached mu for light candidate weighting (S11.1).
 *   - CV+RRR:            Revalidation ray gating at reconnection (S11.3).
 *   - LightSel + CV+RRR: Full VisCache integration.
 ***************************************************************************/

#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "Core/Pass/ComputePass.h"

using namespace Falcor;

class ReSTIRPTPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ReSTIRPTPass, "ReSTIRPTPass",
                        "ReSTIR PT (multi-bounce) with VisCache integration");

    static ref<ReSTIRPTPass> create(ref<Device> pDevice, const Properties& props);

    Properties           getProperties() const override;
    RenderPassReflection reflect(const CompileData& compileData) override;
    void                 compile(RenderContext* pCtx, const CompileData& compileData) override;
    void                 execute(RenderContext* pCtx, const RenderData& rd) override;
    void                 renderUI(Gui::Widgets& widget) override;
    void                 setScene(RenderContext* pCtx, const ref<Scene>& pScene) override;

    // -----------------------------------------------------------------------
    // ReSTIR PT parameters
    // -----------------------------------------------------------------------
    struct Params
    {
        uint32_t maxBounces          = 4;       ///< Max path depth (1 = GI only)
        uint32_t numSpatialNeighbors = 5;       ///< k in spatial reuse
        float    spatialRadius       = 30.0f;   ///< Screen-space pixel radius
        bool     enableTemporalReuse = true;
        bool     enableSpatialReuse  = true;
        bool     enableMIS           = true;
    };

    // -----------------------------------------------------------------------
    // VisCache integration — each feature independently toggleable
    // -----------------------------------------------------------------------
    struct VisCacheFlags
    {
        bool     enableVisCacheLightSelection = false;  ///< S11.1: cached mu in target func
        bool     enableVisCacheRevalidation   = false;  ///< S11.3: CV+RRR via VisCache hash table
        bool     enableCVRRRRevalidation      = false;  ///< CV+RRR via reservoir-local mu (no hash table)
        float    contribThreshold             = 0.01f;  ///< Minimum residual to force trace
        float    pMin                         = 0.05f;  ///< RR floor for revalidation
    };

    bool isVisCacheActive() const { return mVisCacheFlags.enableVisCacheRevalidation || mVisCacheFlags.enableVisCacheLightSelection; }
    bool isAnyRevalActive() const { return mVisCacheFlags.enableVisCacheRevalidation || mVisCacheFlags.enableCVRRRRevalidation; }

    ReSTIRPTPass(ref<Device> pDevice, const Properties& props);

private:
    void createPasses();
    void retrieveVisCacheBuffers(const RenderData& rd);
    void bindVisCacheToPass(const ref<ComputePass>& pass);

    // -----------------------------------------------------------------------
    // Compute passes (same structure as ReSTIRGIPass, extended for multi-bounce)
    // -----------------------------------------------------------------------
    ref<ComputePass>  mpInitialSamplingPass;
    ref<ComputePass>  mpTemporalReusePass;
    ref<ComputePass>  mpSpatialReusePass;
    ref<ComputePass>  mpFinalShadingPass;

    // -----------------------------------------------------------------------
    // Reservoir buffers (sizes determined by Slang reflection at compile time)
    // -----------------------------------------------------------------------
    ref<Buffer>       mpReservoirBuffer;
    ref<Buffer>       mpPrevReservoirBuffer;
    ref<Buffer>       mpSecondaryHitBuffer;

    // -----------------------------------------------------------------------
    // VisCache
    // -----------------------------------------------------------------------
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
    Params            mParams;
    VisCacheFlags     mVisCacheFlags;
    uint2             mFrameDim = { 0, 0 };
    uint32_t          mFrameCount = 0u;
};

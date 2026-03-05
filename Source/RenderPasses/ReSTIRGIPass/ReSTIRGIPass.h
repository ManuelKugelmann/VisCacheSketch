/***************************************************************************
 * ReSTIRGIPass.h
 *
 * Falcor 8.0 RenderPass — ReSTIR GI with VisCache CV+RRR revalidation.
 *
 * Port of DQLin/ReSTIR_PT (Falcor 5.2) to Falcor 8.0 with integrated
 * visibility cache for revalidation ray gating (§11.3).
 *
 * Port checklist (Falcor 5.2 → 8.0):
 *   [x] SharedPtr<X>  → ref<X>
 *   [x] Program::Desc → ProgramDesc
 *   [x] Shader::DefineList → DefineList
 *   [x] Scene::SharedPtr → ref<Scene>
 *   [x] Buffer::createStructured() → device->createStructuredBuffer()
 *   [x] RenderPass::compile() takes const CompileData&
 *   [x] Dictionary → InternalDictionary
 *   [x] Gui::Window → Gui::Widgets
 *   [x] flush() → submit(false)
 *   [x] Plugin registration: FALCOR_PLUGIN_CLASS + registerPlugin
 ***************************************************************************/

#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "Core/Pass/ComputePass.h"

using namespace Falcor;

class ReSTIRGIPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ReSTIRGIPass, "ReSTIRGIPass",
                        "ReSTIR GI with VisCache CV+RRR revalidation");

    static ref<ReSTIRGIPass> create(ref<Device> pDevice, const Properties& props);

    // RenderPass interface (Falcor 8.0 signatures)
    Properties           getProperties() const override;
    RenderPassReflection reflect(const CompileData& compileData) override;
    void                 compile(RenderContext* pCtx, const CompileData& compileData) override;
    void                 execute(RenderContext* pCtx, const RenderData& rd) override;
    void                 renderUI(Gui::Widgets& widget) override;
    void                 setScene(RenderContext* pCtx, const ref<Scene>& pScene) override;

    // -----------------------------------------------------------------------
    // ReSTIR GI parameters (ported from DQLin/ReSTIR_PT)
    // -----------------------------------------------------------------------
    struct ReSTIRParams
    {
        uint32_t numSpatialNeighbors = 5;      ///< k in spatial reuse
        float    spatialRadius       = 30.0f;   ///< Screen-space pixel radius
        uint32_t numTemporalSamples  = 1;       ///< Temporal reuse candidates
        bool     enableTemporalReuse = true;
        bool     enableSpatialReuse  = true;
        bool     enableMIS           = true;    ///< Talbot MIS for spatial
    };

    // -----------------------------------------------------------------------
    // VisCache integration parameters (§11.3 / §12)
    // -----------------------------------------------------------------------
    struct VisCacheParams
    {
        bool     enabled              = true;
        float    contribThreshold     = 0.01f;  ///< Minimum residual to force trace
        float    pMin                 = 0.05f;  ///< RR floor for revalidation
        bool     symmetricCells       = false;  ///< Use symmetric cell sizes for GI (§5.2)
    };

    ReSTIRGIPass(ref<Device> pDevice, const Properties& props);

private:
    void createPasses();
    void retrieveVisCacheBuffers(const RenderData& rd);

    // -----------------------------------------------------------------------
    // Compute passes
    // -----------------------------------------------------------------------
    ref<ComputePass>  mpInitialSamplingPass;
    ref<ComputePass>  mpTemporalReusePass;
    ref<ComputePass>  mpSpatialReusePass;
    ref<ComputePass>  mpFinalShadingPass;

    // -----------------------------------------------------------------------
    // Reservoir buffers
    // -----------------------------------------------------------------------
    ref<Buffer>       mpReservoirBuffer;       ///< Current-frame reservoirs
    ref<Buffer>       mpPrevReservoirBuffer;   ///< Previous-frame (temporal)
    ref<Buffer>       mpSecondaryHitBuffer;    ///< Secondary hit data (Lo, posW, N)

    // -----------------------------------------------------------------------
    // VisCache: retrieved from InternalDictionary each frame
    // -----------------------------------------------------------------------
    ref<Buffer>       mpVisCacheTable;
    uint32_t          mVisCacheCapacity = 0u;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    ref<Scene>        mpScene;
    ReSTIRParams      mReSTIRParams;
    VisCacheParams       mVisCacheParams;
    uint2             mFrameDim = { 0, 0 };
    uint32_t          mFrameCount = 0u;
};

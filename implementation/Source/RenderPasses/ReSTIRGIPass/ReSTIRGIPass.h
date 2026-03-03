/***************************************************************************
 * ReSTIRGIPass.h  (patched delta — port of DQLin/ReSTIR_PT to Falcor 8.0)
 *
 * This file shows ONLY the additions required to integrate MLVHF.
 * Start from the full DQLin/ReSTIR_PT source and apply these changes.
 *
 * Port checklist (Falcor 5.2 → 8.0):
 *   [ ] SharedPtr<X>  → ref<X>       (global search-replace)
 *   [ ] Program::Desc → ProgramDesc  (constructor syntax changed)
 *   [ ] Shader::DefineList → DefineList (moved namespace)
 *   [ ] Scene::SharedPtr → ref<Scene>
 *   [ ] Buffer::createStructured() signature updated (see Falcor 8 docs)
 *   [ ] RenderPass::compile() signature now takes const CompileData&
 *   [ ] Dictionary → InternalDictionary in RenderData
 ***************************************************************************/

#pragma once
#include "Falcor.h"
using namespace Falcor;

class ReSTIRGIPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ReSTIRGIPass, "ReSTIRGIPass",
                        "ReSTIR GI with MLVHF CV+RRR revalidation");

    static ref<ReSTIRGIPass> create(ref<Device> pDevice, const Properties& props);

    Properties      getProperties()                                    const override;
    RenderPassReflection reflect(const CompileData& compileData)             override;
    void            execute(RenderContext* pCtx, const RenderData& rd)       override;
    void            renderUI(Gui::Widgets& widget)                           override;
    void            setScene(RenderContext* pCtx, const ref<Scene>& pScene)  override;

    // -----------------------------------------------------------------------
    // MLVHF additions (all other members unchanged from DQLin/ReSTIR_PT)
    // -----------------------------------------------------------------------
    struct MLVHFParams
    {
        bool     enabled              = true;
        float    contribThreshold     = 0.01f;  ///< Minimum residual to force trace
        float    pMin                 = 0.05f;  ///< RR floor for revalidation
        bool     symmetricCells       = false;  ///< Use symmetric cell sizes for GI (§5.2)
    };

private:
    ReSTIRGIPass(ref<Device> pDevice, const Properties& props);

    // Original DQLin members (keep as-is) ...

    // MLVHF: retrieved from InternalDictionary each frame
    ref<Buffer>  mpVHFTable;
    uint32_t     mVHFCapacity = 0u;

    MLVHFParams  mMLVHFParams;

    void retrieveVHFBuffers(const RenderData& rd);
};

/***************************************************************************
 * SHaRCPass.h
 *
 * Falcor 8.0 RenderPass — SHaRC (Spatial Hash Radiance Cache)
 * Minimal Slang port of NVIDIA RTXGI SHaRC v1.6.5.
 *
 * Owns the three GPU buffers (hash entries, accumulation, resolved).
 * Runs the resolve compute pass each frame.
 * Exports buffers + parameters to downstream passes via InternalDictionary.
 ***************************************************************************/

#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "Core/Pass/ComputePass.h"

using namespace Falcor;

class SHaRCPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(SHaRCPass, "SHaRCPass",
                        "SHaRC radiance cache (NVIDIA RTXGI v1.6.5 Slang port)");

    static ref<SHaRCPass> create(ref<Device> pDevice,
                                 const Properties& props);

    // RenderPass interface
    Properties getProperties() const override;
    void setProperties(const Properties& props) override;
    RenderPassReflection reflect(const CompileData& compileData) override;
    void compile(RenderContext* pRenderContext,
                 const CompileData& compileData) override;
    void execute(RenderContext* pRenderContext,
                 const RenderData& renderData) override;
    void renderUI(Gui::Widgets& widget) override;
    void setScene(RenderContext* pRenderContext,
                  const ref<Scene>& pScene) override;

    struct Params
    {
        uint32_t capacity           = 1u << 22u;    ///< Hash map capacity (power-of-two)
        float    sceneScale         = 50.0f;        ///< Controls voxel size scaling
        float    radianceScale      = 1000.0f;      ///< Quantization factor for atomic radiance accumulation
        uint32_t accumulationFrameNum = 128u;       ///< Temporal accumulation window (frames)
        uint32_t staleFrameNumMax   = 128u;         ///< Eviction threshold (frames without samples)
        float    levelBias          = 0.0f;         ///< LOD bias
        bool     enableAntiFirefly  = true;
    };

    const Params& getParams() const { return mParams; }

    SHaRCPass(ref<Device> pDevice, const Properties& props);

private:
    void allocateBuffers();
    void autoTuneSceneScale();

    // ------------------------------------------------------------------
    // GPU resources — match SHaRC's 3-buffer layout
    // ------------------------------------------------------------------
    ref<Buffer> mpHashEntries;       ///< RWStructuredBuffer<uint64_t> — hash keys
    ref<Buffer> mpAccumulation;      ///< RWStructuredBuffer<SharcAccumulationData> — per-frame radiance
    ref<Buffer> mpResolved;          ///< RWStructuredBuffer<SharcPackedData> — temporally resolved
    ref<Buffer> mpLockBuffer;        ///< RWStructuredBuffer<uint> — spinlock fallback (if no 64-bit atomics)

    ref<ComputePass> mpResolvePass;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    Params      mParams;
    ref<Scene>  mpScene;
    uint32_t    mFrameCount = 0u;
    float3      mCameraPositionPrev = float3(0.f);
};

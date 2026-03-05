/***************************************************************************
 * VisHashFilter.h
 *
 * Falcor 8.0 RenderPass — Multilevel Visibility Hash Filter
 *
 * Owns the hash table buffer and stats buffer.
 * Exposes both to downstream passes via InternalDictionary.
 * Runs the optional background decay sweep each frame.
 * Auto-tunes decayPeriod via a PI controller on load pressure.
 ***************************************************************************/

#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "Core/Pass/ComputePass.h"

using namespace Falcor;

class VisHashFilter : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(VisHashFilter, "VisHashFilter",
                        "Multilevel Visibility Hash Filter (Kugelmann 2026)");

    static ref<VisHashFilter> create(ref<Device> pDevice,
                                     const Properties& props);

    // RenderPass interface
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData& compileData) override;
    void compile(RenderContext* pRenderContext,
                 const CompileData& compileData) override;
    void execute(RenderContext* pRenderContext,
                 const RenderData& renderData) override;
    void renderUI(Gui::Widgets& widget) override;
    void setScene(RenderContext* pRenderContext,
                  const ref<Scene>& pScene) override;

    // ------------------------------------------------------------------
    // Parameters (exposed to UI and Python scripting)
    // ------------------------------------------------------------------
    struct Params
    {
        uint32_t tableCapacity   = 1u << 22u;  ///< 4M entries = 32 MB
        uint32_t bootThreshold   = 32u;         ///< Min samples before trusting entry
        float    varThreshold    = 0.10f;       ///< Variance gate for write depth
        float    pMin            = 0.05f;       ///< Min RR survival probability
        float    fireflyBudget   = 0.05f;       ///< Adaptive pMin scale
        uint32_t decayPeriod     = 300u;        ///< Frames per full table sweep (0=off)
        uint32_t decayPeriodMax  = 600u;        ///< PI controller ceiling
        bool     enableGIRevalidation  = true;
        bool     enableLightSelection  = true;
        bool     enableWarpReduction   = true;  ///< SM 6.5 WaveMatch (disable for ablation C)
        bool     enableVarianceGate    = true;  ///< Ablation B
        bool     enableDistanceLOD     = true;  ///< Ablation A
        bool     enableDecay           = true;  ///< Ablation D
        bool     enablePressureEvict   = true;  ///< Ablation E
        int      minLevel              = 0;     ///< For finest-only: set to 2
        int      maxLevel              = 2;     ///< For coarsest-only: set to 0
    };

    const Params& getParams() const { return mParams; }

private:
    VisHashFilter(ref<Device> pDevice, const Properties& props);

    void allocateBuffers();
    void runDecayPass(RenderContext* pCtx);
    void readbackStats(RenderContext* pCtx);
    void autoTuneDecayPeriod();

    // ------------------------------------------------------------------
    // GPU resources
    // ------------------------------------------------------------------
    ref<Buffer>         mpHashTable;     ///< RWStructuredBuffer<VHFEntry>
    ref<Buffer>         mpStatsBuffer;   ///< 5x uint32 atomic counters
    ref<Buffer>         mpStagingBuffer; ///< CPU readback for stats

    ref<ComputePass>    mpDecayPass;
    ref<ComputePass>    mpStatsPass;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    Params   mParams;
    uint32_t mFrameCount = 0u;

    // Stats (readback with 4-frame delay)
    struct Stats
    {
        float hitRate     = 0.f;
        float raySavings  = 0.f;
        float loadFactor  = 0.f;
        float avgProbeLen = 0.f;
        float evictRate   = 0.f;
    } mStats;

    // PI controller state for decayPeriod auto-tuning
    float mPIIntegral      = 0.f;
    float mTargetLoadPressure = 0.1f;  ///< Target eviction/insert ratio
};

/***************************************************************************
 * VisCache.h
 *
 * Falcor 8.0 RenderPass — Visibility Cache
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

class VisCache : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(VisCache, "VisCachePass",
                        "Visibility Cache (Kugelmann 2026)");

    static ref<VisCache> create(ref<Device> pDevice,
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

    /// GPU constant buffer layout — must match VisCacheParams in VisCache.slang exactly.
    /// Exported via InternalDictionary as "vhfParamsCB" so downstream passes
    /// bind it with a single line: rootVar["VisCacheParams"] = dict["vhfParamsCB"].
    struct GPUParams
    {
        uint32_t tableCapacity;
        uint32_t bootThreshold;
        float    varThreshold;
        float    pMin;
        float    fireflyBudget;
        uint32_t numLevels;
        float    cellCoarse;
        float    cellFine;
    };
    static_assert(sizeof(GPUParams) == 32, "GPUParams must match VisCacheParams cbuffer (32 bytes)");

    struct Params
    {
        uint32_t tableCapacity   = 1u << 22u;  ///< 4M entries = 32 MB
        uint32_t bootThreshold   = 32u;         ///< Min samples before trusting entry
        float    varThreshold    = 0.10f;       ///< Variance gate for write depth
        float    pMin            = 0.05f;       ///< Min RR survival probability
        float    fireflyBudget   = 0.05f;       ///< Adaptive pMin scale
        uint32_t numLevels       = 3u;          ///< Arbitrary N LOD levels
        float    cellCoarse      = 10.0f;       ///< Coarsest level cell size (world units, or auto-derived)
        float    cellFine        = 0.16f;       ///< Finest level cell size (world units, or auto-derived)
        bool     autoTuneCells   = true;        ///< Auto-derive cellCoarse/cellFine from scene
        uint32_t decayPeriod     = 300u;        ///< Frames per full table sweep (0=off)
        uint32_t decayPeriodMax  = 600u;        ///< PI controller ceiling
        bool     enableVisCacheRevalidation    = true;  ///< CV+RRR shadow ray gating (§11.3)
        bool     enableVisCacheLightSelection = true;  ///< Cached mu in target function (§11.1)
        bool     enableVisCacheWarpReduction  = true;  ///< SM 6.5 WaveMatch (ablation C)
        bool     enableVisCacheVarianceGate   = true;  ///< Ablation B
        bool     enableVisCacheDecay          = true;  ///< Ablation D
        bool     enableVisCachePressureEvict  = true;  ///< Ablation E
    };

    const Params& getParams() const { return mParams; }

    VisCache(ref<Device> pDevice, const Properties& props);

private:

    void allocateBuffers();
    void autoTuneCellSizes();    ///< Derive cellCoarse/cellFine from scene bounds + camera
    void runDecayPass(RenderContext* pCtx);
    void readbackStats(RenderContext* pCtx);
    void autoTuneDecayPeriod();

    // ------------------------------------------------------------------
    // GPU resources
    // ------------------------------------------------------------------
    ref<Buffer>         mpHashTable;     ///< RWStructuredBuffer<VHFEntry>
    ref<Buffer>         mpParamsBuffer;  ///< VisCacheParams cbuffer (32 bytes, exported via dict)
    ref<Buffer>         mpStatsBuffer;   ///< 5x uint32 atomic counters
    ref<Buffer>         mpStagingBuffer; ///< CPU readback for stats

    ref<ComputePass>    mpDecayPass;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    Params   mParams;
    ref<Scene> mpScene;          ///< Current scene (for bounds + camera)
    bool     mAutoTuneCells = true;  ///< Auto-derive cellCoarse/cellFine from scene
    uint32_t mFrameCount = 0u;

    // Stats (readback with 4-frame delay)
    struct Stats
    {
        float hitRate     = 0.f;
        float raySavings  = 0.f;
        float evictRate   = 0.f;
    } mStats;

    // PI controller state for decayPeriod auto-tuning
    float mPIIntegral      = 0.f;
    float mTargetLoadPressure = 0.1f;  ///< Target eviction/insert ratio
};

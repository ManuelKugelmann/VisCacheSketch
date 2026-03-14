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

// ---------------------------------------------------------------------------
// Diagnostic heatmap output channels.
// Downstream passes write to these via dictionary-exposed textures.
// Connect to ColorMapPass for visualization (channel R/G/B/A selects metric).
// ---------------------------------------------------------------------------
// vcDiag (RGBA32Float): R=cachedMu, G=variance, B=level+1(0=miss), A=raySaved
// vcDiagError (R32Float): |mu - V| prediction error
// ---------------------------------------------------------------------------

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
    struct Params
    {
        uint32_t tableCapacity   = 1u << 22u;  ///< 4M entries = 32 MB
        uint32_t bootThreshold   = 32u;         ///< Min samples before trusting entry
        float    varThreshold    = 0.10f;       ///< Variance gate for write depth
        float    pMin            = 0.05f;       ///< Min RR survival probability
        float    fireflyBudget   = 0.05f;       ///< Adaptive pMin scale
        uint32_t numLevels       = 3u;          ///< Arbitrary N LOD levels
        float    cellCoarse      = 10.0f;       ///< L0 cell size (world units)
        float    cellFine        = 0.16f;       ///< L_{N-1} cell size (world units)
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
        float evictRate   = 0.f;
    } mStats;

    // PI controller state for decayPeriod auto-tuning
    float mPIIntegral      = 0.f;
    float mTargetLoadPressure = 0.1f;  ///< Target eviction/insert ratio

    // ------------------------------------------------------------------
    // Diagnostic heatmap textures (written by downstream passes)
    // ------------------------------------------------------------------
    enum class DiagMode : uint32_t
    {
        Off             = 0,
        CachedMu        = 1,  ///< R channel — visibility prediction [0,1]
        Variance        = 2,  ///< G channel — cache uncertainty [0,0.25]
        LODLevel        = 3,  ///< B channel — LOD level+1 (0=miss)
        RaySaved        = 4,  ///< A channel — 1=skipped, 0=traced
        PredictionError = 5,  ///< |mu - V| from vcDiagError
    };

    bool            mEnableDiagnostics = false; ///< Master enable (auto-set by dropdown)
    DiagMode        mDiagMode = DiagMode::Off;  ///< Selected heatmap mode
    ref<Texture>    mpDiagTex;          ///< RGBA32F: mu, var, level, raySaved
    ref<Texture>    mpDiagErrorTex;     ///< R32F: prediction error |mu - V|
    ref<Texture>    mpDiagCompositeTex; ///< RGBA32F: composite (R=mu, G=level, B=N)
    uint2           mFrameDims = {0, 0};
};

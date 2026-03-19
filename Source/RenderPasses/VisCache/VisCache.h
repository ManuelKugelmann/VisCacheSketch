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
    void setProperties(const Properties& props) override;
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
        uint32_t enableJitter;
        float    cellACoarse;     ///< posA coarsest cell (world units)
        float    cellAFine;       ///< posA finest cell (auto-derived)
        float    cellBCoarse;     ///< posB coarsest cell (pos×pos modes)
        float    cellBFine;       ///< posB finest cell (auto-derived)
        float    angularBCoarse;  ///< direction coarsest cell (degrees, dirdist)
        float    angularBFine;    ///< direction finest cell (auto-derived)
        float    distBCoarse;     ///< distance coarsest cell (world units, dirdist)
        float    distBFine;       ///< distance finest cell (auto-derived)
        uint32_t _pad[1];
    };
    static_assert(sizeof(GPUParams) == 64, "GPUParams must match VisCacheParams cbuffer (64 bytes)");

    /// Full parameter set — includes GPU params + host-only knobs (decay, auto-tune,
    /// ablation toggles). Feature and ablation toggles are exported via InternalDictionary
    /// so downstream passes (ReSTIRPTPass) can read them and set compile-time defines.
    struct Params
    {
        // --- Hash table sizing ---
        uint32_t tableCapacity   = 1u << 22u;  ///< 4M entries = 32 MB (must be power-of-two)
        uint32_t bootThreshold   = 32u;         ///< Min samples before trusting entry (maturity gate)
        float    varThreshold    = 0.10f;       ///< Bernoulli variance gate for cascaded write depth
        float    pMin            = 0.05f;       ///< Min RR survival probability (floor for CV+RRR)
        float    fireflyBudget   = 0.05f;       ///< Contribution luminance scale for adaptive pMin
        uint32_t numLevels       = 8u;          ///< Number of LOD levels in the cascade (1..16)

        // --- Per-dimension coarse cell sizes (fine auto-derived from coarse + numLevels) ---
        float    cellACoarse     = 10.0f;       ///< posA coarsest cell (world units, auto-tuned from scene)
        float    cellBCoarse     = 20.0f;       ///< posB coarsest cell (world units, pos×pos modes)
        float    angularBCoarse  = 90.0f;       ///< direction coarsest cell (degrees, dirdist mode)
        float    distBCoarse     = 10.0f;       ///< distance coarsest cell (world units, dirdist mode)
        bool     autoTuneCells   = true;        ///< Auto-derive cellACoarse from scene bounds

        // --- Decay (host-only, not uploaded to GPU params cbuffer) ---
        uint32_t decayPeriod     = 300u;        ///< Frames per full table sweep (0=disabled)
        uint32_t decayPeriodMax  = 600u;        ///< PI controller ceiling for auto-tuned decay

        // --- Feature toggles (exported to downstream passes via dict) ---
        bool     enableVisCacheVisibilityCheck    = true;  ///< §12: CV+RRR in reconnection shifts
        bool     enableVisCacheLightSelection = true;   ///< §11.1: cached mu in NEE target function

        // --- Ablation toggles (Table 1 in paper) ---
        bool     enableVisCacheWarpReduction  = true;  ///< C: SM 6.5 WaveMatch coalescing
        bool     enableVisCacheVarianceGate   = true;  ///< B: Bernoulli variance-gated write depth
        bool     enableVisCacheDecay          = true;  ///< D: Background decay sweep
        bool     enableVisCachePressureEvict  = true;  ///< E: Pressure-driven eviction
        bool     enableVisCacheJitter         = true;  ///< F: Jitter-before-quantize (§4.2)
        bool     enableVisCacheDirDistAddr   = false; ///< G: Dir+dist addressing (inherently non-canonical)
    };

    const Params& getParams() const { return mParams; }

    VisCache(ref<Device> pDevice, const Properties& props);

private:

    void allocateBuffers();
    void autoTuneCellSizes();    ///< Derive cellACoarse (+ cellBCoarse, distBCoarse) from scene bounds
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
    bool     mAutoTuneCells = true;  ///< Auto-derive cellACoarse/cellBCoarse/distBCoarse from scene
    uint32_t mFrameCount = 0u;

    /// Readback stats (GPU → staging → CPU, ~4 frame latency).
    /// These are displayed in the UI and fed to the PI controller.
    struct Stats
    {
        float hitRate     = 0.f;  ///< (queries - misses) / queries — cache effectiveness
        float raySavings  = 0.f;  ///< (queries - inserts) / queries — fraction of rays skipped
        float evictRate   = 0.f;  ///< evictions / inserts — load pressure indicator
    } mStats;

    /// PI controller state for decayPeriod auto-tuning.
    /// The controller targets a stable eviction/insert ratio (mTargetLoadPressure).
    /// When load pressure exceeds the target, decay speeds up to free stale entries.
    /// Quality parameters (varThreshold, pMin) are NEVER auto-tuned — only decay speed.
    float mPIIntegral      = 0.f;       ///< Accumulated integral term
    float mTargetLoadPressure = 0.1f;   ///< Target eviction/insert ratio (setpoint)

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

    // Per-frame diag textures (cleared each frame)
    ref<Texture>    mpDiagTex;           ///< RGBA32F: mu, var, level, raySaved
    ref<Texture>    mpDiagErrorTex;     ///< R32F: prediction error |mu - V|
    ref<Texture>    mpVarMaturityLevelTex; ///< RGBA32F: var/maturity/level heatmap (R=var, G=maturity, B=level)
    ref<Texture>    mpVarMaturityMuTex; ///< RGBA32F: var/maturity/mu heatmap (R=var, G=maturity, B=mu)

    // Accumulated textures (persistent across frames, cleared on reset)
    ref<Texture>    mpAccumSaved;       ///< R32Uint: per-pixel saved ray count
    ref<Texture>    mpAccumTotal;       ///< R32Uint: per-pixel total query count
    ref<Texture>    mpRaySavedRatioTex; ///< R32Float: saved/total ratio
    ref<Texture>    mpNoiseTex;         ///< R32Float: noise estimate (variance EMA)
    bool            mResetAccum = true; ///< Clear accum textures next frame

    uint2           mFrameDims = {0, 0};
};

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
// vcAccumMeanVarMatCount (RGBA32F): R=variance*4, G=maturity, B=mean, A=count (accumulated avg)
// vcAccumRaysNoiseErrorCold (RGBA32F): R=raysTraced, G=renderNoise(TBD), B=renderError(TBD), A=coldmiss
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
    /// Exported via InternalDictionary as "vhfParamsCB" — VisCache.cpp memcpy's
    /// the entire struct here each frame.
    ///
    /// CRITICAL: when adding a field here you MUST also:
    ///   1. Add it to the slang cbuffer in matching order
    ///      (Source/RenderPasses/VisCache/VisCache.slang `cbuffer VisCacheParams`).
    ///   2. Add a per-field binding in EVERY downstream pass that imports the
    ///      cbuffer (Falcor 8 setBuffer() doesn't accept ConstantBuffer-typed
    ///      shader vars, so cross-pass binding must enumerate every field):
    ///        - Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp (tracePass)
    ///        - Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp (PathRetrace/PathReuse)
    ///   3. Surface it in the dict as `vhfParam_<name>` so passes can read it
    ///      back via `mVCParams.<name>` (VisCache.cpp ~line 510 area).
    /// Forgetting step 2 leaves the shader global at 0 silently — a bug that
    /// is very hard to debug. See CLAUDE.md "Workflow → Cbuffer cross-pass binding".
    struct GPUParams
    {
        uint32_t tableCapacity;
        uint32_t bootThreshold;
        uint32_t matureThreshold;
        float    varThreshold;
        float    pMin;
        float    fireflyBudget;
        uint32_t numLevels;
        uint32_t flags;           ///< Packed: bit 0 = adaptivePMin, bit 1 = normalAddr, bit 2 = bootstrapBreak, bit 3 = parentPreinit
        float    posACoarse;     ///< posA coarsest cell (world units)
        float    posAFine;       ///< posA finest cell (auto-derived)
        float    posBCoarse;     ///< posB coarsest cell (pos×pos modes)
        float    posBFine;       ///< posB finest cell (auto-derived)
        float    dirBCoarse;  ///< direction coarsest cell (degrees, dirdist)
        float    dirBFine;    ///< direction finest cell (auto-derived)
        float    distBCoarse;     ///< distance coarsest cell (world units, dirdist)
        float    distBFine;       ///< distance finest cell (auto-derived)
        float    normalACoarse;   ///< normal coarsest bin scale (oct [0,2] multiplier, 3=60°/bin)
        float    normalAFine;     ///< normal finest bin scale (auto-derived)
        float    bootThresholdFactorFootprintPx;  ///< K: footprint trust scale. 0 = off (pure bootThreshold),
                                  ///< 1 = log2(cellPixels) floor, >1 = aggressive.
        uint32_t forceDescendFootprintPx; ///< Cell-footprint (px²) above which vhfLookup refuses
                                          ///< to stop on convergence — always descends to finer
                                          ///< levels. Defends hard-shadow penumbra at big near-
                                          ///< camera cells. 0 = off.
        uint32_t cascadeWindowForward;    ///< Levels finer than targetLvl the lookup will visit.
                                          ///< Default 12 — cascade descends up to 12 levels finer.
                                          ///< 0 = entry-level-only (no descent) for debugging.
        float    stderrThreshold;         ///< Bernoulli standard-error gate: trust only when
                                          ///< sqrt(var/N) ≤ stderrThreshold. 0 = off (falls back
                                          ///< to varThreshold). Principled replacement for vt:
                                          ///< combines "low variance" and "enough samples" into
                                          ///< one criterion. Few-sample cells (high stderr) refuse
                                          ///< trust even if their var estimate is spuriously low.
        uint32_t enableHierarchicalConsistency; ///< 1 = at each converged level, peek the next
                                                ///< finer level's μ and require agreement within
                                                ///< gHierarchicalMuTolerance before early-stop.
                                                ///< 0 = off (legacy fast-path). Costs one extra
                                                ///< hash probe per converged level.
        float    hierarchicalMuTolerance; ///< |μ_next - μ_this| above which a converged level is
                                          ///< distrusted and the cascade keeps descending. Default
                                          ///< 0.20 = allow 20% spread between neighbour levels.
        float    accelDecayDisagreeThresh; ///< |sample − μ| above which an insert triggers an
                                           ///< in-line half-decay of the cell before the add.
                                           ///< Fights stale/wrong cell means by giving outlier
                                           ///< samples extra weight. 0 = off (legacy insert).
        uint32_t bootThresholdFine;        ///< Per-level fine variant of bootThreshold. 0 = off
                                           ///< (uniform bootThreshold). When nonzero, effective
                                           ///< required-sample count lerps from bootThreshold
                                           ///< (coarse, L=0) to bootThresholdFine (fine, L=N-1).
                                           ///< "Coarse HIGH, fine LOW" defends Cornell 1PL blob
                                           ///< without costing Bistro rays.
        float    jitterFilter;    ///< F: per-position-seed jitter scale (soft cell boundaries, 3D filter kernel). 0 = off.
        float    jitterCell;      ///< F: per-cell-index-seed jitter scale (Binder 2018, hard boundaries shift per cell). 0 = off.
        uint32_t diagAccumWindow; ///< EMA window for accumulated diagnostics (0 = all frames)
        uint32_t frameCount;      ///< Current frame index for per-frame RNG variation
        uint32_t spp;             ///< Samples per pixel (matches PathTracer; used as RNG frame stride)
        float    cameraPosW[3];   ///< Camera world position (for footprint estimation)
        float    pixelSize1;      ///< Pixel world size at unit depth
        uint32_t subframeN;        ///< N×N Bayer gate (1 = disabled)
        uint32_t warmupSlotsFirst; ///< # Bayer slots write-only in frame 0
        uint32_t warmupSlotsRun;   ///< # Bayer slots write-only in every subsequent frame

        // --- §9.4 World-space ReSTIR DI reservoirs (rides VisCache posA cascade) ---
        uint32_t wsEnable;             ///< 1 = WS-reservoir buffer active. Master gate.
        uint32_t wsLevelOffset;        ///< Reservoirs read at max(0, visTargetLvl - wsLevelOffset).
                                       ///< Default 1 = one level coarser than visibility.
        uint32_t wsCapacity;           ///< Power-of-two reservoir slot count (table size).
        float    wsMCap;               ///< Temporal sample-count cap for reservoir merge (Bitterli '20).
        uint32_t wsSpatialNeighbours;  ///< Neighbour cells gathered during spatial reuse (0..4).
        float    wsLightMuMin;         ///< ε-floor for cached μ in target p̂ (defensive sampling).
        float    wsLightSoftness;      ///< 0..1 softening of cached μ in target p̂.
                                       ///< 0 = uniform (no cache effect), 1 = full trust.
                                       ///< Effective μ = max(lerp(1, μ, softness), wsLightMuMin).
        uint32_t wsNormalAddr;         ///< 1 = fold a 6-axis face-normal bin into the cell hash.
                                       ///< Prevents cross-normal pollution at corners / thin shells.
        uint32_t wsInitialCandidates;  ///< K fresh per-pixel candidates per frame (RTXDI default: 8).
                                       ///< Drives variance reduction on many-lights scenes — single
                                       ///< candidate (K=1) gives no variance benefit beyond vanilla NEE.
    };

    /// Full parameter set — includes GPU params + host-only knobs (decay, auto-tune,
    /// ablation toggles). Feature and ablation toggles are exported via InternalDictionary
    /// so downstream passes (ReSTIRPTPass) can read them and set compile-time defines.
    struct Params
    {
        // --- Hash table sizing ---
        uint32_t tableCapacity   = 1u << 22u;  ///< 4M entries = 32 MB (must be power-of-two)
        uint32_t bootThreshold   = 32u;         ///< Min samples before trusting entry for RR (use gate)
        uint32_t matureThreshold = 128u;        ///< Min samples before stopping writes (mature gate, >= bootThreshold)
        float    varThreshold    = 0.10f;       ///< Bernoulli variance gate for cascaded write depth
        float    pMin            = 0.05f;       ///< Min RR survival probability (floor for CV+RRR)
        float    fireflyBudget   = 0.05f;       ///< Contribution luminance scale for adaptive pMin
        uint32_t numLevels       = 8u;          ///< Number of LOD levels in the cascade (1..16)

        // --- Per-dimension coarse cell sizes (fine auto-derived from coarse + numLevels) ---
        float    posACoarse     = 10.0f;       ///< posA coarsest cell (world units, auto-tuned from scene)
        float    posBCoarse     = 20.0f;       ///< posB coarsest cell (world units, pos×pos modes)
        float    dirBCoarse  = 90.0f;       ///< direction coarsest cell (degrees, dirdist mode)
        float    distBCoarse     = 10.0f;       ///< distance coarsest cell (world units, dirdist mode)
        float    normalACoarse   = 60.0f;      ///< normal coarsest cell (degrees, 60°≈6 bins, 90°≈4 bins, 360°=collapsed)
        uint32_t diagAccumWindow = 128u;        ///< EMA window for accumulated diagnostics (0 = all frames)
        uint32_t spp             = 1u;          ///< Samples per pixel (matches PathTracer; used as RNG frame stride)
        bool     autoTuneCells   = true;        ///< Auto-derive posACoarse from scene bounds
        bool     quantSceneScale = false;       ///< Interpret posA/posB/distB as fractions of scene BB
                                                ///< (Cornell-calibrated reference: avgAxis=2 units).
                                                ///< Opt-in via Python ladder PRESET. Only applied when
                                                ///< autoTuneCells=False; autoTune already scales.

        // --- Decay (host-only, not uploaded to GPU params cbuffer) ---
        uint32_t decayPeriod     = 300u;        ///< Frames per full table sweep (0=disabled).
                                                ///< Primary decay rate — set by user, not load-tuned.
        uint32_t decayPeriodMax  = 600u;        ///< PI controller ceiling for auto-tuned decay (only
                                                ///< used when enableDecayAutoTune is on).
        bool     enableDecayAutoTune = false;   ///< Secondary PI adjustment of decayPeriod based on
                                                ///< eviction load. Off by default — user's decayPeriod
                                                ///< is the canonical setting; PI tuning is opt-in for
                                                ///< production-style adaptive use.

        // --- Feature toggles (exported to downstream passes via dict) ---
        bool     enableVisCacheVisibilityCheck    = true;  ///< §12: CV+RRR in reconnection shifts
        bool     enableVisCacheLightSelection = true;   ///< §11.1: cached mu in NEE target function

        // --- Ablation toggles (Table 1 in paper) ---
        bool     enableVisCacheWarpReduction  = true;  ///< C: SM 6.5 WaveMatch coalescing
        bool     enableVisCacheVarianceGate   = true;  ///< B: Bernoulli variance-gated write depth
        bool     enableVisCacheDecay          = true;  ///< D: Background decay sweep
        bool     enableVisCachePressureEvict  = true;  ///< E: Pressure-driven eviction
        float    jitterFilter                 = 0.0f;  ///< F: per-position-seed jitter scale (soft cell boundaries, 3D filter kernel). 0 = off.
        float    jitterCell                   = 0.0f;  ///< F: per-cell-index-seed jitter scale [Binder et al. 2018] (hard boundaries, per-cell shift). 0 = off.
        bool     enableVisCacheAdaptivePMin   = true;  ///< H: Confidence-adaptive pMin (§8.1.1)
        bool     enableVisCacheNormalAddr     = false; ///< I: Normal-augmented addressing (posNorm)
        bool     enableVisCacheDirDistAddr   = false; ///< G: Dir+dist addressing (inherently non-canonical)
        bool     enableVisCacheBootstrapBreak = false; ///< §5 Bootstrap: break cascade when post-write total < bootThreshold (too sparse to guide children).
        bool     enableVisCacheParentPreinit  = false; ///< §5 Parent-preinit: seed new child slot with (parentVis>>3, parentTotal>>3) on first claim.
        float    bootThresholdFactorFootprintPx              = 1.0f; ///< K: Footprint trust scale (floor = k*log2(cellPx)).
                                                      ///< 0 disables (equivalent to prior fpOff).
        uint32_t cascadeWindowForward        = 12u;   ///< Levels finer than targetLvl that vhfLookup
                                                      ///< visits during cascade descent. 0 = entry-only
                                                      ///< (debug; isolates targetLvl correctness).
        uint32_t forceDescendFootprintPx     = 0u;    ///< Cell-footprint (px²) ceiling for convergence
                                                      ///< early-stop in vhfLookup. Cells with cellPx above
                                                      ///< this threshold are not allowed to short-circuit
                                                      ///< on variance ≤ gVarThreshold; the cascade always
                                                      ///< descends to refine them. 0 = off (prior behavior).
        float    stderrThreshold             = 0.0f;  ///< Bernoulli stderr gate; 0 = off (fallback to vt).
        bool     enableHierarchicalConsistency = false; ///< Peek finer-level μ for agreement check.
        float    hierarchicalMuTolerance     = 0.20f; ///< |μ_next − μ_this| above which trust is refused.
        float    accelDecayDisagreeThresh    = 0.0f;  ///< |sample−μ| that triggers in-insert half-decay; 0 = off.
        uint32_t bootThresholdFine           = 0u;    ///< Per-level fine bootThreshold; 0 = uniform legacy.
        float    preinitAmbiguityCutoff      = 0.0f;  ///< Preinit ambiguity gate; 0 = unconditional preinit.
        uint32_t subframeN                     = 1u;    ///< M: N×N subframe gate (1=full frame, 2=2×2, 4=4×4); disperses cell writes across frames
        uint32_t warmupSlotsFirst              = 0u;    ///< L: # of Bayer slots [0,N²) write-only in frame 0 (force trace, no RR)
        uint32_t warmupSlotsRun                = 0u;    ///< L: # of Bayer slots write-only in every subsequent frame
        uint32_t cascadeVisitCount             = 32u;   ///< # cascade strides per trace (levelStride = (N-1)/this).
                                                        ///< Lower = bigger cell-size step per stride, more samples per cell.

        // --- §9.4 World-space ReSTIR DI reservoirs ---
        bool     enableWSReservoirs            = false; ///< Master gate. Off = legacy NEE in PathTracer.
        uint32_t wsLevelOffset                 = 1u;    ///< Cascade-coarseness offset for reservoir reads (vs visibility).
        uint32_t wsReservoirCapacity           = 1u << 18u; ///< 256K slots × ~32 B = 8 MB default.
        float    wsMCap                        = 30.0f; ///< Temporal M-cap for reservoir merge.
        uint32_t wsSpatialNeighbours           = 4u;    ///< Spatial neighbour cells gathered per pixel (0..4).
        float    wsLightMuMin                  = 0.01f; ///< ε-floor for cached μ in NEE target p̂.
        float    wsLightSoftness               = 1.0f;  ///< Softening of cached μ for light selection.
                                                        ///< 0 disables (uniform — cache has no effect on selection),
                                                        ///< 1 = full trust (current behavior). 0.5 = √μ-like soft.
        bool     wsNormalAddr                  = false; ///< Fold 6-axis face-normal bin into cell hash.
                                                        ///< Prevents cross-normal cell sharing at corners.
        uint32_t wsInitialCandidates           = 8u;    ///< K fresh per-pixel candidates per frame
                                                        ///< (matches RTXDI's localLightCandidateCount default).
    };

    const Params& getParams() const { return mParams; }

    VisCache(ref<Device> pDevice, const Properties& props);

private:

    void allocateBuffers();
    void autoTuneCellSizes();    ///< Derive posACoarse (+ posBCoarse, distBCoarse) from scene bounds
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
    ref<Buffer>         mpWSReservoirs;  ///< RWStructuredBuffer<WSReservoir>, sized by wsReservoirCapacity. Allocated on demand.
    uint32_t            mWSReservoirCapacityCommitted = 0u; ///< Capacity used to allocate mpWSReservoirs (re-alloc on resize).
    // §9.4 per-pixel temporal reservoir (RTXDI-style). One slot per pixel,
    // persists across frames so temporal-M accumulation kicks in.
    ref<Buffer>         mpPixelReservoirs;
    uint2               mPixelReservoirsCommitted = {0u, 0u};

    ref<ComputePass>    mpDecayPass;

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    Params   mParams;
    ref<Scene> mpScene;          ///< Current scene (for bounds + camera)
    bool     mAutoTuneCells = true;  ///< Auto-derive posACoarse/posBCoarse/distBCoarse from scene
    uint32_t mFrameCount = 0u;    ///< Logical frame (shared across all N² subframes of one Bayer cycle)
    uint32_t mSubframeIdx = 0u;   ///< 0..N²-1 — cycles within one logical frame

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
    };

    bool            mEnableDiagnostics = false; ///< Master enable (auto-set by dropdown)
    DiagMode        mDiagMode = DiagMode::Off;  ///< Selected heatmap mode

    // Per-frame diag textures (cleared each frame)
    ref<Texture>    mpAccumMeanVarMatCountTex;   ///< RGBA32F accumulated: R=variance*4, G=maturity, B=mean, A=count (bookkeeping for online mean)
    ref<Texture>    mpFrameMeanVarMatSamplesRawTex;   ///< RGBA32F frame: R=variance*4, G=maturity, B=mean, A=samplesRaw
    ref<Texture>    mpFrameLevelProbesSamplesColdTex;   ///< RGBA32F frame: R=level, G=probeSteps, B=samples, A=coldmiss
    ref<Texture>    mpFrameHashAHashBHashABRaysTex;   ///< RGBA32F frame: R=posAHash, G=posBHash, B=combinedHash, A=raysTraced

    // Accumulated textures (persistent across frames, cleared on reset)
    ref<Texture>    mpAccumSaved;       ///< R32Uint: per-pixel saved ray count
    ref<Texture>    mpAccumTotal;       ///< R32Uint: per-pixel total query count
    ref<Texture>    mpAccumRaysNoiseErrorColdTex; ///< RGBA32Float: R=raysTraced, G=renderNoise(TBD), B=renderError(TBD), A=coldmiss
    bool            mResetAccum = true;      ///< Clear accum textures next frame
    bool            mClearHashTable = true;  ///< Clear hash table to empty sentinel

    uint2           mFrameDims = {0, 0};
};

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
        uint32_t mlAlphaFloorN;           ///< MLE α-floor: target effective sample count N* for
                                           ///< per-cell mean blending. While total < N*, the cell
                                           ///< is a pure running mean (α = 1/N). When total ≥ N*,
                                           ///< 1/8 inline decay fires per insert, giving effective
                                           ///< α ≈ 1/N* ≈ MIN_ALPHA in MCPG 2025 / Alber et al.
                                           ///< 0 = off (defaults to legacy 16-bit overflow trigger
                                           ///< at ~57344 samples ≈ no forgetting). Typical: 256 –
                                           ///< 1024. Lower → faster adaptation, more variance.
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
        uint32_t bayerN;           ///< Bayer N×N dither — N=4 means 4×4 pattern with N²=16 total subframes per cycle. 1 = disabled (full frame each frame).
        uint32_t warmupSlotsFirst; ///< # Bayer slots write-only in frame 0
        uint32_t warmupSlotsRun;   ///< # Bayer slots write-only in every subsequent frame

        // --- §9.4 World-space ReSTIR DI reservoirs (rides VisCache posA cascade) ---
        uint32_t wsEnable;             ///< 1 = WS-reservoir buffer active. Master gate.
        uint32_t wsCellLevel;          ///< WS-ReSTIR cell level into VisCache's posA cascade.
                                       ///< Reuses vhfPosASize(lvl) and jitterQuantize machinery.
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
        uint32_t _wsPad0;              ///< (reserved — was wsJitterFilter; WS-ReSTIR now reuses VisCache's gJitterFilter)
        uint32_t _wsPad1;              ///< (reserved — was wsJitterCell; WS-ReSTIR now reuses VisCache's gJitterCell)
        uint32_t wsUseCellInRIS;       ///< 1 = include WS cell candidate(s); 0 = pure per-pixel ReSTIR.
        uint32_t wsVisInPHat;          ///< 0 = visibility-blind p̂ (legacy), 1 = visibility-aware p̂ via cache (CV+RR), 2 = explicit always-trace (no cache).
        // --- §9.4 WS-cascade ReGIR cell pool (multi-light pool per cell) ---
        uint32_t wsCellPoolEnable;     ///< 1 = pool buffer active. Step (a)+ master gate.
        uint32_t wsCellPoolCapacity;   ///< Power-of-two pool slot count.
        uint32_t wsCellPoolDrawK;      ///< K candidates drawn from pool per pixel (0 = read disabled,
                                       ///< write-back still active so pool fills).
        uint32_t wsCellLevelJitter;    ///< Stochastic LOD jitter range (0 = off).
        uint32_t wsSpatialPixelsK;     ///< Per-pixel screen-space spatial-reuse neighbour count (default 4).
        uint32_t wsSpatialPixelsRadius;///< Spatial-reuse search radius in pixels (default 32).
        uint32_t wsPoolAddrMode;       ///< 0 = 3D cell, 1 = 2D screen-tile.
        uint32_t wsPoolTileSize;       ///< Tile edge in pixels (default 16). AddrMode=1 only.
        float    dirSolidAngleScale;   ///< §4.2 posB angular axis multiplier (default 1.0).
        float    distSolidAngleScale;  ///< §4.2 posB distance axis multiplier (default 1.0).
        uint32_t wsCellReservoirMerge; ///< 0 = identity-hint cell (legacy), 1 = Bitterli merge (3D-eq variant).
        uint32_t wsCellPoolFootprintPx;///< Target cell screen-space footprint in pixels. 0 = fixed-level
                                       ///< (gWSCellLevel). >0 = analytical entry level via shared
                                       ///< vhfLevelForFootprint helper.
        uint32_t wsRetraceOnReuseMode; ///< Retrace V on temporal/spatial reservoir reuse (RTXDI BiasCorrection
                                       ///< analog). 0 = Off (Basic-equiv: stored W carries write-time V — what
                                       ///< we ship today), 1 = FullTrace (≡ RTXDI BiasCorrection::RayTraced —
                                       ///< unbiased, expensive), 2 = CacheCV (cache CV+RRR via existing
                                       ///< evalRevalidationCV — same PT-canonical knobs as the regular shadow
                                       ///< gate). Layer (b) of the WS-ReSTIR DI plan.
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
        uint32_t mlAlphaFloorN               = 0u;    ///< MLE α-floor target N* (MCPG 2025); 0 = off (legacy overflow only).
        uint32_t bootThresholdFine           = 0u;    ///< Per-level fine bootThreshold; 0 = uniform legacy.
        float    preinitAmbiguityCutoff      = 0.0f;  ///< Preinit ambiguity gate; 0 = unconditional preinit.
        uint32_t bayerN                        = 1u;    ///< Bayer N×N dither — N=4 means 4×4 pattern with N²=16 subframes per cycle (1=disabled, 2=2×2/4-subframe, 4=4×4/16-subframe, 8=8×8/64-subframe); disperses cell writes across frames.
        uint32_t warmupSlotsFirst              = 0u;    ///< L: # of Bayer slots [0,N²) write-only in frame 0 (force trace, no RR)
        uint32_t warmupSlotsRun                = 0u;    ///< L: # of Bayer slots write-only in every subsequent frame
        uint32_t cascadeVisitCount             = 32u;   ///< # cascade strides per trace (levelStride = (N-1)/this).
                                                        ///< Lower = bigger cell-size step per stride, more samples per cell.

        // --- §9.4 World-space ReSTIR DI reservoirs ---
        bool     enableWSReservoirs            = false; ///< Master gate. Off = legacy NEE in PathTracer.
        bool     enableWSPixelReservoir        = true;  ///< Per-pixel temporal + spatial pixel-reuse
                                                        ///< layer (RTXDI screen-side reservoir). Set false
                                                        ///< to focus on the pure WS-cell pipeline (cell pool +
                                                        ///< cell reservoir + jittered cell-spatial gather).
        bool     enableBoilingFilter           = false; ///< DISABLED 2026-05-05. Field kept so existing
                                                        ///< Python configs / dict round-trips do not break,
                                                        ///< but VisCache.cpp does not create or dispatch the
                                                        ///< compute pass. See WSReservoirBoilingFilter.cs.slang
                                                        ///< header for the failure mode (shader writes never
                                                        ///< reach gWSPixelReservoirs) and the recommended
                                                        ///< separable-include fix path.
        float    boilingFilterStrength         = 0.2f;  ///< Unused while enableBoilingFilter is hard-disabled.
        uint32_t wsCellLevel                   = 4u;    ///< WS-ReSTIR cell level into VisCache's posA cascade.
                                                        ///< Default 4 = mid-cascade (with default numLevels=8).
                                                        ///< Reuses vhfPosASize(lvl) + jitterQuantize from VisCache;
                                                        ///< the cascade is shared infrastructure even though the two
                                                        ///< systems are functionally independent.
        uint32_t wsCellLevelJitter             = 0u;    ///< Stochastic LOD jitter (0 = off). When >0, the per-pixel
                                                        ///< level is perturbed by a one-sided truncated-exponential
                                                        ///< offset in [0, jitter] *above* wsCellLevel. P(offset=k) ∝
                                                        ///< 2^(-k); never queries levels finer than base. Form follows
                                                        ///< MCPG 2025 (merian-quake/mc.glsl: -log2(1-u)). Composes
                                                        ///< with gJitterFilter / gJitterCell (spatial jitter from
                                                        ///< VisCache).
        uint32_t wsReservoirCapacity           = 1u << 18u; ///< 256K slots × ~32 B = 8 MB default.
        float    wsMCap                        = 5.0f;  ///< Temporal M-cap for reservoir merge.
                                                        ///< Higher = more temporal stability but per-pixel
                                                        ///< reservoir lock-in bias (occluded picks stay dark
                                                        ///< on emissive scenes). Mitigated by spatial reuse.
        uint32_t wsSpatialNeighbours           = 4u;    ///< Spatial neighbour cells gathered per pixel (0..4).
        float    wsLightMuMin                  = 0.01f; ///< ε-floor for cached μ in NEE target p̂.
        float    wsLightSoftness               = 1.0f;  ///< Softening of cached μ for light selection.
                                                        ///< 0 disables (uniform — cache has no effect on selection),
                                                        ///< 1 = full trust (current behavior). 0.5 = √μ-like soft.
        bool     wsNormalAddr                  = false; ///< Fold 6-axis face-normal bin into cell hash.
                                                        ///< Prevents cross-normal cell sharing at corners.
        uint32_t wsInitialCandidates           = 8u;    ///< K fresh per-pixel candidates per frame
                                                        ///< (matches RTXDI's localLightCandidateCount default).
        // (wsJitterFilter / wsJitterCell removed — WS-ReSTIR reuses
        //  VisCache's gJitterFilter / gJitterCell via the shared
        //  jitterQuantize() machinery. Set the latter via the
        //  jitterFilter / jitterCell Params.)
        bool     wsUseCellInRIS                = true;  ///< Include WS cell candidate(s) in per-pixel RIS.
                                                        ///< Off = pure per-pixel ReSTIR DI (per-pixel temporal
                                                        ///< + spatial reuse only). Useful as an ablation: WS
                                                        ///< layer's value vs the boundary artifacts it adds.
        uint32_t wsVisInPHat                   = 0u;    ///< Visibility-aware target function (off by default).
                                                        ///< RTXDI-faithful behavior is BLIND RIS (this default) +
                                                        ///< V=0 reservoir invalidation after the winner's shadow
                                                        ///< trace (always-on, in PathTracer.slang). Putting V in
                                                        ///< the K-RIS p̂ adds μmin-floor bias on emissive scenes.
                                                        ///< 0 = blind (RTXDI-faithful, default).
                                                        ///< 1 = cache-amortized (experimental — biased).
                                                        ///< 2 = explicit always-trace (experimental — biased).

        // --- §9.4 WS-cascade ReGIR cell pool (multi-light pool per cell) ---
        bool     enableWSCellPool              = false; ///< Master gate for the multi-light pool (step a+ of
                                                        ///< .plans/rtxdi-parity-ws-cascade.md).
        uint32_t wsCellPoolCapacity            = 1u << 18u; ///< 256K slots × 72 B = 18 MB default.
        uint32_t wsCellPoolDrawK               = 0u;    ///< K candidates drawn from pool per pixel (read path).
                                                        ///< 0 = pool fills from write-back only; main pass keeps
                                                        ///<     using fresh generateLightSample candidates.
                                                        ///< K>0 = main pass draws K from pool (when populated)
                                                        ///<       and falls back to fresh per-pixel for empty pools.
        uint32_t wsSpatialPixelsK              = 4u;    ///< Per-pixel screen-space spatial-reuse neighbour count.
                                                        ///< 0 = no per-pixel spatial gather (still has temporal).
                                                        ///< 4 = current default (matches RTXDI's 1-round k≈4–5).
                                                        ///< 8+ = compensates for missing 2nd spatial round at the
                                                        ///<      cost of more reservoir reads per pixel.
        uint32_t wsSpatialPixelsRadius         = 32u;   ///< Spatial-reuse pixel search radius (Manhattan-ish).
                                                        ///< 32 ≈ RTXDI's default; smaller = more correlated reuse,
                                                        ///< larger = wider but more bias from disparate surfaces.
        uint32_t wsPoolAddrMode                = 0u;    ///< 0 = 3D world cell (default), 1 = 2D screen-tile.
                                                        ///< Tile mode (RTXDI-style) reuses the cell-pool buffer
                                                        ///< but addresses by `pixel.xy / tileSize`. Same K-RIS
                                                        ///< prepass (`PathTracerPrePass`) writes; main pass
                                                        ///< reads its-pixel's tile entries. Concentrates K-RIS
                                                        ///< filtering in screen-space — closes the single-frame
                                                        ///< Sponza x1 gap to RTXDI without a separate compute pass.
        uint32_t wsPoolTileSize                = 16u;   ///< Tile edge in pixels for AddrMode=1. 16 → 256-pixel
                                                        ///< tiles match RTXDI's default; larger = fewer tiles
                                                        ///< (more inserts per tile = better filter quality but
                                                        ///< broader candidate region per pixel).
        float    dirSolidAngleScale            = 1.0f;  ///< §4.2 posB Option B angular-axis multiplier.
                                                        ///< α = clamp((cellSizeA / posACoarse) × this, 0.05, 0.5).
                                                        ///< 1.0 = posA-cell-matched (recommended). <1 = finer
                                                        ///< angular bins (more cells); >1 = coarser.
        float    distSolidAngleScale           = 1.0f;  ///< §4.2 posB Option B distance-axis multiplier.
                                                        ///< logStep = log(1 + α × this). 1.0 = isotropic
                                                        ///< (matched solid-angle cubic bins). <1 = finer dist;
                                                        ///< >1 = coarser dist.
        uint32_t wsCellReservoirMerge          = 0u;    ///< 0 = legacy identity-hint cell read (preserves wsrestir).
                                                        ///< 1 = promote cell to full Bitterli weighted merge —
                                                        ///< world-space analog of per-pixel reservoir, no
                                                        ///< reprojection needed. Set to 1 for `restir_3d`.
        uint32_t wsCellPoolFootprintPx         = 0u;    ///< 0 = fixed-level pool addressing (gWSCellLevel).
                                                        ///< >0 = analytical footprint-derived per-pixel level
                                                        ///< via shared vhfLevelForFootprint(targetPx²). e.g.
                                                        ///< 16 → ~256 px² cell footprint, matching the 2D
                                                        ///< tile-pool's 16-px tile.
        uint32_t wsRetraceOnReuseMode          = 0u;    ///< 0 = Off (Basic-equiv, current default), 1 = FullTrace
                                                        ///< (≡ RTXDI RayTraced), 2 = CacheCV (cheap CV+RRR via
                                                        ///< evalRevalidationCV with PT-canonical knobs). Toggleable
                                                        ///< like RTXDI's BiasCorrection enum.
    };

    const Params& getParams() const { return mParams; }

    VisCache(ref<Device> pDevice, const Properties& props);

private:

    void allocateBuffers();
    void autoTuneCellSizes();    ///< Derive posACoarse (+ posBCoarse, distBCoarse) from scene bounds
    void runDecayPass(RenderContext* pCtx);
    // ╔══ DISABLED 2026-05-05 — see WSReservoirBoilingFilter.cs.slang ══╗
    // void runBoilingFilterPass(RenderContext* pCtx);
    // ╚═════════════════════════════════════════════════════════════════╝
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
    // §9.4 WS-cascade ReGIR cell pool — multi-light pool per cell.
    ref<Buffer>         mpWSCellPools;
    uint32_t            mWSCellPoolCapacityCommitted = 0u;

    ref<ComputePass>    mpDecayPass;
    // ╔══ DISABLED 2026-05-05 — see WSReservoirBoilingFilter.cs.slang ══╗
    // ref<ComputePass> mpBoilingFilterPass;
    // ╚═════════════════════════════════════════════════════════════════╝

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

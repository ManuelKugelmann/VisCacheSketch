/***************************************************************************
 * VisCache.slang
 *
 * Visibility Cache — Core Data Structure
 * Kugelmann 2026, extending Kugelmann 2006
 *
 * Flat N-level spatial hash table caching pairwise visibility estimates
 * between arbitrary world-space endpoint pairs (A, B). The cache stores
 * Bernoulli statistics (vis_count / total_count) per quantized cell pair,
 * enabling the CV+RRR estimator to skip shadow rays where visibility is
 * already well-known, while remaining strictly unbiased.
 *
 * Key design decisions and their reasoning:
 *
 *   SYMMETRIC CELL PAIRS: V(A,B) = V(B,A), so both orderings hash to the
 *     same entry via lexicographic canonicalization. This halves the table
 *     pressure compared to directional caching.
 *
 *   N-LEVEL LOD CASCADE: Coarse levels converge quickly (many samples per
 *     cell pair) but miss penumbra detail. Fine levels resolve shadow edges
 *     but need more samples. The cascade iterates coarse-to-fine, stopping
 *     early when variance is low (converged region) or when an entry is
 *     immature (too few samples). This adaptive depth means the cache
 *     spends capacity on shadow boundaries where it matters most.
 *
 *   GEOMETRIC CELL SIZE INTERPOLATION: Level cell sizes are geometrically
 *     spaced between coarse and fine per dimension. Geometric (not linear)
 *     spacing gives each level roughly the same number of populated cells.
 *
 *   JITTER-BEFORE-QUANTIZE: Two stackable float knobs (jitterFilter,
 *     jitterCell) add a per-position or per-cell random offset before
 *     floor() to eliminate systematic aliasing at cell boundaries.
 *     jitterFilter [asuint(pos)-seeded] softens boundaries (3D filter
 *     kernel); jitterCell [baseIdx-seeded, Binder et al. 2018] shifts
 *     each cell as a unit. Both default to 0.0 (off).
 *
 *   TWO INDEPENDENT HASH CHAINS: Address and fingerprint are computed from
 *     different hash seeds. The fingerprint detects collisions (different
 *     cell pairs mapping to the same slot). Double hashing with h2 derived
 *     from fingerprint guarantees full table traversal (h2 is odd).
 *
 *   CV+RRR ESTIMATOR: The control variate with Russian Roulette and
 *     Resampling estimator gives E[mu + (V - mu)/p] = E[V], unbiased for
 *     any p in (0,1]. When the cache mean mu is accurate, the residual
 *     (V - mu) is small, so the variance-scaled RR probability p can be
 *     low, skipping most shadow rays while keeping the estimator unbiased.
 *
 * References:
 *   [Binder et al. 2018]        Hash-grid spatial caching
 *   [Jarzynski & Olano 2020]    PCG3D hash, JCGT
 *   [Szirmay-Kalos et al. 2005] CV+RRR for visibility
 *   [Kugelmann 2006]            Visibility hash fields (thesis)
 ***************************************************************************/

#pragma once

// When USE_VISCACHE=0, this module compiles to nothing — all types,
// resources, and functions are excluded. Consumer passes can import
// unconditionally without #if guards; the Slang compiler eliminates
// the empty module at compile time.
#if USE_VISCACHE

// Addressing modes (compile-time, mutually exclusive):
//   Default (neither set):       Canonical pos x pos — same cell size for both endpoints, lexicographic swap.
//   USE_VISCACHE_DIRDIST_ADDRESSING=1:  Dir+dist — posB from direction+distance, per-dimension cascade.
//                                       gDirBCoarse/Fine control angular quantization.
//                                       gDistBCoarse/Fine control distance quantization.
//   Neither set + posBCoarse == posACoarse: Canonical pos x pos with lexicographic swap.
//   Neither set + posBCoarse != posACoarse: Asymmetric pos x pos, no swap (auto-derived).
#ifndef USE_VISCACHE_DIRDIST_ADDRESSING
#define USE_VISCACHE_DIRDIST_ADDRESSING 0
#endif

// ===========================================================================
// DATA STRUCTURES
// ===========================================================================

// ---------------------------------------------------------------------------
// VHFEntry: 8 bytes per hash table slot.
//
// Layout: [fingerprint:32][vis_count:16 | total_count:16]
//
// Fingerprint: second hash of the quantized cell pair, used for collision
//   detection. If two different cell pairs hash to the same address, the
//   fingerprint distinguishes them. A fingerprint of 0 means the slot is
//   empty (or was cleared by decay).
//
// Packed counters: 16-bit vis_count (numerator) and 16-bit total_count
//   (denominator). Packed into a single uint32 so that both can be updated
//   atomically with a single InterlockedAdd. The mean visibility estimate
//   is mu = vis_count / total_count.
//
// The 16-bit counter width means entries saturate at 65535 samples.
// Inline overflow decay (vhfOverflowDecay) prevents wrap-around by
// subtracting 1/8 of both counters when total exceeds kOverflowTrigger.
// This preserves the ratio (mean) while freeing counter headroom.
// ---------------------------------------------------------------------------
struct VHFEntry
{
    uint fingerprint;   ///< Collision detection hash [Binder et al. 2018]
    uint packed;        ///< [vis_count:16 | total_count:16] — atomic update target
};

// ---------------------------------------------------------------------------
// VHFResult: returned by vhfLookup() — the cascade query result.
//
// A "valid" result means at least one level had enough samples (>= boot
// threshold) to produce a trustworthy mean. An invalid result (cold miss)
// means the caller must trace unconditionally.
// ---------------------------------------------------------------------------
struct VHFResult
{
    float mu;       ///< Cached visibility mean (vis_count / total_count)
    float var;      ///< Bernoulli variance = mu * (1 - mu)
    int   level;    ///< LOD level that produced this result (-1 = miss)
    uint  N;        ///< Total sample count at matched level (0 = miss, for diagnostics)
    bool  valid;    ///< false = cold miss — no mature entry found, always trace
    uint  probeSteps; ///< Total probe steps across all levels (diagnostics — collision pressure)
    int3  qa;       ///< Quantized posA at matched level (diagnostics — hash grid vis)
    int3  qb;       ///< Quantized posB at matched level (diagnostics — hash grid vis)
};

// ===========================================================================
// PARAMETERS
// ===========================================================================

// ---------------------------------------------------------------------------
// VisCacheParams: uploaded as a 32-byte constant buffer each frame by the
// VisCache host pass (VisCache.cpp). Downstream passes (ReSTIRPTPass,
// PathTracer) bind this buffer with a single line:
//
//   rootVar["VisCacheParams"] = dict["vhfParamsCB"];
//
// The struct layout must exactly match GPUParams in VisCache.h (static_assert
// enforced). All parameters are validated by the host before upload.
//
// Tuning guide (each parameter and its effect on ray savings vs. quality):
//
//   gTableCapacity:  Power-of-two entry count. 2^22 (~4M entries, 32 MB) is
//     a good default for 1080p. Scale with resolution * bounce count. Too
//     small → high eviction rate → cache thrashing. Too large → wasted VRAM.
//
//   gBootThreshold:  Minimum total_count before an entry is trusted for RR
//     decisions (use gate). Lower values (16) give faster warmup but noisier
//     early estimates. Higher values (64) are more conservative.
//     Must be >= 1 and <= 0xFFFF (16-bit counter width).
//
//   gMatureThreshold:  Minimum total_count before stopping writes to an entry
//     (mature gate). Must be >= gBootThreshold. Higher values keep entries
//     accepting new samples longer, improving estimate quality in penumbrae.
//     The actual required count scales with variance: high-variance cells
//     need more samples (required = var * matureThreshold / varThreshold).
//
//   gVarThreshold:  Variance gate for cascaded LOD stop (lookup) and RR
//     probability scaling. 0.10 means: stop refining when mu*(1-mu) < 0.10.
//     Lower values (0.01) activate more levels, giving higher quality at
//     shadow penumbrae but tracing more rays. Higher values save more rays
//     but may miss penumbra detail.
//
//   gPMin:  Minimum RR survival probability — the floor below which
//     variance-based p is never reduced. 0.05 means never kill more than
//     95% of rays. Raise to 0.10-0.20 for less noise at the cost of
//     fewer skipped rays.
//
//   gFireflyBudget:  Adaptive pMin scale for firefly suppression. When a
//     path has high contribution luminance (bright caustic), pMin is raised
//     so the CV+RRR weight doesn't explode. 0.05 is conservative; raise
//     for scenes with bright caustics.
//
//   gNumLevels:  Number of LOD levels in the cascade. 3 is typical
//     (coarse/mid/fine). More levels give finer spatial adaptation but
//     use more table capacity per endpoint pair. Must be >= 1.
//
//   Per-dimension coarse/fine pairs (posA, posB, dirB, distB):
//     Coarse = coarsest level cell size, fine = finest (auto-derived).
//     Intermediate levels are geometrically interpolated.
// ---------------------------------------------------------------------------
cbuffer VisCacheParams
{
    uint   gTableCapacity;   ///< Power-of-two entry count
    uint   gBootThreshold;   ///< Min total_count before entry is trusted for RR (use gate)
    uint   gMatureThreshold; ///< Min total_count before stopping writes (mature gate)
    float  gVarThreshold;    ///< Variance below which we stop refining LOD
    float  gPMin;            ///< Minimum RR survival probability
    float  gFireflyBudget;   ///< Contribution scale for adaptive pMin
    uint   gNumLevels;       ///< Number of LOD levels (runtime, arbitrary N)
    uint   gFlags;           ///< Packed flags: 0=adaptivePMin 1=normalAddr
    // --- Per-dimension LOD cascade (coarse → fine, geometric interpolation) ---
    float  gPosACoarse;      ///< posA coarsest cell size (world units, auto-tuned from scene)
    float  gPosAFine;        ///< posA finest cell size (auto-derived from coarse + numLevels)
    float  gPosBCoarse;      ///< posB coarsest cell size (world units, pos×pos modes)
    float  gPosBFine;        ///< posB finest cell size (auto-derived)
    float  gDirBCoarse;      ///< direction coarsest cell size (degrees, dirdist mode)
    float  gDirBFine;        ///< direction finest cell size (auto-derived)
    float  gDistBCoarse;     ///< distance coarsest cell size (world units, dirdist mode)
    float  gDistBFine;       ///< distance finest cell size (auto-derived)
    float  gNormalACoarse;   ///< normal coarsest cell size (degrees, like dirBCoarse)
    float  gNormalAFine;     ///< normal finest cell size (auto-derived)
    float  gBootThresholdFactorFootprintPx;  ///< K: footprint trust scale. 0 = off (pure bootThreshold),
                             ///< 1 = log2(cellPixels) floor, >1 = aggressive.
    uint   gForceDescendFootprintPx; ///< Cell-footprint (px²) above which vhfLookup always
                                     ///< descends past convergence — defends penumbra at big
                                     ///< near-camera cells. 0 = off (prior early-stop behaviour).
    uint   gCascadeWindowForward;    ///< Levels finer than targetLvl that vhfLookup visits.
                                     ///< Default 12. 0 = entry-level-only (debug).
    float  gStderrThreshold;          ///< Bernoulli stderr gate — trust iff sqrt(var/N) ≤ this.
                                      ///< 0 = off (fall back to gVarThreshold).
    float  gWilsonZSquared;           ///< Wilson interval gate: z² value (0 = off, 3.8416 = 95% CI,
                                      ///< 6.6349 = 99% CI). When >0 takes precedence over stderr/vt.
                                      ///< Trust if Wilson LB > 1−ε OR UB < ε. SPP-adaptive: small N
                                      ///< → wide interval → no trust regardless of μ̂ point estimate.
    float  gWilsonEps;                ///< Margin for "definitely visible/occluded" Wilson trust
                                      ///< decision. 0.01 = trust when 95% CI is within 1% of corner.
    float  gMuShrinkZSquared;         ///< Agresti-Coull shrinkage on the cached cell μ:
                                      ///< μ̃ = (X + z²/2) / (N + z²). 0 = off (raw μ = X/N).
                                      ///< 4 = "add 2,4" form (95% CI Beta(2,2) prior, pulls extreme
                                      ///< μ values away from 0/1 at low N). Affects μ AND
                                      ///< var = μ̃(1−μ̃) consumed by trust gates and CV+RRR.
                                      ///< Orthogonal to the trust gate; changes WHAT the cache
                                      ///< stores, not WHEN we trust it. See
                                      ///< .plans/agresti-coull-shrinkage.md.
    // NOTE 2026-05-06: gCtSppScaleK / gVtSppScaleK were considered but
    // pulled — this codebase accumulates frames at PathTracer SPP=1, so
    // gSpp = mStaticParams.samplesPerPixel = 1 always and any SPP-scaling
    // collapses to a fixed multiplier. Param scaling that needs the
    // virtual-SPP context lives in the test harness (Python-side); the
    // algorithm sees a single concrete vt/ct per render. See
    // .plans/wilson-interval-prototype.md for the full reasoning.
    uint   gEnableHierarchicalConsistency; ///< 1 = peek next level μ for agreement check.
    float  gHierarchicalMuTolerance;  ///< |μ_next − μ_this| gate for the hierarchical check.
    float  gAccelDecayDisagreeThresh; ///< |sample − μ| that triggers in-insert half-decay. 0 = off.
    uint   gMLAlphaFloorN;            ///< MLE α-floor target N* (MCPG 2025). When >0 and total ≥ N*, 1/8 inline decay
                                      ///< gives effective α ≈ 1/N*. 0 = off (legacy 16-bit overflow at 57344 only).
    uint   gBootThresholdFine;        ///< Per-level-fine variant of gBootThreshold. When nonzero,
                                      ///< the effective required-sample count at level L is a
                                      ///< linear interp from gBootThreshold (coarse, L=0) to
                                      ///< gBootThresholdFine (fine, L=numLevels-1). 0 = off
                                      ///< (uniform gBootThreshold across all levels, legacy).
    float  gJitterFilter;    ///< F: per-position-seed jitter scale (soft cell boundaries, 3D filter kernel). 0 = off.
    float  gJitterCell;      ///< F: per-cell-index-seed jitter scale [Binder 2018] (per-cell shift, hard boundaries). 0 = off.
    uint   gDiagAccumWindow; ///< EMA window size for accumulated diagnostics (0 = all frames)
    uint   gFrameCount;      ///< Current frame index for per-frame RNG variation
    uint   gSpp;             ///< Samples per pixel (matches PathTracer; used as RNG frame stride)
    float  gCameraPosX;      ///< Camera world-space X (for footprint estimation)
    float  gCameraPosY;      ///< Camera world-space Y
    float  gCameraPosZ;      ///< Camera world-space Z
    float  gPixelSize1;      ///< Pixel world-space size at unit depth (2*length(cameraU)/frameDim.x)
    uint   gBayerN;           ///< N×N Bayer gate (1 = disabled, 2 = 2×2/4 subframes, 4 = 4×4/16 subframes)
    uint   gWarmupFirst;      ///< # Bayer slots write-only in frame 0 (force trace, no RR)
    uint   gWarmupRun;        ///< # Bayer slots write-only in every subsequent frame
    // --- §9.4 World-space ReSTIR DI reservoirs ---
    uint   gWSEnable;             ///< 1 = WS reservoir buffer active.
    uint   gWSCellLevel;          ///< WS-ReSTIR cell level into VisCache's posA cascade (0=coarse..N-1=fine).
    uint   gWSCapacity;           ///< Power-of-two reservoir slot count.
    float  gWSMCap;               ///< Temporal M-cap for reservoir merge.
    uint   gWSSpatialNeighbours;  ///< Neighbour cells gathered during spatial reuse (0..4).
    float  gWSLightMuMin;         ///< ε-floor for cached μ in target p̂ (defensive sampling).
    float  gWSLightSoftness;      ///< Softening of cached μ in target p̂. 0=uniform, 1=full trust.
    uint   gWSNormalAddr;         ///< 1 = fold 6-axis face-normal bin into the WS cell hash.
    uint   gWSInitialCandidates;  ///< K fresh per-pixel candidates per frame (RTXDI parity, default 8).
    uint   gWSFrameDimX;          ///< Frame width  (for indexing per-pixel reservoir buffer).
    uint   gWSFrameDimY;          ///< Frame height.
    uint   _wsPad0;               ///< (was gWSJitterFilter — now reused via VisCache's gJitterFilter)
    uint   _wsPad1;               ///< (was gWSJitterCell   — now reused via VisCache's gJitterCell)
    uint   gWSUseCellInRIS;       ///< 1 = WS cell candidate active; 0 = pure per-pixel ReSTIR.
    uint   gWSVisInPHat;          ///< 0=blind, 1=cache-amortized, 2=explicit-always-trace.
    // --- §9.4 WS-cascade ReGIR cell pool (multi-light pool per cell) ---
    uint   gWSCellPoolEnable;     ///< 1 = pool buffer active. Master gate for ReGIR step (a)+.
    uint   gWSCellPoolCapacity;   ///< Power-of-two pool slot count (table size).
    uint   gWSCellPoolDrawK;      ///< K candidates drawn from pool per pixel (0 = read disabled).
    uint   gWSCellLevelJitter;    ///< Stochastic LOD jitter (0 = off; one-sided truncated exp [0, J] *above* gWSCellLevel, MCPG 2025).
    uint   gWSSpatialPixelsK;     ///< Per-pixel screen-space spatial-reuse neighbour count (default 4).
    uint   gWSSpatialPixelsRadius;///< Spatial-reuse search radius in pixels (default 32).
    uint   gWSPoolAddrMode;       ///< 0 = 3D cell (default), 1 = 2D screen-tile (RTXDI-style).
    uint   gWSPoolTileSize;       ///< Tile edge in pixels (default 16). Only used when AddrMode=1.
    // §4.2 posB solid-angle quantization (Option B — posA-cell-coupled).
    // alpha (angular cell, octahedral units) = (cellSizeA / gPosACoarse) * gDirSolidAngleScale,
    // clamped to [kAlphaMin=0.05, kAlphaMax=0.5] (≈ 3°..30°).
    // log_step (radial) = log(1 + alpha * gDistSolidAngleScale).
    // Near-dist cutoff: dist < cellSizeA → single-bucket fallback (direction sub-resolvable).
    float  gDirSolidAngleScale;   ///< Anisotropy knob for angular axis. Default 1.0.
    float  gDistSolidAngleScale;  ///< Anisotropy knob for distance axis. Default 1.0.
    uint   gWSCellReservoirMerge; ///< 0 = legacy identity-hint cell read (default; preserves wsrestir).
                                  ///< 1 = promote cell to full Bitterli weighted merge (uses cell.W,
                                  ///< cell.M like the per-pixel temporal read). World-space analog of
                                  ///< the per-pixel reservoir, NO reprojection needed (cell ID is
                                  ///< camera-invariant). Used by the `restir_3d` variant.
    uint   gWSCellPoolFootprintPx;///< 0 = use gWSCellLevel for pool addressing (legacy fixed level).
                                  ///< >0 = footprint-derived level: per-pixel, pick the cascade
                                  ///< level whose cell projects to ~footprint² screen pixels at this
                                  ///< primary hit (via shared vhfLevelForFootprint). e.g. 16 → 256
                                  ///< px tile-equivalent footprint, matching restir_2d's tile size.
    uint   gWSRetraceOnReuseMode; ///< Retrace V on reservoir temporal/spatial reuse — RTXDI
                                  ///< BiasCorrection analog. 0 = Off (Basic-equiv: stored W carries
                                  ///< write-time V), 1 = FullTrace (≡ RTXDI RayTraced), 2 = CacheCV
                                  ///< (cheap CV+RRR via evalRevalidationCV with PT-canonical knobs).
};

// ---------------------------------------------------------------------------
// Geometric interpolation from coarsest to finest cell size per dimension.
// t = 0 → coarse (level 0), t = 1 → fine (level N-1).
// When numLevels == 1, returns coarse.
// ---------------------------------------------------------------------------
float vhfInterp(float coarse, float fine, int lvl)
{
    float t = (gNumLevels <= 1u) ? 0.f : float(lvl) / float(gNumLevels - 1u);
    return coarse * exp(t * log(max(fine, 1e-6f) / max(coarse, 1e-6f)));
}

float vhfPosASize(int lvl)      { return vhfInterp(gPosACoarse,  gPosAFine,  lvl); }

/// Estimated screen-space pixel count for a cell at the given level and depth.
/// cellSize² / pixelSize² where pixelSize = depth * gPixelSize1.
uint vhfCellPixels(int lvl, float3 posA)
{
    float cellSize = vhfPosASize(lvl);
    float3 camPos = float3(gCameraPosX, gCameraPosY, gCameraPosZ);
    float depth = max(length(posA - camPos), 0.001f);
    float pixelSize = depth * gPixelSize1;
    float ratio = cellSize / max(pixelSize, 1e-6f);
    return uint(max(ratio * ratio, 1.f));
}

/// Inverse of vhfCellPixels: cascade level whose cell at this primary hit
/// projects to ~targetFootprintPx² screen pixels. Shared canonical helper
/// — both VisCache and the WS-ReSTIR pool address by it. Picks the level
/// that minimises log-distance to targetCellSize = sqrt(targetFootprintPx)
/// × pixelSize. Output clamped to [0, gNumLevels-1].
///
/// Use cases:
///   - WS-cell-pool entry level: targetFootprintPx ≈ tileSize² (256 for
///     16×16 tile) → cell screen footprint matches RTXDI tile pre-sample.
///   - VisCache lookup entry: same idea applied to vhfLookup's start level
///     so insertion and lookup converge on the same posA cascade level
///     based on observed pixel footprint, not a fixed gWSCellLevel.
int vhfLevelForFootprint(float3 posA, float targetFootprintPx)
{
    if (gNumLevels <= 1u) return 0;
    float3 camPos = float3(gCameraPosX, gCameraPosY, gCameraPosZ);
    float depth = max(length(posA - camPos), 0.001f);
    float pixelSize = depth * gPixelSize1;
    float targetCellSize = sqrt(max(targetFootprintPx, 1.f)) * max(pixelSize, 1e-6f);
    // Solve vhfPosASize(lvl) ≈ targetCellSize for lvl. Geometric interp:
    //   cellSize(t) = posACoarse · (posAFine/posACoarse)^t,  t = lvl/(N-1)
    //   t = log(targetCellSize/posACoarse) / log(posAFine/posACoarse)
    float lo = log(max(gPosACoarse, 1e-6f));
    float hi = log(max(gPosAFine,   1e-6f));
    float denom = (hi - lo);
    if (abs(denom) < 1e-6f) return 0;
    float t = (log(max(targetCellSize, 1e-6f)) - lo) / denom;
    int lvl = int(round(t * float(gNumLevels - 1u)));
    return clamp(lvl, 0, int(gNumLevels) - 1);
}
float vhfPosBSize(int lvl)      { return vhfInterp(gPosBCoarse,  gPosBFine,  lvl); }
float vhfDirBSize(int lvl)      { return vhfInterp(gDirBCoarse,  gDirBFine,  lvl); }
float vhfDistSize(int lvl)      { return vhfInterp(gDistBCoarse, gDistBFine, lvl); }

/// The hash table — RWStructuredBuffer so all threads can read and atomically
/// update entries concurrently. Bound by the host via dict["vhfTable"].
RWStructuredBuffer<VHFEntry> gVHFTable;

// ===========================================================================
// HASH FUNCTIONS
// ===========================================================================

// ---------------------------------------------------------------------------
// PCG3D: permuted congruential generator for 3D hashing.
// Two rounds of multiply-add-xor-shift produce high-quality, uncorrelated
// hash values from integer coordinates. Used for both address computation
// and fingerprint generation.
//
// Reference: Jarzynski & Olano, "Hash Functions for GPU Rendering", JCGT 2020
// ---------------------------------------------------------------------------
uint3 pcg3d(uint3 v)
{
    v = v * 1664525u + 1013904223u;
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    v ^= v >> 16u;
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    return v;
}

// ---------------------------------------------------------------------------
// PCG6D: 6-dimensional hash for endpoint pairs (qa, qb).
// Extends the Jarzynski & Olano PCG pattern to 6 components so all 6
// quantized coordinates contribute independently — no information loss
// from XOR reduction. Each component is cross-mixed with products of
// pairs from the other 5 components (circular neighbor pattern).
//
// Returns 6 hash values; callers typically XOR-fold to the needed width.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// pcgHash: 9-dimensional hash for cache entry addressing.
// Inputs: qa.xyz (3) + qb.xyz (3) + lvlA (1) + lvlB (1) + salt (1) = 9.
//
// qa/qb: quantized endpoint coordinates (6D spatial key).
// lvlA/lvlB: independent LOD levels for each endpoint (currently synced,
//   lvlB reserved for future independent A/B level control).
// salt: differentiates address from fingerprint without coordinate offsets.
//
// Extends Jarzynski & Olano's PCG cross-mixing to 9 components.
// Two rounds of circular neighbor products + XOR-shift.
// Returns XOR-folded uint.
//
// 9 is odd, which breaks perfect circular symmetry — acceptable since the
// inputs ARE asymmetric (positions vs levels vs salt).
// ---------------------------------------------------------------------------
/// Hash one endpoint: int3 coords + level + salt → uint.
/// PCG-style: LCG init, 2 rounds of circular cross-mix, XOR-fold.
uint pcgHashEndpoint(int3 q, uint lvl, uint salt)
{
    uint a = uint(q.x) * 1664525u + 1013904223u;
    uint b = uint(q.y) * 1664525u + 1013904223u;
    uint c = uint(q.z) * 1664525u + 1013904223u;
    uint d = lvl        * 1664525u + 1013904223u;
    uint e = salt       * 1664525u + 1013904223u;

    a += b * e;  b += c * a;  c += d * b;  d += e * c;  e += a * d;
    a ^= a >> 16u;  b ^= b >> 16u;  c ^= c >> 16u;  d ^= d >> 16u;  e ^= e >> 16u;
    a += b * e;  b += c * a;  c += d * b;  d += e * c;  e += a * d;

    return a ^ b ^ c ^ d ^ e;
}

// Per-dimension salt constants — each dimension gets its own hash space.
static const uint kSaltA    = 0x12345678u;
static const uint kSaltB    = 0x9E3779B9u;
static const uint kSaltDist = 0x6C62272Eu;

/// Hash one dimension. posB modes reuse pcgHashEndpoint with kSaltDist for distance
/// (distance is qb.z in dirdist mode, or a constant in pos×pos mode).
/// Per-dimension hash functions. Same calls in rendering and diagnostics.
uint pcgHashA(int3 qa, uint lvlA) { return pcgHashEndpoint(qa, lvlA, kSaltA); }
uint pcgHashB(int3 qb, uint lvlB) { return pcgHashEndpoint(qb, lvlB, kSaltB); }
uint pcgHashDist(uint lvlDist)     { return pcgHashEndpoint(int3(0), lvlDist, kSaltDist); }

/// Combined hash: hashA ^ hashB ^ hashDist ^ salt.
/// salt differentiates address from fingerprint (applied to final output only).
uint pcgHash(int3 qa, int3 qb, uint lvlA, uint lvlB, uint lvlDist, uint salt)
{
    return pcgHashA(qa, lvlA) ^ pcgHashB(qb, lvlB) ^ pcgHashDist(lvlDist) ^ salt;
}


// ===========================================================================
// DIRECTIONAL ENCODING — shared by IBL and dirdist addressing
// ===========================================================================

// ---------------------------------------------------------------------------
// Octahedral direction encoding: maps unit sphere → [−1,1]² near-uniformly.
// Used for both IBL direction encoding and dirdist addressing to quantize
// directions as 2D bins independently of spatial cell size.
// Reference: Meyer et al. 2010, "On Floating-Point Normal Vectors"
// ---------------------------------------------------------------------------
float2 octEncode(float3 n)
{
    float s = abs(n.x) + abs(n.y) + abs(n.z);
    float2 o = n.xy / max(s, 1e-7f);
    if (n.z < 0.f)
        o = (1.f - abs(o.yx)) * float2(o.x >= 0.f ? 1.f : -1.f, o.y >= 0.f ? 1.f : -1.f);
    return o;  // in [−1, 1]²
}

/// Legacy quantization (linear distance, fixed cell sizes per level).
/// Kept for back-compat with the pos×pos env-ray path.
int3 vhfQuantizeDirection(float3 dir, float angularCellSize, float dist, float distCellSize)
{
    float2 oct = octEncode(dir) + 1.f;  // now in [0, 2]
    float angCell = max(angularCellSize, 0.01f);
    int2 dirBin = int2(round(oct / angCell));
    int distBin = int(round(dist / max(distCellSize, 0.01f)));
    return int3(dirBin.x, dirBin.y, distBin);
}

/// §4.2 Option B — solid-angle posB quantization (posA-cell-coupled).
///
/// Angular cell α and radial step both derive from posA's cell size at this
/// level — one length scale per cascade level drives both axes. The user
/// knobs `gDirSolidAngleScale` and `gDistSolidAngleScale` (default 1.0 each)
/// scale the two axes independently for anisotropy.
///
///     α      = clamp((cellA / gPosACoarse) × gDirSolidAngleScale, αMin, αMax)
///     logStep = log(1 + α × gDistSolidAngleScale)
///     dirBin = round(octEncode(dir) / α)
///     distBin = round(log(d / cellA) / logStep)
///
/// Near-dist fallback: when `d < cellA`, direction is sub-cell-resolvable
/// (any small posA perturbation swings it widely). Returns a single-bucket
/// sentinel `int3(0, 0, 0)` so all near-dist queries from the same posA
/// share one slot — matches the posA-only behavior for the near regime.
///
/// α bounds: [0.05, 0.5] in octahedral units ≈ [3°, 30°] per bin. Outside
/// this range the cache either has too many empty cells (α too small) or
/// loses direction discrimination (α too coarse).
int3 vhfQuantizeDirectionSA(float3 dir, float dist, float cellA)
{
    if (dist < cellA) return int3(0, 0, 0);  // single-bucket near-dist fallback

    const float kAlphaMin = 0.05f;   // ≈ 3° per bin (1/64 hemisphere)
    const float kAlphaMax = 0.5f;    // ≈ 30° per bin (1/8 hemisphere)
    float alphaRaw = (cellA / max(gPosACoarse, 1e-6f)) * max(gDirSolidAngleScale, 1e-3f);
    float alpha = clamp(alphaRaw, kAlphaMin, kAlphaMax);

    float logStep = log(1.f + alpha * max(gDistSolidAngleScale, 1e-3f));
    if (logStep < 1e-6f) logStep = 1e-3f;  // safety against degenerate scale

    float2 oct = octEncode(dir) + 1.f;  // [0, 2]
    int2 dirBin = int2(round(oct / alpha));
    int distBin = int(round(log(max(dist / cellA, 1e-6f)) / logStep));
    return int3(dirBin.x, dirBin.y, distBin);
}

// ---------------------------------------------------------------------------
// IBL direction encoding: for env maps and directional lights (infinite distance).
// Returns a posB that, when passed to vhfQuantizePair, produces directional bins.
// Uses octahedral mapping with coarse angular resolution (~4 bins = octant level).
//
// In dirdist mode: IBL is handled by vhfQuantizeDirection in vhfQuantizePair
// with distBin = 0 (infinite). In endpoint mode: this function encodes
// direction as a far-away position for spatial quantization.
// ---------------------------------------------------------------------------
static const float kIBLAngularCell = 0.785f;  ///< ~45 degrees for endpoint mode fallback

float3 vhfEncodeDirection(float3 dir)
{
    float marker = gPosACoarse / kIBLAngularCell;
    return dir * marker;
}

// ===========================================================================
// SPATIAL QUANTIZATION
// ===========================================================================

// ---------------------------------------------------------------------------
// Jitter-before-quantize — two stackable modes, each a float scale (0 = off).
//
// Both modes are conceptually anticipated in [Kugelmann 2006 §3.2.2], which
// lists "the location of the query point" (per-position grouping) and "the
// occupied grid cell" (per-cell grouping) as criteria for defining "nearby"
// samples in a cache. We instantiate both as orthogonal jitter modes:
//
//   jitterFilter (per-POSITION seed, `asuint(pos) ^ seed`):
//     Each position gets independent jitter → stochastic/soft cell boundaries.
//     Neighboring positions near a boundary have a chance of landing in either
//     cell, effectively acting as a 3D reconstruction kernel over the grid.
//     This is the [Binder/Fricke/Keller 2018 §2.1] formulation:
//     "jittering realizes the stochastic evaluation of filter kernels".
//     [Alber/Hanika/Dachsbacher 2025] (MCPG, merian-quake/mc.glsl
//     `grid_idx_interpolate(pos, w, rand)`) restates the same mechanism.
//
//   jitterCell (per-CELL-INDEX seed, `baseIdx ^ seed`):
//     All positions in the same cell get identical jitter → each cell shifts
//     as a unit → boundaries stay hard but the regular grid is de-aligned
//     from scene geometry. Different bias defence than filterJitter: removes
//     systematic alignment artefacts (axis-aligned scene features falling on
//     cell planes) without mixing samples across cells. Conceptual root:
//     [Teschner et al. 2003] spatial-hash on cell indices; we re-randomize
//     each cell's effective center.
//
// Both scales are in units of "cells": 1.0 = standard ±0.5-cell offset at the
// current level's cellSize (so multi-level caches auto-scale). >1 widens the
// jitter range. When both non-zero, the offsets are summed.
//
// The seed parameter allows different jitter for posA vs posB (0xAA vs 0xBB),
// preventing systematic correlation between endpoints. The level index is
// XORed into the seed so different LOD levels get independent patterns.
// ---------------------------------------------------------------------------
int3 jitterQuantize(float3 pos, float cellSize, uint seed)
{
    int3 baseIdx = int3(round(pos / cellSize));
    if (gJitterFilter == 0.f && gJitterCell == 0.f)
        return baseIdx;

    float3 offset = float3(0.f);
    if (gJitterFilter != 0.f)
    {
        uint3 r = pcg3d(asuint(pos) ^ seed);
        float3 j = float3(r & 0xFFFFu) / 65535.0f - 0.5f;
        offset += j * gJitterFilter;
    }
    if (gJitterCell != 0.f)
    {
        uint3 r = pcg3d(uint3(baseIdx) ^ seed);
        float3 j = float3(r & 0xFFFFu) / 65535.0f - 0.5f;
        offset += j * gJitterCell;
    }
    return int3(round((pos + offset * cellSize) / cellSize));
}

// ===========================================================================
// ADDRESSING MODES
// ===========================================================================

// ---------------------------------------------------------------------------
// vhfAddressPosB: compute the posB used for cache addressing.
//
// Two modes (compile-time switch USE_VISCACHE_DIRDIST_ADDRESSING):
//
// Endpoint mode (default): posB = target position.
//   Each unique light sample position maps to a different posB cell.
//   Works well when few light positions exist (point lights, small area lights).
//   With large area lights, samples scatter across many posB cells.
//
// Dir+dist mode: posB = posA + dir * quantized_distance.
//   Groups all light samples in the same direction bin and distance bin.
//   Much better sample accumulation for area lights and env maps.
//   Distance quantization is coarse (4× coarsest cell size, log-scaled).
//   No canonicalization — direction is asymmetric (V(A→B) ≠ V(B→A) key).
// ---------------------------------------------------------------------------
/// Sentinel distance encoding "env ray" in the pos cascade. Picked finite
/// and large-but-safe-int32 (posB coord stays ≤ 1e6 × dir which quantizes
/// fine at any cell size ≥ 1e-10). vhfQuantizePair checks `length(posB-posA)
/// == kEnvSentinelDist` to switch into direction-binned quantization.
static const float kEnvSentinelDist = 1.0e6f;

float3 vhfAddressPosB(float3 posA, float3 dir, float dist)
{
    // Env/directional rays: Falcor passes dist = kRayTMax (1e30) / FLT_MAX.
    // Raw multiply overflows int32 in quantization (blob 148 vs fixed 98 at
    // Sponza x1). Route env rays onto a sentinel distance that vhfQuantizePair
    // detects and switches to dir_dist-style direction binning for, matching
    // how dir_dist addressing handles env correctly via its "infinity" distBin.
    if (dist > 1e10f)
        return posA + dir * kEnvSentinelDist;
    return posA + dir * dist;
}

// ---------------------------------------------------------------------------
// Canonical quantization: quantize both endpoints and lexicographic-swap
// so that V(A,B) and V(B,A) always produce the same (qa, qb) pair.
//
// Canonicalization: in pos×pos mode, if posA == posB (same resolution for
// both endpoints), V(A,B) = V(B,A) so we lexicographic-swap to halve table
// pressure. If posA != posB, endpoints have different resolutions — no swap.
// In dirdist mode: direction is inherently asymmetric — never canonicalize.
//
// The canonicalize flag is constant per frame (depends only on coarse values),
// so it's checked once outside the per-level loop by the caller.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Hash-based canonicalization: sort endpoints by a quick scalar hash of their
// quantized coordinates. This is position-independent — no coordinate-sign
// sensitivity. The same pair always gets the same canonical form regardless
// of where in the scene it is, eliminating the left/right asymmetry from
// lexicographic comparison on raw (possibly negative) coordinates.
// ---------------------------------------------------------------------------
/// Scalar hash of quantized cell coords — for diagnostic visualization only.
uint vhfCellHash(int3 q)
{
    return uint(q.x) * 0x9e3779b9u ^ uint(q.y) * 0x517cc1b7u ^ uint(q.z) * 0x6c62272eu;
}

/// Lexicographic comparison for canonicalization: returns true if a < b.
/// Collision-free — unlike scalar hash, distinct int3 values always get
/// a deterministic ordering.
bool vhfCanonicalLess(int3 a, int3 b)
{
    if (a.x != b.x) return a.x < b.x;
    if (a.y != b.y) return a.y < b.y;
    return a.z < b.z;
}

// Canonicalization disabled — posB is always coarser than posA (3× by convention),
// and normal addressing makes qa/qb asymmetric. No V(A,B)==V(B,A) assumption.
// To re-enable: uncomment kCanonicalize and the swap block in vhfQuantizePair.
// #if !USE_VISCACHE_DIRDIST_ADDRESSING
// static const bool kCanonicalize = (gPosACoarse == gPosBCoarse)
//                                && !(gFlags & kFlag_EnableNormalAddr);
// #endif

void vhfQuantizePair(float3 posA, float3 posB, float cellSizeA, uint lvl,
                     out int3 qa, out int3 qb, float3 normalA = float3(0.f))
{
    qa = jitterQuantize(posA, cellSizeA, 0xAAu ^ lvl);

    // Normal addressing: octahedral-encode normalA and fold into qa hash.
    // This splits cells by surface orientation — same position but different
    // normals (e.g., floor vs wall at a corner) get separate cache entries.
    if (gFlags & kFlag_EnableNormalAddr)
    {
        float2 oct = octEncode(normalA) + 1.f;  // [0, 2]
        // Coarse normal bins: ~6 bins (60° per bin) — separates
        // floor/wall/ceiling without excessive subdivision.
        float normCellOct = max(gNormalACoarse, 1.f) / 90.f;  // degrees → octahedral cell size
        int2 nBin = int2(floor(oct / normCellOct));
        // XOR-fold into qa to change the hash without adding dimensions.
        qa.x ^= nBin.x * 0x45D9F3Bu;
        qa.y ^= nBin.y * 0xC3A5C85Cu;
    }

#if USE_VISCACHE_DIRDIST_ADDRESSING
    // §4.2 Dir+dist Option B: posA-cell-coupled solid-angle quantization.
    // Angular bin α and log-distance step both derive from cellSizeA;
    // gDirSolidAngleScale + gDistSolidAngleScale tune the two axes.
    // Env rays (sentinel dist) land in distBin=0 infinity slot via the
    // log formula's saturation at large d.
    {
        float3 edge = posB - posA;
        float dist = length(edge);
        float3 dir = dist > 1e-6f ? edge / dist : float3(0.f, 1.f, 0.f);
        if (abs(dist - kEnvSentinelDist) < 1.f)
        {
            // Env ray: fixed coarse angular bin, distBin = sentinel max.
            float2 oct = octEncode(dir) + 1.f;
            int2 dirBin = int2(round(oct / 0.5f));  // 30° bins for env
            qb = int3(dirBin.x, dirBin.y, 0x7FFF);
        }
        else
        {
            qb = vhfQuantizeDirectionSA(dir, dist, cellSizeA);
        }
    }
#else
    // Pos×pos: env rays are routed to a sentinel distance (vhfAddressPosB).
    // Detect via edge magnitude and route them through dir_dist-style direction
    // binning with distBin=0 — the "infinity slot" matches what dir_dist
    // addressing inherently does for env rays.
    float3 edgeB = posB - posA;
    float distB  = length(edgeB);
    if (abs(distB - kEnvSentinelDist) < 1.f)
    {
        float3 dir = distB > 1e-6f ? edgeB / distB : float3(0.f, 1.f, 0.f);
        float angCellOct = max(vhfDirBSize(lvl), 1.f) / 90.f;
        qb = vhfQuantizeDirection(dir, angCellOct, 0.f, 1.f);  // distBin=0 = env slot
    }
    else
    {
        float posBCell = vhfPosBSize(lvl);
        qb = jitterQuantize(posB, posBCell, 0xBBu ^ lvl);
    }

    // Canonicalization disabled — asymmetric endpoints (posB coarser, normal on A only).
#endif
}

// ===========================================================================
// ADDRESS AND FINGERPRINT
// ===========================================================================

// ---------------------------------------------------------------------------
// Two independent hash chains from the same quantized cell pair.
//
// vhfAddr: primary hash → table slot address (masked to table size).
//   Uses the XOR of both endpoints' coordinates plus a level-dependent
//   offset (golden ratio constant 0x9e3779b9) for good distribution.
//
// vhfFingerprint: secondary hash → collision detection tag.
//   Uses different additive constants (+7, +13, 0xdeadbeef) to ensure
//   statistical independence from the address hash. Two different cell
//   pairs that collide in address will almost certainly have different
//   fingerprints (collision probability ~2^-32).
//
// Both use PCG3D for high-quality mixing of the 6 integer coordinates
// (3 from each quantized endpoint).
// ---------------------------------------------------------------------------
uint vhfAddr(int3 qa, int3 qb, uint lvlA, uint lvlB, uint lvlDist)
{
    return pcgHash(qa, qb, lvlA, lvlB, lvlDist, 0x12345678u) & (gTableCapacity - 1u);
}

uint vhfFingerprint(int3 qa, int3 qb, uint lvlA, uint lvlB, uint lvlDist)
{
    uint fp = pcgHash(qa, qb, lvlA, lvlB, lvlDist, 0xDEADBEEFu);
    return fp == 0u ? 1u : fp;  // Reserve 0 as empty-slot sentinel
}

// ===========================================================================
// SLOT FINDING (DOUBLE HASHING WITH EVICTION)
// ===========================================================================

// ---------------------------------------------------------------------------
// Double-hash probe sequence [Binder et al. 2018]:
//
// When the primary slot is occupied by a different fingerprint, we probe
// subsequent slots using a second hash h2 derived from the fingerprint.
// h2 is forced odd (|1) to guarantee full table traversal (since table
// size is a power of two, an odd step size is coprime with the table size).
//
// Pressure-scaled eviction: at probe steps >= kEvictStartStep, we check
// whether the existing entry has accumulated enough samples to be worth
// keeping. Entries with fewer than (kEvictBaseCount << (step - kEvictStartStep))
// samples are evictable. This means:
//   - Steps 0-2: never evict (protected zone)
//   - Step 3: evict if total < 8
//   - Step 4: evict if total < 16
//   - Step 5: evict if total < 32  ...etc.
//
// This graduated pressure ensures established entries survive while new
// entries can claim slots at deeper probe depths when the table is full.
//
// Tuning constants (compile-time, not runtime — these rarely need changing):
// ---------------------------------------------------------------------------
static const uint kMaxProbe        = 8u;      ///< Max probe steps before giving up (controls worst-case lookup time)

// --- gFlags bitfield constants ---
// Assumption: flags are fixed per run (set once at startup, never toggled at runtime).
// Runtime toggling of flags that drive side-effects on insert/evict paths would
// leak stale per-slot state until the next full cache turnover.
static const uint kFlag_EnableAdaptivePMin    = 1u << 0;
static const uint kFlag_EnableNormalAddr      = 1u << 1;
static const uint kFlag_EnableBootstrapBreak  = 1u << 2;
static const uint kFlag_EnableParentPreinit   = 1u << 3;
// ---------------------------------------------------------------------------
// vhfBayerWarmup: returns true if this pixel is in write-only warmup mode
// this frame. The caller should force trace + write (skip RR read) when true.
//
// Bayer slot index: (x mod N) + (y mod N) * N, range [0, N²).
// Frame 0  → (slot − 0)       mod N² < gWarmupFirst
// Frame >0 → (slot − offset)  mod N² < gWarmupRun, offset = gFrameCount mod N²
//
// The frame-count offset rotates which slots are write-only each frame so
// every Bayer slot eventually takes a turn being warmup. Without rotation
// the same low-index slots would be permanently sacrificed for cache
// population and never get to use their own gated result.
// ---------------------------------------------------------------------------
bool vhfBayerWarmup(uint2 pixel)
{
    uint N = max(gBayerN, 1u);
    uint N2 = N * N;
    uint slot = (pixel.x % N) + (pixel.y % N) * N;
    uint activeSlots = (gFrameCount == 0u) ? gWarmupFirst : gWarmupRun;
    uint offset = gFrameCount % N2;
    uint shifted = (slot + N2 - offset) % N2;
    return shifted < activeSlots;
}
static const uint kEvictStartStep  = 3u;      ///< First probe step that may evict (lower = more aggressive eviction)
static const uint kEvictBaseCount  = 8u;      ///< Min total_count to survive eviction at kEvictStartStep
static const uint kOverflowTrigger = 0xE000u; ///< Inline decay fires when total > this (~57K of 65535 max)
static const uint kDecayShift      = 3u;      ///< Decay strength: subtract value >> shift (shift=3 keeps 7/8)

/// Find a slot for the given (addr, fingerprint) pair.
///
/// When allowInsert is false (lookup mode): returns the slot index if found,
/// or -1 if the entry doesn't exist.
///
/// When allowInsert is true (insert mode): also considers empty slots and
/// evictable entries as valid return values.
int vhfFindSlot(uint addr0, uint fp, bool allowInsert, out uint probeSteps)
{
    uint h2 = fp | 1u;  // Odd step → coprime with power-of-two table → full traversal
    for (uint i = 0u; i < kMaxProbe; i++)
    {
        uint slot = (addr0 + i * h2) & (gTableCapacity - 1u);
        uint efp  = gVHFTable[slot].fingerprint;

        // Exact match — this slot holds our cell pair's data.
        if (efp == fp)
        {
            probeSteps = i;
            return int(slot);
        }

        // Empty slot — no entry was ever placed here or beyond.
        // Eviction replaces (never empties), so empty = chain end.
        if (efp == 0u && gVHFTable[slot].packed == 0u)
        {
            probeSteps = i;
            return allowInsert ? int(slot) : -1;
        }

        if (allowInsert)
        {

            // Pressure-scaled eviction: deeper probe steps can evict
            // entries with few samples. This prevents probe chains from
            // growing unboundedly at high load factors.
            if (i >= kEvictStartStep)
            {
                uint total = gVHFTable[slot].packed & 0xFFFFu;
                uint threshold = kEvictBaseCount << (i - kEvictStartStep);
                if (total < threshold)
                {
                    probeSteps = i;
                    return int(slot);  // Evict this low-sample entry
                }
            }
        }
    }
    probeSteps = kMaxProbe;
    return -1;  // No slot found within kMaxProbe steps
}

// ===========================================================================
// LOOKUP — COARSE-TO-FINE CASCADE
// ===========================================================================

// ---------------------------------------------------------------------------
// vhfLookup: iterate from coarsest to finest level, returning the finest
// level that has a mature (trusted) entry.
//
// The cascade stops early in three cases:
//   1. No entry found at this level (slot < 0) — finer levels can't help
//   2. Entry has too few samples (total < bootThreshold) — not yet trusted
//   3. Variance is low (var <= varThreshold) — converged region, finer
//      levels would produce the same estimate
//
// Early stop #3 is the key optimization: in fully lit or fully shadowed
// regions, the coarsest level converges quickly (mu ≈ 1 or mu ≈ 0,
// var ≈ 0), and the cascade never descends. Only at shadow penumbrae
// (mu ≈ 0.5, var ≈ 0.25) does the cascade go deeper to resolve detail.
//
// Returns VHFResult with valid=false on cold miss (no mature entry at any
// level), which tells the caller to trace unconditionally.
// ---------------------------------------------------------------------------
VHFResult vhfLookup(float3 posA, float3 posB, float3 normalA = float3(0.f))
{
    VHFResult best;
    best.mu    = 0.5f;   // Default: uncertain (max variance)
    best.var   = 0.125f; // Half of max Bernoulli variance (0.25/2)
    best.level = -1;
    best.probeSteps = 0u;
    best.N     = 0u;
    best.valid = false;
    best.qa = int3(0);
    best.qb = int3(0);

    // fd selects a per-pixel TARGET level where cellPx ≤ threshold.
    // Entry starts ~2 doublings coarser than target so neighboring coarse
    // levels get populated and the cascade can early-stop at coarse if μ
    // already converged. Analytical formula (log-based) avoids a linear
    // scan so numLevels can be huge (e.g. 32000) without cost. "2 steps
    // back" is expressed in doublings-of-cell-size so the prefill breadth
    // stays constant regardless of numLevels.
    //
    // Pick the integer level whose cell size is closest to the per-pixel
    // target (depth × pixelSize × √fd). At small N (e.g. 32) consecutive
    // levels are meaningful cell-size steps (~25% each), so we don't need
    // strided iteration — visit a fixed window [target-A, target+B] around
    // the entry. Round-to-nearest so all rays hashing the same world cell
    // hit the same fingerprint (vhfFingerprint includes the lvl index).
    //
    // LOOKUP starts AT targetLvl — never reads from cells COARSER than
    // the per-pixel footprint. A coarser cell averages over more screen
    // area than the pixel covers, so its stored μ is wrong-by-aggregation
    // for that pixel. The back-window (kCascadeWindowBack) exists only
    // for INSERT to backfill coarser cells (amortization across nearby
    // pixels), but reads must use cells ≤ target footprint size.
    int kWindowFwd = int(gCascadeWindowForward);  // runtime-tunable; 0=entry-only debug
    float lookupLogRatio = log(max(gPosAFine, 1e-6f) / max(gPosACoarse, 1e-6f));

    int startLvl = 0;
    int endLvl   = int(gNumLevels);
    if (gForceDescendFootprintPx != 0u && gNumLevels > 1u && lookupLogRatio < -1e-6f)
    {
        float3 camPos = float3(gCameraPosX, gCameraPosY, gCameraPosZ);
        float depth = max(length(posA - camPos), 0.001f);
        float pixelSize = depth * gPixelSize1;
        float targetCellSize = pixelSize * sqrt(float(gForceDescendFootprintPx));
        float t = log(max(targetCellSize, 1e-6f) / max(gPosACoarse, 1e-6f)) / lookupLogRatio;
        int targetLvl = int(round(t * float(gNumLevels - 1u)));
        // Lookup window: [targetLvl, targetLvl + kWindowFwd].
        // No back-window — never read coarser-than-target cells.
        startLvl = clamp(targetLvl,                          0, int(gNumLevels) - 1);
        endLvl   = clamp(targetLvl + kWindowFwd + 1,         1, int(gNumLevels));
    }

    for (int lvl = startLvl; lvl < endLvl; lvl++)
    {
        float cs = vhfPosASize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb, normalA);

        // Always record the queried cell coords/level into best.qa/qb/level
        // even if no entry exists yet — diag visualization uses these to
        // show the cell SIZE that was queried (not lvl 0 fallback). The
        // best.valid flag remains false until a mature entry is found, so
        // the trust path is unaffected.
        if (!best.valid) {
            best.qa    = qa;
            best.qb    = qb;
            best.level = lvl;
        }

        uint fp   = vhfFingerprint(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint lvlProbe;
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/false, lvlProbe);
        best.probeSteps += lvlProbe;

        if (slot < 0) break;  // No entry at this level — stop cascade

        VHFEntry e  = gVHFTable[slot];
        uint total  = e.packed & 0xFFFFu;
        if (total == 0u) break;

        uint  vis = e.packed >> 16u;
        // Agresti-Coull shrinkage on cached μ: μ̃ = (X + z²/2)/(N + z²).
        // Default gMuShrinkZSquared = 0 → raw μ = X/N (legacy). When >0,
        // pulls extreme values away from 0/1 at low N (Beta-prior shrinkage).
        // var = μ̃(1−μ̃) propagates to all downstream gates and CV+RRR.
        float mu;
        if (gMuShrinkZSquared > 0.f)
        {
            float zsq = gMuShrinkZSquared;
            mu = (float(vis) + 0.5f * zsq) / (float(total) + zsq);
        }
        else
        {
            mu = float(vis) / float(total);
        }
        float var = mu * (1.0f - mu);  // Bernoulli variance (using shrunk μ when active)

        // Per-level bootThreshold — linear interp from gBootThreshold (coarse,
        // level 0) to gBootThresholdFine (fine, level numLevels-1). When
        // gBootThresholdFine == 0, all levels use gBootThreshold (legacy).
        // Enables "coarse HIGH, fine LOW" configurations where the coarse
        // level demands more samples before trust (defends against spurious
        // low-variance at penumbra-straddling cells) while finer levels can
        // trust faster (they see less data per cell but their variance
        // estimate reflects genuine uniformity).
        uint ctLvl = gBootThreshold;
        if (gBootThresholdFine != 0u && gNumLevels > 1u)
        {
            float t = float(lvl) / float(gNumLevels - 1u);
            ctLvl = uint(lerp(float(gBootThreshold), float(gBootThresholdFine), t));
        }

        // Footprint-aware trust: gBootThresholdFactorFootprintPx * log2(cellPixels) gives a
        // conservative spatial diversity requirement that scales with cell
        // size. Examples at scale=1: cellPx=4→2, 64→6, 1024→10, 6889→13.
        // scale=0 collapses the floor to 0 → max(ctLvl,0) = ctLvl
        // (old fpOff behaviour). scale=1 matches the prior fpOn formula.
        // Larger scales put more pressure on big cells.
        uint cellPx = vhfCellPixels(lvl, posA);
        uint diversityReq = uint(gBootThresholdFactorFootprintPx * log2(max(float(cellPx), 1.f)));
        uint footprintReq = max(ctLvl, diversityReq);
        uint required = uint(float(footprintReq) * (1.f + var * 4.f));

        // Too sparse: don't trust this level, and finer levels will be sparser
        // still — break and keep `best` from the last mature level (if any).
        if (total < required) break;

        // Mature: record and keep `best` at this level. Only overwrite on
        // mature hits so we never pair a coarse valid mu with a finer
        // immature one.
        best.mu    = mu;
        best.var   = var;
        best.level = lvl;
        best.N     = total;
        best.qa    = qa;
        best.qb    = qb;
        best.valid = true;

        // Determine "converged" via whichever gate is active:
        //   Wilson gate (preferred when gWilsonZSquared > 0): trust if the
        //     Bernoulli (1−ε) Wilson confidence interval lies entirely above
        //     1−ε or entirely below ε. Absorbs the SPP-dependent vt finding —
        //     small N gives a wide interval that refuses trust regardless of
        //     the point estimate, large N gives a narrow interval that trusts
        //     whichever side μ̂ lands on. See .plans/wilson-interval-prototype.md.
        //   stderr gate: sqrt(var/N) ≤ gStderrThreshold. Principled Bernoulli
        //     standard-error criterion — combines "low variance" and "enough
        //     samples" into one. Rejects few-sample cells with spurious low
        //     var (the x16-correlation pathology).
        //   varThreshold (legacy): var ≤ gVarThreshold, ignores N.
        bool converged;
        if (gWilsonZSquared > 0.f)
        {
            float Nf   = max(float(total), 1.f);
            float zsq  = gWilsonZSquared;
            float p    = mu;
            float invD = 1.f / (1.f + zsq / Nf);
            float numCenter = p + zsq / (2.f * Nf);
            float radical = sqrt(zsq * (p * (1.f - p) / Nf + zsq / (4.f * Nf * Nf)));
            float LB = (numCenter - radical) * invD;
            float UB = (numCenter + radical) * invD;
            float eps = gWilsonEps;
            converged = (LB > 1.f - eps) || (UB < eps);
        }
        else if (gStderrThreshold > 0.f)
        {
            float invN   = 1.f / max(float(total), 1.f);
            float stderr2 = var * invN;
            converged = stderr2 <= gStderrThreshold * gStderrThreshold;
        }
        else
        {
            converged = var <= gVarThreshold;
        }

        if (converged)
        {
            // fd already enforced via entry-level selection above; no in-loop
            // fd branch needed. Hierarchical consistency: peek the next finer
            // level; if its μ disagrees with this one, the current convergence
            // is suspect (likely a penumbra boundary where coarse/fine
            // differ). Keep descending to the refined estimate. Costs one
            // extra hash probe per converged level.
            if (gEnableHierarchicalConsistency != 0u && lvl + 1 < endLvl)
            {
                int nextLvl = lvl + 1;
                float nextCs  = vhfPosASize(nextLvl);
                int3  nqa, nqb;
                vhfQuantizePair(posA, posB, nextCs, uint(nextLvl), nqa, nqb, normalA);
                uint nfp   = vhfFingerprint(nqa, nqb, uint(nextLvl), uint(nextLvl), uint(nextLvl));
                uint naddr = vhfAddr(nqa, nqb, uint(nextLvl), uint(nextLvl), uint(nextLvl));
                uint nProbe;
                int  nslot = vhfFindSlot(naddr, nfp, /*allowInsert=*/false, nProbe);
                if (nslot >= 0)
                {
                    VHFEntry ne = gVHFTable[nslot];
                    uint ntot = ne.packed & 0xFFFFu;
                    if (ntot > 0u)
                    {
                        float nmu = float(ne.packed >> 16u) / float(ntot);
                        if (abs(nmu - mu) > gHierarchicalMuTolerance)
                        {
                            // Disagreement — don't trust this level, keep descending.
                            continue;
                        }
                    }
                }
                // No next entry or agreement — accept convergence.
                break;
            }
            else
            {
                break;
            }
        }
        // Else: high variance (penumbra) — descend to refine.
    }

    return best;
}

// ---------------------------------------------------------------------------
// vhfLookupRaw: diagnostic variant that returns entry data even below
// bootThreshold. Returns the finest level that has ANY samples (total > 0).
// Used by vcWriteDiag to show mu/level for immature entries.
// ---------------------------------------------------------------------------
VHFResult vhfLookupRaw(float3 posA, float3 posB, float3 normalA = float3(0.f))
{
    VHFResult best;
    best.mu    = 0.5f;
    best.var   = 0.125f; // Half of max Bernoulli variance (0.25/2)
    best.level = -1;
    best.N     = 0u;
    best.valid = false;

    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfPosASize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb, normalA);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint _ps;
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/false, _ps);

        if (slot < 0) break;

        VHFEntry e  = gVHFTable[slot];
        uint total  = e.packed & 0xFFFFu;
        if (total == 0u) break;

        uint  vis = e.packed >> 16u;
        float mu  = float(vis) / float(total);
        float var = mu * (1.0f - mu);

        best.mu    = mu;
        best.var   = var;
        best.level = lvl;
        best.N     = total;
        best.valid = (total >= gBootThreshold);
    }

    return best;
}

// ===========================================================================
// TWO-PHASE GATE/COMMIT API — CORE CV+RRR ESTIMATOR
// ===========================================================================

// ---------------------------------------------------------------------------
// The gate/commit pattern separates the "should I trace?" decision from
// the actual trace, allowing the caller to use any tracing method.
//
// Phase 1 (vhfGate / vhfGateDeterministic):
//   - Looks up the cache
//   - Computes RR probability p from variance and contribution luminance
//   - Returns shouldTrace (coin flip: xi < p) and cached mu
//
// Phase 2 (vhfCommit):
//   - Inserts the trace result into the cache
//   - Computes the unbiased CV+RRR weight: mu + (V - mu) / p
//
// The CV+RRR weight has the property:
//   E[mu + (V - mu) / p] = mu + E[V - mu] / 1 = mu + (E[V] - mu) = E[V]
//   (since E[1/p * indicator(xi < p)] = 1)
//
// This means the estimator is UNBIASED regardless of mu's accuracy.
// However, mu's accuracy determines the VARIANCE: when mu ≈ V, the
// residual (V - mu) is small, so the 1/p amplification doesn't cause
// large variance spikes. This is why the cache improves quality even
// before fully converging.
//
// Usage pattern (any pass):
//   VHFGateResult g = vhfGateDeterministic(posA, posB, contribLum);
//   if (g.shouldTrace) {
//       float V = <trace shadow ray>;
//       float visWeight = vhfCommit(posA, posB, V, g);
//       // visWeight is the unbiased CV+RRR estimate of visibility
//   } else {
//       float visWeight = g.visWeight;  // = cached mu, no ray needed
//   }
// ---------------------------------------------------------------------------
struct VHFGateResult
{
    bool  shouldTrace;  ///< true = caller must trace and call vhfCommit
    float visWeight;    ///< When !shouldTrace: unbiased estimate = cached mu
    float mu;           ///< Cached visibility mean (passed through to vhfCommit)
    float invP;         ///< 1/p (passed through to vhfCommit for CV+RRR weight)
    float var;          ///< Cached variance mu*(1-mu) (diagnostics)
    int   level;        ///< LOD level QUERIED (always set; valid_data flags whether
                        ///< an actual entry was found at that level for trust).
    bool  valid_data;   ///< true = mature entry found at level (trust path);
                        ///< false = no entry / sparse cell (level still set to
                        ///< the queried level for diag visualization).
    uint  N;            ///< Total sample count at matched level (diagnostics)
    uint  probeSteps;   ///< Hash probe steps (diagnostics — collision pressure)
    int3  qa;           ///< Quantized posA cell coords (diagnostics — hash grid vis)
    int3  qb;           ///< Quantized posB cell coords (diagnostics — hash grid vis)
};

/// Phase 1: lookup + RR decision.
///
/// xi: uniform random in [0,1) for the RR coin flip. Use vhfDeterministicXi()
///   for temporal stability, or sampleNext1D(sg) for stochastic paths.
///
/// contribLuminance: luminance of the path contribution through this edge.
///   When > 0, enables firefly-aware adaptive pMin: high-contribution paths
///   get higher p (more likely to trace) to prevent weight explosion.
///   Pass 0 to disable adaptive pMin and use the flat gPMin floor.
VHFGateResult vhfGate(float3 posA, float3 posB,
                       float xi, float contribLuminance = 0.f,
                       float3 normalA = float3(0.f),
                       bool forceWarmup = false)
{
    VHFGateResult g;
    VHFResult r = vhfLookup(posA, posB, normalA);

    // Copy qa/qb from the cascade-selected level (diagnostics — hash grid vis).
    g.qa = r.qa;
    g.qb = r.qb;

    // Warmup: force trace + cache write, no RR. When forceWarmup is true
    // (caller determined pixel is in write-only Bayer slot this frame),
    // skip the RR read entirely. See vhfBayerWarmup().
    if (forceWarmup)
    {
        g.shouldTrace = true;
        g.visWeight   = 0.f;
        g.mu          = r.mu;
        g.invP        = 1.f;
        g.var         = r.var;
        g.level       = r.level;
        g.valid_data  = r.valid;
        g.N           = r.N;
        g.probeSteps  = r.probeSteps;
        return g;
    }

    // No mature entry: must trace unconditionally.
    // invP = 1 means the commit weight is just V (no correction needed).
    // Pass through immature data (mu, level, N) if any entry exists — the
    // diagnostic uses these even though the RR decision doesn't trust them.
    if (!r.valid)
    {
        g.shouldTrace = true;
        g.visWeight   = 0.f;
        g.mu          = r.mu;     // immature mu if entry exists, 0.5 if no entry
        g.invP        = 1.f;
        g.var         = r.var;    // immature var if entry exists, 0.125 if no entry
        g.level       = r.level;  // queried level (always set, even if no entry)
        g.valid_data  = false;
        g.N           = r.N;      // 0 if no entry, else immature sample count
        g.probeSteps  = r.probeSteps;
        return g;
    }

    // Compute RR probability p from two factors:
    //
    // 1. Variance-based: p = var / varThreshold. High-variance entries
    //    (penumbrae) get p ≈ 1 (almost always trace). Low-variance entries
    //    (fully lit/shadowed) get low p (mostly skip).
    //
    // 2. Confidence-adaptive pMin: high-N + low-var cells get lower pMin floor.
    //    log2 N-dependence limits max reduction to ~12x at counter saturation.
    //    High-variance cells (penumbra) get no reduction regardless of N.
    float pMinEff = gPMin;
    if (gFlags & kFlag_EnableAdaptivePMin)
    {
        float nRatio    = float(r.N) / float(max(gBootThreshold, 1u));
        float nFactor   = log2(max(nRatio, 1.f)) + 1.f;
        float varFactor = 1.f - saturate(r.var / gVarThreshold);
        float confidence = nFactor * varFactor;
        pMinEff = gPMin / max(confidence, 1.f);
    }

    // 3. Firefly-aware floor: if the path contribution is high, raise pMin
    //    so the 1/p amplification doesn't create fireflies. The budget
    //    parameter controls how aggressively this kicks in.
    float pFloor = pMinEff;
    if (contribLuminance > 0.f)
    {
        float contrib = contribLuminance * max(r.mu, 1.f - r.mu);
        pFloor = clamp(contrib / gFireflyBudget, pMinEff, 1.f);
    }
    // Final RR probability clamped to [0.01, 1]. Lower bound prevents runaway
    // invP when variance is near zero; upper bound accommodates pMin>=1 (force
    // trace) — callers passing pMin=2 collapse to p=1 cleanly.
    float p = clamp(r.var / gVarThreshold, max(pFloor, 0.01f), 1.f);

    // Pass through diagnostic fields from the lookup result.
    g.var         = r.var;
    g.level       = r.level;
    g.valid_data  = r.valid;
    g.N           = r.N;
    g.probeSteps  = r.probeSteps;

    // RR coin flip: trace if xi < p, skip otherwise.
    if (xi < p)
    {
        g.shouldTrace = true;
        g.visWeight   = 0.f;
        g.mu          = r.mu;
        g.invP        = 1.f / p;  // Needed by vhfCommit for CV+RRR weight
    }
    else
    {
        g.shouldTrace = false;
        g.visWeight   = r.mu;     // No trace — use cached mean as estimate
        g.mu          = r.mu;
        g.invP        = 0.f;      // Not used when !shouldTrace
    }
    return g;
}

// ---------------------------------------------------------------------------
// Deterministic xi: derive the RR coin flip from the quantized cell
// coordinates instead of from a random sequence.
//
// Why deterministic: in ReSTIR path tracing, the same reconnection edge
// is evaluated multiple times (temporal reuse, spatial reuse, MIS weight
// computation). If each evaluation uses a different random xi, the same
// edge might be traced in one evaluation and skipped in another, causing
// inconsistent MIS weights and visible temporal flicker.
//
// By deriving xi from the quantized (posA, posB) cell pair at the finest
// level, the same physical edge always gets the same coin flip. This
// eliminates flicker and ensures MIS weight consistency.
//
// The finest level is used because it has the highest spatial resolution,
// giving the most spatially varying xi pattern (avoiding large blocks of
// pixels all getting the same decision).
//
// Note: if gNumLevels changes at runtime (via UI), the xi mapping changes,
// causing a one-frame discontinuity. This is acceptable for interactive
// tuning but gNumLevels should be stable during production rendering.
// ---------------------------------------------------------------------------
float vhfDeterministicXi(float3 posA, float3 posB)
{
    int hiLvl = int(gNumLevels) - 1;
    float cs = vhfPosASize(hiLvl);
    int3 qa, qb;
    vhfQuantizePair(posA, posB, cs, uint(hiLvl), qa, qb);
    // Different hash constants (0xCC, 0x13371337) ensure independence from
    // the address and fingerprint hashes.
    uint3 h = pcg3d(uint3(
        (uint(qa.x) ^ uint(qb.x)) + 0xCCu,
        (uint(qa.y) ^ uint(qb.y)) + 0xCCu,
        (uint(qa.z) ^ uint(qb.z)) + uint(hiLvl) * 0x13371337u
    ));
    // Shift right by 1 to stay within float32 exact integer range (2^31-1),
    // then divide by 0x7FFFFFFF for [0, 1) mapping.
    return float(h.x >> 1u) / float(0x7FFFFFFFu);
}

/// Phase 1 with deterministic xi — no external random number needed.
/// Preferred for shift mapping and MIS weight computation where temporal
/// stability and reproducibility are required.
VHFGateResult vhfGateDeterministic(float3 posA, float3 posB,
                                    float contribLuminance = 0.f,
                                    bool forceWarmup = false,
                                    float3 normalA = float3(0.f))
{
    float xi = vhfDeterministicXi(posA, posB);
    return vhfGate(posA, posB, xi, contribLuminance, normalA, forceWarmup);
}

// ===========================================================================
// INSERT — COARSE-TO-FINE CASCADE WITH TWO GATES
// ===========================================================================

// ---------------------------------------------------------------------------
// Maturity gate: "mature" means the standard error of the mean is small
// enough that additional writes have diminishing returns.
//
// The standard error of a Bernoulli mean is:
//   SE = sqrt(mu * (1 - mu) / n)
//
// We define "mature" as SE <= SE_threshold, where:
//   SE_threshold^2 = gVarThreshold / gMatureThreshold
//
// Rearranging:
//   n >= mu * (1 - mu) * gMatureThreshold / gVarThreshold
//
// Examples (matureThreshold=128, varThreshold=0.1):
//   mu=1.0  → var=0.00, required=0     → mature immediately (fully lit)
//   mu=0.95 → var=0.05, required=64    → mature quickly (mostly lit)
//   mu=0.50 → var=0.25, required=320   → needs many samples (penumbra)
//   mu=0.70 → var=0.21, required=269   → intermediate
//
// The maturity gate reduces atomic contention on well-converged entries.
// Without it, every shadow ray trace would contend on the same slots,
// especially at coarse levels where many pixels share a cell.
//
// Decay periodically halves counts, temporarily un-maturing entries so
// they receive fresh samples. This revalidates the cache for animated
// scenes without explicit invalidation.
// ---------------------------------------------------------------------------
bool vhfIsMature(uint addr, uint fp)
{
    uint _ps;
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false, _ps);
    if (slot < 0) return false;  // No entry — definitely not mature

    // Single atomic read — avoids double-fetch race with concurrent writers.
    // Reading packed twice (once in vhfFindSlot, once here) could see
    // inconsistent values if another thread writes between the reads.
    uint packed = gVHFTable[slot].packed;
    uint total  = packed & 0xFFFFu;

    // Hard floor: never mature before bootThreshold, regardless of variance.
    if (total < gBootThreshold) return false;

    // Variance-scaled maturity: penumbrae need more samples than lit/shadowed.
    uint  vis = packed >> 16u;
    float mu  = float(vis) / float(total);
    float var = mu * (1.0f - mu);

    // Guard against gVarThreshold == 0 (would cause division by zero).
    if (gVarThreshold <= 0.f) return total >= gMatureThreshold;

    float required = var * float(gMatureThreshold) / gVarThreshold;
    return float(total) >= required;
}

// ---------------------------------------------------------------------------
// Inline overflow / MLE-α-floor decay.
//
// Two regimes share one mechanism:
//   1. Default (gMLAlphaFloorN == 0): trigger at ~57K samples, prevents
//      16-bit counter wrap-around. Effective forgetting window is so long
//      it's effectively a pure MLE running mean.
//   2. MLE α-floor (gMLAlphaFloorN > 0): trigger lowered to N* (typ 256-1024).
//      Once total ≥ N*, the 1/8 decay fires per insert, holding total in
//      [7N*/8, N*]. Steady-state per-sample weight ≈ 1/N* — the discrete
//      analogue of MCPG 2025's α = max(1/N, MIN_ALPHA) with MIN_ALPHA = 1/N*.
//
// 1/8 decay (kDecayShift=3) is race-tolerant under concurrent writers:
// each thread subtracts ⌊cur/8⌋ which converges to zero without underflow.
// A stronger decay (e.g. halving) would risk total→0 under contention.
// ---------------------------------------------------------------------------
uint vhfOverflowDecay(int slot, uint cur)
{
    uint trigger = (gMLAlphaFloorN > 0u) ? gMLAlphaFloorN : kOverflowTrigger;
    if ((cur & 0xFFFFu) > trigger)
    {
        uint visDecay   = (cur >> 16u) >> kDecayShift;
        uint totalDecay = (cur & 0xFFFFu) >> kDecayShift;
        uint sub        = (visDecay << 16u) | totalDecay;
        uint prev;
        InterlockedAdd(gVHFTable[slot].packed, -sub, prev);
        cur = prev - sub;  // Use atomic return value, not stale pre-decay cur
    }
    return cur;
}

// ---------------------------------------------------------------------------
// vhfInsert: write a visibility sample into the cache at all levels.
//
// Two gates control which levels receive the sample:
//
// 1. Maturity gate (before write): if this level already has enough samples
//    for its current variance, skip it. This reduces atomic contention on
//    well-converged entries and lets newer entries accumulate faster.
//
// 2. Cascaded variance gate (after write): if this level is now smooth
//    (low variance), stop descending to finer levels. Finer levels would
//    produce the same estimate, so writing to them wastes table capacity.
//
// The combination of these gates means: coarse levels mature first (they
// see more samples), and once mature, samples flow to finer levels only
// in penumbra regions where the variance is still high.
//
// Fingerprint CAS: when claiming an empty slot, we use
// InterlockedCompareExchange to atomically set the fingerprint. If another
// thread already claimed the slot with a different fingerprint (race),
// we skip the write to avoid corrupting that entry's statistics.
// ---------------------------------------------------------------------------
void vhfInsert(float3 posA, float3 posB, float V, float3 normalA = float3(0.f))
{
    uint visVal = (V > 0.5f) ? 1u : 0u;  // Binarize: 1 = visible, 0 = occluded

    bool enableBootstrap = (gFlags & kFlag_EnableBootstrapBreak) != 0u;
    bool enablePreinit   = (gFlags & kFlag_EnableParentPreinit) != 0u;

    // Parent state propagated from the last level we actually wrote to.
    // Used by parent-preinit (paper §5): when a finer level first claims an
    // empty slot, seed it with 1/8 of the parent's counts so the child has
    // a reasonable μ from frame one. Reset across mature-skip because we
    // don't read the mature entry here (acceptable — post-warmup, children
    // usually already exist and preinit wouldn't fire anyway).
    uint parentVis   = 0u;
    uint parentTotal = 0u;

    // Same analytical entry-level as vhfLookup (target minus 2 cascade
    // strides) so writes populate coarse-neighbor levels, enabling lookup
    // early-stop at coarse when μ converges there. Per-pixel, depth-dep.
    float insertLogRatio = log(max(gPosAFine, 1e-6f) / max(gPosACoarse, 1e-6f));

    // Insert visits the same [target-A, target+B] window as lookup so writes
    // populate exactly the levels that lookup will later read. No stride.
    static const int kCascadeWindowBack    = 4;
    static const int kCascadeWindowForward = 12;
    int startLvl = 0;
    int endLvl   = int(gNumLevels);
    if (gForceDescendFootprintPx != 0u && gNumLevels > 1u && insertLogRatio < -1e-6f)
    {
        float3 camPos = float3(gCameraPosX, gCameraPosY, gCameraPosZ);
        float depth = max(length(posA - camPos), 0.001f);
        float pixelSize = depth * gPixelSize1;
        float targetCellSize = pixelSize * sqrt(float(gForceDescendFootprintPx));
        float t = log(max(targetCellSize, 1e-6f) / max(gPosACoarse, 1e-6f)) / insertLogRatio;
        int targetLvl = int(round(t * float(gNumLevels - 1u)));
        startLvl = clamp(targetLvl - kCascadeWindowBack,    0, int(gNumLevels) - 1);
        endLvl   = clamp(targetLvl + kCascadeWindowForward + 1, 1, int(gNumLevels));
    }

    // Cap insert iterations to a small neighborhood around the analytical
    // entry level. Without a cap the loop would continue past N-startLvl
    // mature levels doing wasted hash probes on cells that are either
    // already converged (continue) or in empty space below the data's
    // actual depth. Lookup naturally breaks on cold levels; insert uses
    // Bounded by the analytical entry window already (endLvl is set above).
    // `continue` is used inside; the explicit upper bound prevents wasted
    // probes on cells far below the cascade target.

    for (int lvl = startLvl; lvl < endLvl; lvl++)
    {
        float cs = vhfPosASize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb, normalA);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl), uint(lvl), uint(lvl));

        // Gate 1: maturity — skip entries with enough samples.
        // Decay periodically un-matures entries for revalidation.
        // Never skip the finest level — always keep it populated for
        // maximum spatial resolution at shadow boundaries.
        bool isFinestLevel = (lvl + 1 >= endLvl);
        if (!isFinestLevel && vhfIsMature(addr, fp))
        {
            // Mature parent — cascade continues but preinit chain resets
            // because we didn't fetch the parent's packed here.
            parentVis   = 0u;
            parentTotal = 0u;
            continue;
        }

        // fd already enforced via startLvl above — no in-loop fd check.

        uint _ps;
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/true, _ps);
        if (slot < 0) continue;  // Table full at this probe depth

        // Atomic CAS: only write fingerprint if slot is still empty (fp==0).
        // Three outcomes:
        //   origFp == 0:  we won the race, slot is now ours
        //   origFp == fp: same cell pair, another thread got here first — OK
        //   origFp != fp: different cell pair claimed this slot — evict
        uint origFp;
        InterlockedCompareExchange(gVHFTable[slot].fingerprint, 0u, fp, origFp);
        bool claimedEmpty = (origFp == 0u);
        if (origFp != 0u && origFp != fp)
        {
            // Evict: overwrite fingerprint and zero packed data.
            // vhfFindSlot verified this entry had too few samples to keep
            // (pressure-scaled eviction at probe depth >= kEvictStartStep).
            uint dummy;
            InterlockedExchange(gVHFTable[slot].fingerprint, fp, dummy);
            InterlockedExchange(gVHFTable[slot].packed, 0u, dummy);
            claimedEmpty = true;  // fresh slot — preinit applies
        }

        // Parent-preinit (paper §5): seed a freshly-claimed child slot with
        // parent's μ at reduced weight. Gives the child a useful starting
        // estimate on its first sample rather than starting from zero.
        // Race class identical to the evict path above (a concurrent thread
        // could InterlockedAdd between our CAS and the Exchange below; same
        // collision rate as the existing ABA race, negligible with warp
        // reduction per paper §5).
        if (claimedEmpty && enablePreinit && parentTotal > 0u)
        {
            uint seedVis   = parentVis   >> 3;
            uint seedTotal = parentTotal >> 3;
            if (seedTotal > 0u)
            {
                uint seedPacked = (seedVis << 16u) | seedTotal;
                uint dummy;
                InterlockedExchange(gVHFTable[slot].packed, seedPacked, dummy);
            }
        }

        // Accelerated decay (optional): if the incoming sample disagrees
        // strongly with the cell's current μ, halve the counters before
        // adding. Outlier evidence gets amplified weight — stale / wrong
        // cell means decay faster toward the new evidence. Skip on fresh
        // slots (no prior data). Race-tolerant: multiple threads half-
        // decaying converges to zero without underflow because (packed & 0xFFFF)
        // shifts by 1 each half-decay, not arithmetic subtract of a const.
        if (gAccelDecayDisagreeThresh > 0.f && !claimedEmpty)
        {
            uint curPacked = gVHFTable[slot].packed;
            uint curTotal  = curPacked & 0xFFFFu;
            if (curTotal >= 2u)
            {
                float curMu = float(curPacked >> 16u) / float(curTotal);
                if (abs(float(visVal) - curMu) > gAccelDecayDisagreeThresh)
                {
                    uint subVis   = (curPacked >> 16u) >> 1;
                    uint subTotal = curTotal          >> 1;
                    uint sub      = (subVis << 16u) | subTotal;
                    uint dummy;
                    InterlockedAdd(gVHFTable[slot].packed, 0u - sub, dummy);
                }
            }
        }

        // Atomically increment both vis_count (if visible) and total_count.
        // The packed format [vis:16|total:16] allows a single InterlockedAdd.
        uint delta = (visVal << 16u) | 1u;
        uint prev;
        InterlockedAdd(gVHFTable[slot].packed, delta, prev);

        // Inline overflow decay: prevent 16-bit counter wrap-around.
        uint cur = vhfOverflowDecay(slot, prev + delta);
        uint totalCur = cur & 0xFFFFu;
        uint visCur   = cur >> 16u;

        // Track parent state for next iteration's preinit.
        parentVis   = visCur;
        parentTotal = totalCur;

        // Gate 2a: Bootstrap break (paper §5) — if this level is still too
        // sparse to guide children, stop. Writing to finer (sparser) levels
        // now would just scatter noise that can't converge before its parent.
        if (enableBootstrap && totalCur < gBootThreshold) break;

        // Gate 2b: cascaded variance gate — if this level is now smooth,
        // stop descending. Finer levels in a converged region would produce
        // the same mu, so writing to them wastes table capacity.
        if (totalCur >= gMatureThreshold)
        {
            float muCur  = float(visCur) / float(totalCur);
            float varCur = muCur * (1.0f - muCur);
            if (varCur <= gVarThreshold)
                break;  // Converged — no need to write finer levels
        }
    }
}

// ---------------------------------------------------------------------------
// vhfCommit: Phase 2 of the gate/commit API.
//
// After the caller traces a shadow ray (getting V = 0 or 1), this function:
//   1. Inserts V into the cache at all levels (via vhfInsert)
//   2. Computes and returns the unbiased CV+RRR weight
//
// The CV+RRR weight formula:
//   w = mu + (V - mu) * invP
//
// where mu is the cached mean from Phase 1, V is the trace result, and
// invP = 1/p is the inverse RR probability. This weight satisfies:
//   E[w] = E[V]  (unbiased)
//   Var[w] ≈ 0 when mu ≈ V  (low variance when cache is accurate)
//
// The caller multiplies path contribution by w instead of V, getting the
// same expected value but with potentially much lower variance.
// ---------------------------------------------------------------------------
float vhfCommit(float3 posA, float3 posB, float V, VHFGateResult g,
                float3 normalA = float3(0.f))
{
    vhfInsert(posA, posB, V, normalA);
    // When invP == 1 (always-trace: pMin>=1, or immature-entry fallback, or
    // variance at ceiling) the CV+RRR formula algebraically collapses to V.
    // Short-circuit to avoid `mu + (V - mu) * 1` float drift that leaves tiny
    // per-pixel residuals even when nothing needs estimation. Makes the
    // always-trace mode bitwise-equal to vanilla.
    if (g.invP == 1.f) return V;
    return g.mu + (V - g.mu) * g.invP;
}

#endif // USE_VISCACHE

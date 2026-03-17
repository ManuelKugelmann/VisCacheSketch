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
 *     spaced between gCellCoarse and gCellFine. Geometric (not linear)
 *     spacing gives each level roughly the same number of populated cells.
 *
 *   JITTER-BEFORE-QUANTIZE: Adding position-dependent jitter before
 *     floor() eliminates systematic aliasing at cell boundaries [Binder
 *     et al. 2018]. The jitter is derived from the cell index itself (not
 *     frame number), so the same position always maps to the same cell.
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
    bool  valid;    ///< false = cold miss — no mature entry found, always trace
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
//   gBootThreshold:  Minimum total_count before an entry is trusted. Lower
//     values (16) give faster warmup but noisier early estimates. Higher
//     values (64) are more conservative — good when RR decisions are costly.
//     Must be >= 1 and <= 0xFFFF (16-bit counter width).
//
//   gVarThreshold:  Variance gate for both the cascaded LOD stop (lookup)
//     and the maturity gate (insert). 0.10 means: stop refining when
//     mu*(1-mu) < 0.10. Lower values (0.01) activate more levels, giving
//     higher quality at shadow penumbrae but tracing more rays. Higher
//     values save more rays but may miss penumbra detail.
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
//   gCellCoarse / gCellFine:  World-space cell sizes for the coarsest and
//     finest levels. Intermediate levels are geometrically interpolated.
//     Auto-derived from scene bounds when autoTuneCells is enabled.
// ---------------------------------------------------------------------------
cbuffer VisCacheParams
{
    uint   gTableCapacity;   ///< Power-of-two entry count
    uint   gBootThreshold;   ///< Min total_count before entry is trusted
    float  gVarThreshold;    ///< Variance below which we stop refining LOD
    float  gPMin;            ///< Minimum RR survival probability
    float  gFireflyBudget;   ///< Contribution scale for adaptive pMin
    uint   gNumLevels;       ///< Number of LOD levels (runtime, arbitrary N)
    float  gCellCoarse;      ///< Coarsest level cell size (world units)
    float  gCellFine;        ///< Finest level cell size (world units)
};

// ---------------------------------------------------------------------------
// vhfCellSize: geometric interpolation from coarsest to finest cell size.
//
// t = 0 → gCellCoarse (coarsest level)
// t = 1 → gCellFine   (finest level)
// Intermediate levels are geometrically spaced: each level's cell size is
// the geometric mean of its neighbors. This gives roughly equal spatial
// coverage per level.
//
// When numLevels == 1, t = 0 → returns gCellCoarse (the single level).
// ---------------------------------------------------------------------------
float vhfCellSize(int lvl)
{
    float t = (gNumLevels <= 1u) ? 0.f : float(lvl) / float(gNumLevels - 1u);
    return gCellCoarse * exp(t * log(gCellFine / gCellCoarse));
}

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

// ===========================================================================
// IBL DIRECTION ENCODING
// ===========================================================================

// ---------------------------------------------------------------------------
// Environment map and directional lights have no finite endpoint B. We encode
// the direction as a "position at infinity" by scaling the unit direction
// vector by a marker magnitude derived from gCellCoarse.
//
// The marker is chosen so that quantizing (dir * marker) at the coarsest
// cell size produces angular bins of roughly kIBLAngularCell radians (~45°,
// i.e. octants). This is coarse but meaningful: "is this octant of
// directions occluded from this spatial region?" Finer LOD levels refine
// the angular resolution proportionally via the geometric cascade.
//
// Why octants (45°) rather than finer bins:
//   - Coarser bins accumulate samples faster → quicker convergence
//   - Environment map visibility tends to be spatially smooth at large scales
//   - Finer levels (if needed) automatically refine the angular resolution
//   - Very fine angular bins at the coarsest level would rarely see the same
//     cell pair twice, making the cache useless for IBL
//
// The marker magnitude is: gCellCoarse / kIBLAngularCell
//   → floor(dir * marker / cellCoarse) ≈ floor(dir / kIBLAngularCell)
// ---------------------------------------------------------------------------
static const float kIBLAngularCell = 0.785f;  ///< ~45 degrees in radians (octant-level bins)

/// Encode a normalized direction as a position for VisCache lookups.
/// Use this as posB when querying visibility toward an env map or
/// directional light (no finite endpoint).
///
/// Example:
///   float3 vcPosB = vhfEncodeDirection(ray.dir);
///   VHFGateResult g = vhfGateDeterministic(ray.origin, vcPosB, luminance(Lr));
float3 vhfEncodeDirection(float3 dir)
{
    float marker = gCellCoarse / kIBLAngularCell;
    return dir * marker;
}

// ===========================================================================
// SPATIAL QUANTIZATION
// ===========================================================================

// ---------------------------------------------------------------------------
// Jitter-before-quantize [Binder et al. 2018]:
//
// Naive floor(pos / cellSize) creates systematic aliasing at cell boundaries:
// two points epsilon apart can map to different cells. This causes visual
// banding in shadows.
//
// Solution: add position-dependent random jitter (±0.5 cells) before
// quantizing. The jitter is derived from the base cell index via pcg3d,
// so it's deterministic — the same world position always maps to the same
// cell, regardless of when or how often it's queried.
//
// The seed parameter allows different jitter for posA vs posB (using
// 0xAA vs 0xBB), preventing systematic correlation between endpoints.
// The level index is XORed into the seed so different LOD levels get
// independent jitter patterns.
// ---------------------------------------------------------------------------
int3 jitterQuantize(float3 pos, float cellSize, uint seed)
{
    int3 baseIdx = int3(floor(pos / cellSize));
    uint3 r = pcg3d(uint3(baseIdx) ^ seed);
    float3 jitter = float3(r & 0xFFFFu) / 65535.0f - 0.5f;
    return int3(floor((pos + jitter * cellSize) / cellSize));
}

// ---------------------------------------------------------------------------
// Canonical quantization: quantize both endpoints and lexicographic-swap
// so that V(A,B) and V(B,A) always produce the same (qa, qb) pair.
//
// This exploits the symmetry of visibility: if point A can see point B,
// then point B can see point A. Without canonicalization, the two orderings
// would hash to different slots, wasting half the table capacity and
// halving the sample accumulation rate.
// ---------------------------------------------------------------------------
void vhfQuantizePair(float3 posA, float3 posB, float cellSize, uint lvl,
                     out int3 qa, out int3 qb)
{
    qa = jitterQuantize(posA, cellSize, 0xAAu ^ lvl);
    qb = jitterQuantize(posB, cellSize, 0xBBu ^ lvl);
    // Lexicographic sort ensures V(A,B) == V(B,A) map to same entry.
    if (qa.x > qb.x || (qa.x == qb.x && (qa.y > qb.y || (qa.y == qb.y && qa.z > qb.z))))
    {
        int3 tmp = qa; qa = qb; qb = tmp;
    }
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
uint vhfAddr(int3 qa, int3 qb, uint lvl)
{
    uint3 h = pcg3d(uint3(
        uint(qa.x) ^ uint(qb.x),
        uint(qa.y) ^ uint(qb.y),
        (uint(qa.z) ^ uint(qb.z)) + lvl * 0x9e3779b9u
    ));
    return (h.x ^ h.y ^ h.z) & (gTableCapacity - 1u);
}

uint vhfFingerprint(int3 qa, int3 qb, uint lvl)
{
    uint3 h = pcg3d(uint3(
        (uint(qa.x) ^ uint(qb.x)) + 7u,
        (uint(qa.y) ^ uint(qb.y)) + 13u,
        (uint(qa.z) ^ uint(qb.z)) + lvl * 0xdeadbeefu
    ));
    return h.x ^ h.y ^ h.z;
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
int vhfFindSlot(uint addr0, uint fp, bool allowInsert)
{
    uint h2 = fp | 1u;  // Odd step → coprime with power-of-two table → full traversal
    for (uint i = 0u; i < kMaxProbe; i++)
    {
        uint slot = (addr0 + i * h2) & (gTableCapacity - 1u);
        uint efp  = gVHFTable[slot].fingerprint;

        // Exact match — this slot holds our cell pair's data.
        if (efp == fp)
            return int(slot);

        if (allowInsert)
        {
            // Empty slot — available for new entry.
            if (efp == 0u && gVHFTable[slot].packed == 0u)
                return int(slot);

            // Pressure-scaled eviction: deeper probe steps can evict
            // entries with few samples. This prevents probe chains from
            // growing unboundedly at high load factors.
            if (i >= kEvictStartStep)
            {
                uint total = gVHFTable[slot].packed & 0xFFFFu;
                uint threshold = kEvictBaseCount << (i - kEvictStartStep);
                if (total < threshold)
                    return int(slot);  // Evict this low-sample entry
            }
        }
    }
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
VHFResult vhfLookup(float3 posA, float3 posB)
{
    VHFResult best;
    best.mu    = 0.5f;   // Default: uncertain (max variance)
    best.var   = 1.0f;
    best.level = -1;
    best.valid = false;

    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/false);

        if (slot < 0) break;  // No entry at this level — stop cascade

        VHFEntry e  = gVHFTable[slot];
        uint total  = e.packed & 0xFFFFu;
        if (total < gBootThreshold || total == 0u) break;  // Not enough samples — stop

        uint  vis = e.packed >> 16u;
        float mu  = float(vis) / float(total);
        float var = mu * (1.0f - mu);  // Bernoulli variance

        // This level is mature — record as current best.
        best.mu    = mu;
        best.var   = var;
        best.level = lvl;
        best.valid = true;

        // Variance gate: if this level is converged (low variance),
        // finer levels would produce the same estimate. Stop early.
        if (var <= gVarThreshold) break;
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
                       float xi, float contribLuminance = 0.f)
{
    VHFGateResult g;
    VHFResult r = vhfLookup(posA, posB);

    // Cold miss: no mature entry at any level. Must trace unconditionally.
    // invP = 1 means the commit weight is just V (no correction needed).
    if (!r.valid)
    {
        g.shouldTrace = true;
        g.visWeight   = 0.f;
        g.mu          = 0.f;
        g.invP        = 1.f;
        return g;
    }

    // Compute RR probability p from two factors:
    //
    // 1. Variance-based: p = var / varThreshold. High-variance entries
    //    (penumbrae) get p ≈ 1 (almost always trace). Low-variance entries
    //    (fully lit/shadowed) get low p (mostly skip).
    //
    // 2. Firefly-aware floor: if the path contribution is high, raise pMin
    //    so the 1/p amplification doesn't create fireflies. The budget
    //    parameter controls how aggressively this kicks in.
    float pFloor = gPMin;
    if (contribLuminance > 0.f)
    {
        // Worst-case residual: contribution * max(mu, 1-mu). If the cache
        // is wrong, the error is at most this large.
        float contrib = contribLuminance * max(r.mu, 1.f - r.mu);
        pFloor = clamp(contrib / gFireflyBudget, gPMin, 1.f);
    }
    float p = clamp(r.var / gVarThreshold, pFloor, 1.f);

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
    float cs = vhfCellSize(hiLvl);
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
                                    float contribLuminance = 0.f)
{
    float xi = vhfDeterministicXi(posA, posB);
    return vhfGate(posA, posB, xi, contribLuminance);
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
//   SE_threshold^2 = gVarThreshold / gBootThreshold
//
// Rearranging:
//   n >= mu * (1 - mu) * gBootThreshold / gVarThreshold
//
// Examples (bootThreshold=32, varThreshold=0.1):
//   mu=1.0  → var=0.00, required=0    → mature immediately (fully lit)
//   mu=0.95 → var=0.05, required=16   → mature quickly (mostly lit)
//   mu=0.50 → var=0.25, required=80   → needs many samples (penumbra)
//   mu=0.70 → var=0.21, required=67   → intermediate
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
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false);
    if (slot < 0) return false;  // No entry — definitely not mature

    // Single atomic read — avoids double-fetch race with concurrent writers.
    // Reading packed twice (once in vhfFindSlot, once here) could see
    // inconsistent values if another thread writes between the reads.
    uint packed = gVHFTable[slot].packed;
    uint total  = packed & 0xFFFFu;
    if (total < 2u) return false;  // Too few samples to compute variance

    uint  vis = packed >> 16u;
    float mu  = float(vis) / float(total);
    float var = mu * (1.0f - mu);

    // Guard against gVarThreshold == 0 (would cause division by zero).
    // When varThreshold is zero, fall back to simple sample count check.
    if (gVarThreshold <= 0.f) return total >= gBootThreshold;

    float required = var * float(gBootThreshold) / gVarThreshold;
    return float(total) >= required;
}

// ---------------------------------------------------------------------------
// Inline overflow decay: prevents the 16-bit counters from wrapping around.
//
// When total exceeds kOverflowTrigger (~57K), subtract 1/8 of both counters.
// This preserves the mean (vis/total ratio) while freeing counter headroom.
//
// Why 1/8 (kDecayShift=3): aggressive enough to prevent overflow, gentle
// enough to not lose too much history. The entry effectively "forgets"
// its oldest samples, which also helps with temporal adaptation.
//
// The function takes cur (the post-InterlockedAdd value) and returns the
// post-decay value. Uses the InterlockedAdd return value to avoid stale
// data races with concurrent writers.
// ---------------------------------------------------------------------------
uint vhfOverflowDecay(int slot, uint cur)
{
    if ((cur & 0xFFFFu) > kOverflowTrigger)
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
void vhfInsert(float3 posA, float3 posB, float V)
{
    uint visVal = (V > 0.5f) ? 1u : 0u;  // Binarize: 1 = visible, 0 = occluded

    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));

        // Gate 1: maturity — skip entries with enough samples.
        // Decay periodically un-matures entries for revalidation.
        if (vhfIsMature(addr, fp)) continue;

        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/true);
        if (slot < 0) continue;  // Table full at this probe depth

        // Atomic CAS: only write fingerprint if slot is still empty (fp==0).
        // Three outcomes:
        //   origFp == 0:  we won the race, slot is now ours
        //   origFp == fp: same cell pair, another thread got here first — OK
        //   origFp != fp: different cell pair claimed this slot — skip
        uint origFp;
        InterlockedCompareExchange(gVHFTable[slot].fingerprint, 0u, fp, origFp);
        if (origFp != 0u && origFp != fp) continue;  // Slot claimed by different entry

        // Atomically increment both vis_count (if visible) and total_count.
        // The packed format [vis:16|total:16] allows a single InterlockedAdd.
        uint delta = (visVal << 16u) | 1u;
        uint prev;
        InterlockedAdd(gVHFTable[slot].packed, delta, prev);

        // Inline overflow decay: prevent 16-bit counter wrap-around.
        uint cur = vhfOverflowDecay(slot, prev + delta);

        // Gate 2: cascaded variance gate — if this level is now smooth,
        // stop descending. Finer levels in a converged region would produce
        // the same mu, so writing to them wastes table capacity.
        uint totalCur = cur & 0xFFFFu;
        if (totalCur >= gBootThreshold)
        {
            uint visCur  = cur >> 16u;
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
float vhfCommit(float3 posA, float3 posB, float V, VHFGateResult g)
{
    vhfInsert(posA, posB, V);
    return g.mu + (V - g.mu) * g.invP;
}

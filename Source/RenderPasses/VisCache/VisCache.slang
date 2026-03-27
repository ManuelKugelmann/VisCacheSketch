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

// When USE_VISCACHE=0, this module compiles to nothing — all types,
// resources, and functions are excluded. Consumer passes can import
// unconditionally without #if guards; the Slang compiler eliminates
// the empty module at compile time.
#if USE_VISCACHE

// Default jitter to ON — downstream passes set USE_VISCACHE_JITTER=0 for ablation F.
#ifndef USE_VISCACHE_JITTER
#define USE_VISCACHE_JITTER 1
#endif

// Addressing modes (compile-time, mutually exclusive):
//   Default (neither set):       Canonical pos x pos — same cell size for both endpoints, lexicographic swap.
//   USE_VISCACHE_DIRDIST_ADDRESSING=1:  Dir+dist — posB from direction+distance, per-dimension cascade.
//                                       gAngularBCoarse/Fine control angular quantization.
//                                       gDistBCoarse/Fine control distance quantization.
//   Neither set + cellBCoarse == cellACoarse: Canonical pos x pos with lexicographic swap.
//   Neither set + cellBCoarse != cellACoarse: Asymmetric pos x pos, no swap (auto-derived).
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
//   Per-dimension coarse/fine pairs (cellA, cellB, angularB, distB):
//     Coarse = coarsest level cell size, fine = finest (auto-derived).
//     Intermediate levels are geometrically interpolated.
// ---------------------------------------------------------------------------
cbuffer VisCacheParams
{
    uint   gTableCapacity;   ///< Power-of-two entry count
    uint   gBootThreshold;   ///< Min total_count before entry is trusted
    float  gVarThreshold;    ///< Variance below which we stop refining LOD
    float  gPMin;            ///< Minimum RR survival probability
    float  gFireflyBudget;   ///< Contribution scale for adaptive pMin
    uint   gNumLevels;       ///< Number of LOD levels (runtime, arbitrary N)
    uint   gFlags;           ///< Packed flags: bit 0 = jitterA, bit 1 = jitterB, bit 2 = adaptivePMin
    // --- Per-dimension LOD cascade (coarse → fine, geometric interpolation) ---
    float  gCellACoarse;     ///< posA coarsest cell size (world units, auto-tuned from scene)
    float  gCellAFine;       ///< posA finest cell size (auto-derived from coarse + numLevels)
    float  gCellBCoarse;     ///< posB coarsest cell size (world units, pos×pos modes)
    float  gCellBFine;       ///< posB finest cell size (auto-derived)
    float  gAngularBCoarse;  ///< direction coarsest cell size (degrees, dirdist mode)
    float  gAngularBFine;    ///< direction finest cell size (auto-derived)
    float  gDistBCoarse;     ///< distance coarsest cell size (world units, dirdist mode)
    float  gDistBFine;       ///< distance finest cell size (auto-derived)
    float  gNormalBCoarse;   ///< normal coarsest cell size (degrees, like angularBCoarse)
    float  gNormalBFine;     ///< normal finest cell size (auto-derived)
    uint   gDiagAccumWindow; ///< EMA window size for accumulated diagnostics (0 = all frames)
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

float vhfCellSizeA(int lvl)     { return vhfInterp(gCellACoarse,    gCellAFine,    lvl); }
float vhfCellSizeB(int lvl)     { return vhfInterp(gCellBCoarse,    gCellBFine,    lvl); }
float vhfAngularSize(int lvl)   { return vhfInterp(gAngularBCoarse, gAngularBFine, lvl); }
float vhfDistSize(int lvl)      { return vhfInterp(gDistBCoarse,    gDistBFine,    lvl); }

// Backward compat — used by jitter, deterministic xi, diagnostics
float vhfCellSize(int lvl)      { return vhfCellSizeA(lvl); }

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
/// Per-dimension hash functions. Used directly by diagnostics (salt=0)
/// and indirectly by pcgHash (salt=caller's differentiator).
uint pcgHashA(int3 qa, uint lvlA, uint salt = 0u) { return pcgHashEndpoint(qa, lvlA, kSaltA ^ salt); }
uint pcgHashB(int3 qb, uint lvlB, uint salt = 0u) { return pcgHashEndpoint(qb, lvlB, kSaltB ^ salt); }
uint pcgHashDist(uint lvlDist, uint salt = 0u) { return pcgHashEndpoint(int3(0), lvlDist, kSaltDist ^ salt); }

/// Combined hash: hashA ^ hashB ^ hashDist.
/// salt differentiates address from fingerprint (vhfAddr vs vhfFingerprint).
uint pcgHash(int3 qa, int3 qb, uint lvlA, uint lvlB, uint lvlDist, uint salt)
{
    return pcgHashA(qa, lvlA, salt) ^ pcgHashB(qb, lvlB, salt) ^ pcgHashDist(lvlDist, salt);
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

/// Quantize a direction into an int3 key: (dirBinX, dirBinY, distBin).
/// Grid-scaling convention: larger cell = coarser = fewer bins (matches spatial cells).
/// angularCellSize: cell size in octahedral [-1,1]² space.
///   >= 2.0 = single bin (position-only), 0.5 = ~16 bins, 0.1 = ~400 bins.
/// distCellSize: distance cell size in world units.
///   >= 100.0 = single distance bucket (effectively no distance discrimination).
int3 vhfQuantizeDirection(float3 dir, float angularCellSize, float dist, float distCellSize)
{
    // Octahedral coords shifted to [0,2] — always non-negative, round() safe.
    // Distance is also always >= 0.
    float2 oct = octEncode(dir) + 1.f;  // now in [0, 2]
    float angCell = max(angularCellSize, 0.01f);
    int2 dirBin = int2(round(oct / angCell));
    int distBin = int(round(dist / max(distCellSize, 0.01f)));
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
    float marker = gCellACoarse / kIBLAngularCell;
    return dir * marker;
}

// ===========================================================================
// SPATIAL QUANTIZATION
// ===========================================================================

// ---------------------------------------------------------------------------
// Jitter-before-quantize [Binder et al. 2018]:
//
// Naive round(pos / cellSize) creates systematic aliasing at cell boundaries:
// two points epsilon apart can map to different cells. This causes visual
// banding in shadows.
//
// Solution: add position-dependent random jitter (±0.5 cells) before
// quantizing. Two jitter modes:
//
//   Default (raw-pos jitter): jitter derived from raw float position bits.
//     Each position gets independent jitter → stochastic/soft cell boundaries.
//     Neighboring positions near a boundary have a chance of landing in either
//     cell, effectively low-pass filtering the grid assignment.
//
//   Ablation F2 (Binder-style): jitter derived from quantized cell index.
//     All positions in the same cell get identical jitter → grid shifts
//     uniformly → hard boundaries at new positions. [Binder et al. 2018]
//     Set USE_VISCACHE_JITTER_BINDER=1 to select this mode.
//
// The seed parameter allows different jitter for posA vs posB (using
// 0xAA vs 0xBB), preventing systematic correlation between endpoints.
// The level index is XORed into the seed so different LOD levels get
// independent jitter patterns.
// ---------------------------------------------------------------------------
#ifndef USE_VISCACHE_JITTER_BINDER
#define USE_VISCACHE_JITTER_BINDER 0
#endif

int3 jitterQuantize(float3 pos, float cellSize, uint seed, bool enableJitter)
{
    int3 baseIdx = int3(round(pos / cellSize));
#if USE_VISCACHE_JITTER
    if (enableJitter)
    {
#if USE_VISCACHE_JITTER_BINDER
        // Ablation F2: Binder-style — jitter from quantized cell index.
        uint3 r = pcg3d(uint3(baseIdx) ^ seed);
#else
        // Default: raw-pos jitter — jitter from position float bits.
        uint3 r = pcg3d(asuint(pos) ^ seed);
#endif
        float3 jitter = float3(r & 0xFFFFu) / 65535.0f - 0.5f;
        return int3(round((pos + jitter * cellSize) / cellSize));
    }
#endif
    return baseIdx;
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
float3 vhfAddressPosB(float3 posA, float3 dir, float dist)
{
    // Endpoint mode (canonical, asymmetric, or dirdist) — posB is the light position.
    // In dirdist mode, vhfQuantizePair handles direction encoding directly.
    return posA + dir * dist;
}

// ---------------------------------------------------------------------------
// Canonical quantization: quantize both endpoints and lexicographic-swap
// so that V(A,B) and V(B,A) always produce the same (qa, qb) pair.
//
// Canonicalization: in pos×pos mode, if cellA == cellB (same resolution for
// both endpoints), V(A,B) = V(B,A) so we lexicographic-swap to halve table
// pressure. If cellA != cellB, endpoints have different resolutions — no swap.
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

// Precompute canonicalization flag — constant for all levels in a frame.
#if !USE_VISCACHE_DIRDIST_ADDRESSING
static const bool kCanonicalize = (gCellACoarse == gCellBCoarse);
#endif

void vhfQuantizePair(float3 posA, float3 posB, float cellSizeA, uint lvl,
                     out int3 qa, out int3 qb, float3 normalA = float3(0.f))
{
    bool jitterA = (gFlags & kFlag_EnableJitterA) != 0;
    bool jitterB = (gFlags & kFlag_EnableJitterB) != 0;

    qa = jitterQuantize(posA, cellSizeA, 0xAAu ^ lvl, jitterA);

    // Normal addressing: octahedral-encode normalA and fold into qa hash.
    // This splits cells by surface orientation — same position but different
    // normals (e.g., floor vs wall at a corner) get separate cache entries.
    if (gFlags & kFlag_EnableNormalAddr)
    {
        float2 oct = octEncode(normalA) + 1.f;  // [0, 2]
        // Coarse normal bins: ~6 bins (60° per bin) — separates
        // floor/wall/ceiling without excessive subdivision.
        float normCellOct = max(gNormalBCoarse, 1.f) / 90.f;  // degrees → octahedral cell size
        int2 nBin = int2(floor(oct / normCellOct));
        // XOR-fold into qa to change the hash without adding dimensions.
        qa.x ^= nBin.x * 0x45D9F3Bu;
        qa.y ^= nBin.y * 0xC3A5C85Cu;
    }

#if USE_VISCACHE_DIRDIST_ADDRESSING
    // Dir+dist: 2D octahedral direction bins + distance bin.
    {
        float3 edge = posB - posA;
        float dist = length(edge);
        float3 dir = dist > 1e-6f ? edge / dist : float3(0.f, 1.f, 0.f);
        float angCellOct = vhfAngularSize(lvl) / 90.f;
        float distCell   = vhfDistSize(lvl);
        qb = vhfQuantizeDirection(dir, angCellOct, dist, distCell);
    }
#else
    // Pos×pos: quantize posB at its own cell size from the B cascade.
    float cellB = vhfCellSizeB(lvl);
    qb = jitterQuantize(posB, cellB, 0xBBu ^ lvl, jitterB);

    // Canonicalize only when A and B have the same resolution.
    // Lexicographic sort — collision-free, ensures V(A,B) == V(B,A).
    if (kCanonicalize)
    {
        if (vhfCanonicalLess(qb, qa))
        {
            int3 tmp = qa; qa = qb; qb = tmp;
        }
    }
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
static const uint kFlag_EnableJitterA      = 1u << 0;
static const uint kFlag_EnableJitterB      = 1u << 1;
static const uint kFlag_EnableAdaptivePMin = 1u << 2;
static const uint kFlag_EnableNormalAddr   = 1u << 3;
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

        if (allowInsert)
        {
            // Empty slot — available for new entry.
            if (efp == 0u && gVHFTable[slot].packed == 0u)
            {
                probeSteps = i;
                return int(slot);
            }

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

    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb, normalA);

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
        float mu  = float(vis) / float(total);
        float var = mu * (1.0f - mu);  // Bernoulli variance

        // Always record entry data (even immature) so diagnostics can show it.
        // valid is only set when mature (>= bootThreshold) — the gate uses
        // valid to decide whether to trust the entry for RR decisions.
        best.mu    = mu;
        best.var   = var;
        best.level = lvl;
        best.N     = total;
        if (total >= gBootThreshold)
            best.valid = true;

        // Immature entry: don't stop cascade, let finer levels try.
        if (total < gBootThreshold) continue;

        // Variance gate: if this level is converged (low variance),
        // finer levels would produce the same estimate. Stop early.
        if (var <= gVarThreshold) break;
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
        float cs = vhfCellSize(lvl);
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
    int   level;        ///< LOD level used, -1 = miss (diagnostics)
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
                       float3 normalA = float3(0.f))
{
    VHFGateResult g;
    VHFResult r = vhfLookup(posA, posB, normalA);

    // Quantize at coarsest level for hash grid visualization (diagnostics).
    // Diagnostic hash vis: compute qa/qb exactly as the rendering path does
    // (including normal XOR-fold into qa when enabled).
    vhfQuantizePair(posA, posB, vhfCellSizeA(0), 0u, g.qa, g.qb, normalA);

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
        g.level       = r.level;  // -1 if truly no entry, else immature level
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
    float p = clamp(r.var / gVarThreshold, pFloor, 1.f);

    // Pass through diagnostic fields from the lookup result.
    g.var        = r.var;
    g.level      = r.level;
    g.N          = r.N;
    g.probeSteps = r.probeSteps;

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
                                    float contribLuminance = 0.f,
                                    float3 normalA = float3(0.f))
{
    float xi = vhfDeterministicXi(posA, posB);
    return vhfGate(posA, posB, xi, contribLuminance, normalA);
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
    uint _ps;
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false, _ps);
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
void vhfInsert(float3 posA, float3 posB, float V, float3 normalA = float3(0.f))
{
    uint visVal = (V > 0.5f) ? 1u : 0u;  // Binarize: 1 = visible, 0 = occluded

    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb, normalA);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl), uint(lvl), uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl), uint(lvl), uint(lvl));

        // Gate 1: maturity — skip entries with enough samples.
        // Decay periodically un-matures entries for revalidation.
        // Never skip the finest level — always keep it populated for
        // maximum spatial resolution at shadow boundaries.
        bool isFinestLevel = (lvl == int(gNumLevels) - 1);
        if (!isFinestLevel && vhfIsMature(addr, fp)) continue;

        uint _ps;
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/true, _ps);
        if (slot < 0) continue;  // Table full at this probe depth

        // Atomic CAS: only write fingerprint if slot is still empty (fp==0).
        // Three outcomes:
        //   origFp == 0:  we won the race, slot is now ours
        //   origFp == fp: same cell pair, another thread got here first — OK
        //   origFp != fp: different cell pair claimed this slot — skip
        uint origFp;
        InterlockedCompareExchange(gVHFTable[slot].fingerprint, 0u, fp, origFp);
        if (origFp != 0u && origFp != fp)
        {
            // Evict: overwrite fingerprint and zero packed data.
            // vhfFindSlot verified this entry had too few samples to keep
            // (pressure-scaled eviction at probe depth >= kEvictStartStep).
            uint dummy;
            InterlockedExchange(gVHFTable[slot].fingerprint, fp, dummy);
            InterlockedExchange(gVHFTable[slot].packed, 0u, dummy);
        }

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
float vhfCommit(float3 posA, float3 posB, float V, VHFGateResult g,
                float3 normalA = float3(0.f))
{
    vhfInsert(posA, posB, V, normalA);
    return g.mu + (V - g.mu) * g.invP;
}

#endif // USE_VISCACHE

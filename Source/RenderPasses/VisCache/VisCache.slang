/***************************************************************************
 * VisCache.slang
 *
 * Visibility Cache — Core Data Structure
 * Kugelmann 2026, extending Kugelmann 2006
 *
 * N-level spatial hash table caching pairwise visibility between
 * arbitrary endpoint pairs A and B (canonical symmetric cell sizes).
 * Scale-agnostic: level count and cell range are runtime parameters.
 *
 * Addressing: jitter-before-quantize [Binder et al. 2018]
 * Hash:       PCG3D [Jarzynski & Olano 2020]
 * LOD:        full cascade L0..N-1, variance-gated (no distance heuristic)
 * Contention: read-before-write skip at converged entries
 * Estimator:  CV+RRR [Szirmay-Kalos et al. 2005 / Kugelmann 2006]
 ***************************************************************************/

#pragma once

// ---------------------------------------------------------------------------
// Entry: 8 bytes — fingerprint + packed (vis:16 | total:16)
// ---------------------------------------------------------------------------
struct VHFEntry
{
    uint fingerprint;   ///< Collision detection [Binder et al. 2018]
    uint packed;        ///< [vis_count:16 | total_count:16]
};

// ---------------------------------------------------------------------------
// Cache query result
// ---------------------------------------------------------------------------
struct VHFResult
{
    float mu;       ///< Cached visibility mean
    float var;      ///< Variance = mu*(1-mu)
    int   level;    ///< LOD level that returned this result (-1 = miss)
    bool  valid;    ///< false = cold miss, always trace
};

// ---------------------------------------------------------------------------
// Parameters (uploaded as cbuffer each frame)
// ---------------------------------------------------------------------------
cbuffer VisCacheParams
{
    uint   gTableCapacity;   ///< Power-of-two entry count
    uint   gBootThreshold;   ///< Min total_count before entry is trusted (32)
    float  gVarThreshold;    ///< Variance below which we stop refining (0.1)
    float  gPMin;            ///< Minimum RR survival probability (0.05)
    float  gFireflyBudget;   ///< Contribution scale for adaptive pMin
    uint   gNumLevels;       ///< Number of LOD levels (runtime, arbitrary N)
    float  gCellCoarse;      ///< L0 cell size (world units)
    float  gCellFine;        ///< L_{N-1} cell size (world units)
};

/// Cell size for level `lvl` — geometric interpolation, coarse to fine.
/// Scale-agnostic: driven entirely by gCellCoarse, gCellFine, gNumLevels.
float vhfCellSize(int lvl)
{
    float t = (gNumLevels <= 1u) ? 0.f : float(lvl) / float(gNumLevels - 1u);
    return gCellCoarse * exp(t * log(gCellFine / gCellCoarse));
}

RWStructuredBuffer<VHFEntry> gVHFTable;

// ---------------------------------------------------------------------------
// PCG3D hash [Jarzynski & Olano, JCGT 2020]
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
// Jitter-before-quantize [Binder et al. 2018]
// Position-only — no frame number, so a fixed position always maps to the
// same cell regardless of when it is queried.
// ---------------------------------------------------------------------------
int3 jitterQuantize(float3 pos, float cellSize, uint seed)
{
    // Quantize without jitter first to get a stable base index
    int3 baseIdx = int3(floor(pos / cellSize));
    // Deterministic per-cell jitter in [−0.5, +0.5) cell widths
    uint3 r = pcg3d(uint3(baseIdx) ^ seed);
    float3 jitter = float3(r & 0xFFFFu) / 65535.0f - 0.5f;
    return int3(floor((pos + jitter * cellSize) / cellSize));
}

// ---------------------------------------------------------------------------
// Canonical quantize — quantize both endpoints and lexicographic-swap so
// that V(A,B) and V(B,A) always map to the same cell pair.
// ---------------------------------------------------------------------------
void vhfQuantizePair(float3 posA, float3 posB, float cellSize, uint lvl,
                     out int3 qa, out int3 qb)
{
    qa = jitterQuantize(posA, cellSize, 0xAAu ^ lvl);
    qb = jitterQuantize(posB, cellSize, 0xBBu ^ lvl);
    // Lexicographic swap: ensure qa <= qb so (A,B) and (B,A) are identical.
    if (qa.x > qb.x || (qa.x == qb.x && (qa.y > qb.y || (qa.y == qb.y && qa.z > qb.z))))
    {
        int3 tmp = qa; qa = qb; qb = tmp;
    }
}

// ---------------------------------------------------------------------------
// Address and fingerprint functions
// Two different hash chains to keep them independent [Binder et al. 2018].
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

// ---------------------------------------------------------------------------
// Double-hash probe sequence [Binder et al. 2018]
// h2 is derived from fingerprint (odd, ensures full table coverage).
// Pressure-scaled eviction: steps 0–1 protected, step ≥2 may evict.
// Returns slot index, or -1 if probe exhausted.
// ---------------------------------------------------------------------------
static const uint kMaxProbe = 8u;

int vhfFindSlot(uint addr0, uint fp, bool allowInsert)
{
    uint h2 = fp | 1u;  // odd step
    for (uint i = 0u; i < kMaxProbe; i++)
    {
        uint slot = (addr0 + i * h2) & (gTableCapacity - 1u);
        uint efp  = gVHFTable[slot].fingerprint;

        if (efp == fp)
            return int(slot);

        if (allowInsert)
        {
            // Empty slot: take it
            if (efp == 0u && gVHFTable[slot].packed == 0u)
                return int(slot);

            // Pressure-scaled eviction: never evict steps 0–1
            if (i >= 2u)
            {
                uint total = gVHFTable[slot].packed & 0xFFFFu;
                // Eviction threshold doubles each step — long chains self-heal
                uint threshold = 4u << (i - 2u);
                if (total < threshold)
                    return int(slot);
            }
        }
    }
    return -1;
}

// ===========================================================================
// LOD selection — full cascade L0..N-1, variance gate handles the rest.
//
// No distance heuristic, no static contention threshold.
// Coarse levels converge fast (many updates) → read-before-write in insert
// skips the atomic once converged. This is dynamic contention avoidance:
// contention at L0 is self-limiting because L0 converges quickly.
// ===========================================================================

/// Full cascade: always L0..N-1. The variance gate in lookup and the
/// read-before-write skip in insert handle level selection dynamically.
void vhfLOD(out int loLvl, out int hiLvl)
{
    loLvl = 0;
    hiLvl = int(gNumLevels) - 1;
}

/// Fixed single level — for ablation (single-level testing).
void vhfLOD_Fixed(int level, out int loLvl, out int hiLvl)
{
    loLvl = clamp(level, 0, int(gNumLevels) - 1);
    hiLvl = loLvl;
}

// ===========================================================================
// Core LOOKUP — explicit LOD range, no LOD policy dependency.
// ===========================================================================

// ---------------------------------------------------------------------------
// Coarse-to-fine LOOKUP with explicit LOD range.
// Returns the finest converged result within [loLvl, hiLvl].
// Four stopping conditions: level bounds, no entry, too few samples, low var.
// ---------------------------------------------------------------------------
VHFResult vhfLookupRange(float3 posA, float3 posB, int loLvl, int hiLvl)
{
    VHFResult best;
    best.mu    = 0.5f;
    best.var   = 1.0f;
    best.level = -1;
    best.valid = false;

    for (int lvl = loLvl; lvl <= hiLvl; lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/false);

        if (slot < 0) break;  // no entry at this level — stop

        VHFEntry e  = gVHFTable[slot];
        uint total  = e.packed & 0xFFFFu;
        if (total < gBootThreshold) break;  // too few samples — not trusted

        uint  vis = e.packed >> 16u;
        float mu  = float(vis) / float(total);
        float var = mu * (1.0f - mu);

        best.mu    = mu;
        best.var   = var;
        best.level = lvl;
        best.valid = true;

        if (var <= gVarThreshold) break;  // converged — no need to go finer
    }

    return best;
}

/// Convenience: lookup using full cascade.
VHFResult vhfLookup(float3 posA, float3 posB)
{
    int lo, hi;
    vhfLOD(lo, hi);
    return vhfLookupRange(posA, posB, lo, hi);
}

// ---------------------------------------------------------------------------
// Two-phase gate/commit API — core CV+RRR estimator.
// Eliminates inline duplication in consumer passes.
//
// Minimal signature: two arbitrary endpoints A, B of a visibility query.
// LOD is full cascade (L0..N-1); contention handled by read-before-write.
//
// Usage (any pass):
//   VHFGateResult g = vhfGate(posA, posB, rand01);
//   if (g.shouldTrace) {
//       float V = <pass-specific trace call>;
//       visWeight = vhfCommit(posA, posB, V, g);
//   } else {
//       visWeight = g.visWeight;
//   }
// ---------------------------------------------------------------------------
struct VHFGateResult
{
    bool  shouldTrace;  ///< true = caller must trace and call vhfCommit
    float visWeight;    ///< final answer when !shouldTrace (= cached mu)
    float mu;           ///< cached mean (needed by vhfCommit)
    float invP;         ///< 1/p (needed by vhfCommit)
};

/// Phase 1: lookup + RR decision.
/// posA, posB: arbitrary endpoints of the visibility query.
/// xi: uniform random in [0,1) for RR coin flip.
/// contribLuminance > 0 enables firefly-aware adaptive pMin (§10.1).
/// Uses full cascade LOD.
VHFGateResult vhfGate(float3 posA, float3 posB,
                       float xi, float contribLuminance = 0.f)
{
    int lo, hi;
    vhfLOD(lo, hi);
    return vhfGateRange(posA, posB, lo, hi, xi, contribLuminance);
}

/// Phase 1 with explicit LOD range — core, LOD-agnostic.
VHFGateResult vhfGateRange(float3 posA, float3 posB,
                            int loLvl, int hiLvl,
                            float xi, float contribLuminance = 0.f)
{
    VHFGateResult g;
    VHFResult r = vhfLookupRange(posA, posB, loLvl, hiLvl);

    if (!r.valid)
    {
        // Cold miss — always trace. mu=0, invP=1 → commit returns V directly.
        g.shouldTrace = true;
        g.visWeight   = 0.f;
        g.mu          = 0.f;
        g.invP        = 1.f;
        return g;
    }

    // Compute RR probability.
    float pFloor = gPMin;
    if (contribLuminance > 0.f)
    {
        float contrib = contribLuminance * max(r.mu, 1.f - r.mu);
        pFloor = clamp(contrib / gFireflyBudget, gPMin, 1.f);
    }
    float p = clamp(r.var / gVarThreshold, pFloor, 1.f);

    if (xi < p)
    {
        // Trace correction ray.
        g.shouldTrace = true;
        g.visWeight   = 0.f;  // placeholder — caller uses vhfCommit
        g.mu          = r.mu;
        g.invP        = 1.f / p;
    }
    else
    {
        // No trace — use cached mean.
        g.shouldTrace = false;
        g.visWeight   = r.mu;
        g.mu          = r.mu;
        g.invP        = 0.f;  // unused
    }
    return g;
}

// ---------------------------------------------------------------------------
// Deterministic xi — derive RR coin flip from quantized cell coordinates.
// Same (posA, posB) pair always gets the same xi within the finest usable
// level, eliminating temporal flicker from stochastic RR.
// No frame index: the cache's own convergence drives temporal adaptation.
// ---------------------------------------------------------------------------
float vhfDeterministicXi(float3 posA, float3 posB, int hiLvl)
{
    float cs = vhfCellSize(hiLvl);
    int3 qa, qb;
    vhfQuantizePair(posA, posB, cs, uint(hiLvl), qa, qb);
    // Third hash chain (salt 0xCCu) — independent of addr/fingerprint chains
    uint3 h = pcg3d(uint3(
        (uint(qa.x) ^ uint(qb.x)) + 0xCCu,
        (uint(qa.y) ^ uint(qb.y)) + 0xCCu,
        (uint(qa.z) ^ uint(qb.z)) + uint(hiLvl) * 0x13371337u
    ));
    return float(h.x) / 4294967295.0f; // [0, 1]
}

/// Phase 1 with deterministic xi — no external random number needed.
/// Same cell pair always gets the same RR decision → no temporal flicker.
VHFGateResult vhfGateDeterministic(float3 posA, float3 posB,
                                    float contribLuminance = 0.f)
{
    int lo, hi;
    vhfLOD(lo, hi);
    float xi = vhfDeterministicXi(posA, posB, hi);
    return vhfGateRange(posA, posB, lo, hi, xi, contribLuminance);
}

/// Phase 2: after tracing, compute final CV+RRR weight and insert into cache.
/// Uses full cascade LOD.
/// Returns fractional visWeight in [0, 1].
float vhfCommit(float3 posA, float3 posB, float V, VHFGateResult g)
{
    int lo, hi;
    vhfLOD(lo, hi);
    vhfInsertRange(posA, posB, V, lo, hi);
    return g.mu + (V - g.mu) * g.invP;
}

/// Phase 2 with explicit LOD range.
float vhfCommitRange(float3 posA, float3 posB, float V,
                      int loLvl, int hiLvl, VHFGateResult g)
{
    vhfInsertRange(posA, posB, V, loLvl, hiLvl);
    return g.mu + (V - g.mu) * g.invP;
}

// ===========================================================================
// Core INSERT — explicit LOD range, no LOD policy dependency.
// ===========================================================================

// ---------------------------------------------------------------------------
// Maturity gate: "mature" = standard error of the mean is small enough
// that additional writes have diminishing returns.
//
//   SE = sqrt(mu*(1-mu) / n)  ≤  SE_threshold
//   ⟹  n ≥ mu*(1-mu) / SE_threshold²
//
// We use SE_threshold² = gVarThreshold / gBootThreshold, which gives:
//   requiredSamples = mu*(1-mu) * gBootThreshold / gVarThreshold
//
// Examples (boot=32, varThr=0.1):
//   mu=1.0  → var=0.00, required=0    → mature immediately (unanimous)
//   mu=0.95 → var=0.05, required=16   → mature quickly (19:1 split)
//   mu=0.50 → var=0.25, required=80   → needs more (shadow boundary)
//   mu=0.70 → var=0.21, required=67   → intermediate
//
// Decay periodically halves counts, temporarily un-maturing entries for
// fresh sampling (revalidation). No coin flip needed.
// ---------------------------------------------------------------------------
bool vhfIsMature(uint addr, uint fp)
{
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false);
    if (slot < 0) return false;  // no entry → cold

    uint packed = gVHFTable[slot].packed;
    uint total  = packed & 0xFFFFu;
    if (total < 2u) return false;  // need at least 2 samples for variance

    uint  vis = packed >> 16u;
    float mu  = float(vis) / float(total);
    float var = mu * (1.0f - mu);

    // Required samples scales with variance: high-var cells need more.
    float required = var * float(gBootThreshold) / gVarThreshold;
    return float(total) >= required;
}

/// Inline overflow decay — subtract 1/8 of both counters when total > 0xE000.
/// Returns the post-decay packed value (for cascaded variance gate check).
uint vhfOverflowDecay(int slot, uint cur)
{
    if ((cur & 0xFFFFu) > 0xE000u)
    {
        uint visHalf   = (cur >> 16u) >> 3u;
        uint totalHalf = (cur & 0xFFFFu) >> 3u;
        uint sub       = (visHalf << 16u) | totalHalf;
        InterlockedAdd(gVHFTable[slot].packed, -sub);
        cur -= sub;
    }
    return cur;
}

// ---------------------------------------------------------------------------
// INSERT with explicit LOD range.
// Coarse-to-fine cascade with two gates:
//
// 1. Maturity gate (before write): if total >= boot, skip — the entry has
//    enough samples. Decay periodically halves counts, temporarily un-maturing
//    entries for fresh sampling. No coin flip needed.
//
// 2. Cascaded variance gate (after write): if var <= threshold, stop descending
//    to finer levels — this region is smooth, finer detail is wasteful.
//
// Single InterlockedAdd keeps vis and total always in sync.
// Inline overflow decay: subtract 1/8 when total > 0xE000.
// ---------------------------------------------------------------------------
void vhfInsertRange(float3 posA, float3 posB, float V, int loLvl, int hiLvl)
{
    uint visVal = (V > 0.5f) ? 1u : 0u;

    for (int lvl = loLvl; lvl <= hiLvl; lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, uint(lvl), qa, qb);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));

        // Maturity gate: skip mature entries (decay revalidates periodically)
        if (vhfIsMature(addr, fp)) continue;

        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/true);
        if (slot < 0) continue;  // table full at this cell — skip

        // Set fingerprint if slot was empty
        if (gVHFTable[slot].fingerprint == 0u)
            gVHFTable[slot].fingerprint = fp;

        // Atomic packed increment: vis in high 16 bits, total in low 16 bits
        uint delta = (visVal << 16u) | 1u;
        uint prev;
        InterlockedAdd(gVHFTable[slot].packed, delta, prev);

        uint cur = vhfOverflowDecay(slot, prev + delta);

        // Cascaded gate: if this level is now smooth, stop.
        uint totalCur = cur & 0xFFFFu;
        if (totalCur >= gBootThreshold)
        {
            uint visCur  = cur >> 16u;
            float muCur  = float(visCur) / float(totalCur);
            float varCur = muCur * (1.0f - muCur);
            if (varCur <= gVarThreshold)
                break;  // this level is smooth — no need to go finer
        }
    }
}

/// Convenience: insert using full cascade.
void vhfInsert(float3 posA, float3 posB, float V)
{
    int lo, hi;
    vhfLOD(lo, hi);
    vhfInsertRange(posA, posB, V, lo, hi);
}

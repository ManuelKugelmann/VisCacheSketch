/***************************************************************************
 * VisCache.slang
 *
 * Visibility Cache — Core Data Structure
 * Kugelmann 2026, extending Kugelmann 2006
 *
 * N-level spatial hash table caching pairwise visibility between
 * arbitrary endpoint pairs A and B (canonical symmetric cell sizes).
 *
 * Addressing: jitter-before-quantize [Binder et al. 2018]
 * Hash:       PCG3D [Jarzynski & Olano 2020]
 * LOD:        distance-gated coarse-to-fine [Gautron 2020]
 * Estimator:  CV+RRR [Szirmay-Kalos et al. 2005 / Kugelmann 2006]
 ***************************************************************************/

#pragma once

// ---------------------------------------------------------------------------
// Cell sizes (world units).
// Canonical: both endpoints A and B use the same cell size per level.
// Geometric progression from coarse (L0) to fine (L_max), base factor ~8×.
// Calibrated for viewing distances 2–20 m, mixed scenes (Bistro, Sponza).
//
// Future work: asymmetric A/B cell sizes (shading point finer than light).
// ---------------------------------------------------------------------------
static const uint  kNumLevels    = 3;
static const float kCellCoarse   = 10.0f;   ///< L0 cell size (metres)
static const float kCellFine     = 0.16f;   ///< L_{max} cell size (metres)

/// Cell size for level `lvl` — geometric interpolation, coarse to fine.
float vhfCellSize(int lvl)
{
    float t = (kNumLevels <= 1) ? 0.f : float(lvl) / float(kNumLevels - 1);
    return kCellCoarse * exp(t * log(kCellFine / kCellCoarse));
}

// Maximum cell size below which contention is acceptable.
// Coarser levels cover huge world regions → many threads hit the same cell
// → atomics contention. Skip levels where cell > this threshold.
static const float kMaxUsableCellSize = 20.0f;  // metres

// LOD footprint bounds (pixels) for distance-gated selection
static const float kFootprintMin = 4.0f;
static const float kFootprintMax = 64.0f;

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
    float3 gCamPos;          ///< Camera position (per-frame, for LOD selection)
};

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
        uint(qa.x) ^ uint(qb.x) + 7u,
        uint(qa.y) ^ uint(qb.y) + 13u,
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
// LOD selection — separated from core lookup/insert so callers can override.
// ===========================================================================

/// Lowest usable level — skip levels where cell > kMaxUsableCellSize
/// to avoid heavy atomic contention at coarse LODs.
int vhfMinUsableLevel()
{
    for (int lvl = 0; lvl < int(kNumLevels); lvl++)
        if (vhfCellSize(lvl) <= kMaxUsableCellSize) return lvl;
    return int(kNumLevels) - 1;
}

// ---------------------------------------------------------------------------
// Camera-distance LOD [Gautron, SIGGRAPH Talks 2020]
// Default strategy: projected cell footprint in pixels.
// Clamps coarse end to skip contention-prone levels.
// ---------------------------------------------------------------------------
void vhfLOD_Camera(float3 posA, float3 camPos, out int loLvl, out int hiLvl)
{
    float d = length(posA - camPos);
    int minLvl = vhfMinUsableLevel();
    loLvl = clamp(int(log2(d / kFootprintMax)), minLvl, int(kNumLevels) - 1);
    hiLvl = clamp(int(log2(d / kFootprintMin)), minLvl, int(kNumLevels) - 1);
}

/// Full cascade — all usable levels (skips contention-prone coarse end).
void vhfLOD_Full(out int loLvl, out int hiLvl)
{
    loLvl = vhfMinUsableLevel();
    hiLvl = int(kNumLevels) - 1;
}

/// Fixed single level — caller picks.
void vhfLOD_Fixed(int level, out int loLvl, out int hiLvl)
{
    loLvl = clamp(level, 0, int(kNumLevels) - 1);
    hiLvl = loLvl;
}

/// Default LOD using gCamPos from cbuffer.
void vhfLOD(float3 posA, out int loLvl, out int hiLvl)
{
    vhfLOD_Camera(posA, gCamPos, loLvl, hiLvl);
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
        int3 qa = jitterQuantize(posA, cs, 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(posB, cs, 0xBBu ^ uint(lvl));

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

/// Convenience: lookup using default LOD (camera-distance via cbuffer).
VHFResult vhfLookup(float3 posA, float3 posB, float3 camPos)
{
    int lo, hi;
    vhfLOD_Camera(posA, camPos, lo, hi);
    return vhfLookupRange(posA, posB, lo, hi);
}

// ---------------------------------------------------------------------------
// Two-phase gate/commit API — core CV+RRR estimator.
// Eliminates inline duplication in consumer passes.
//
// Minimal signature: two arbitrary endpoints A, B of a visibility query.
// camPos comes from VisCacheParams cbuffer (same for all pixels in a frame).
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
/// Uses default camera-distance LOD from cbuffer.
VHFGateResult vhfGate(float3 posA, float3 posB,
                       float xi, float contribLuminance = 0.f)
{
    int lo, hi;
    vhfLOD(posA, lo, hi);
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

/// Phase 2: after tracing, compute final CV+RRR weight and insert into cache.
/// Uses default camera-distance LOD from cbuffer.
/// Returns fractional visWeight in [0, 1].
float vhfCommit(float3 posA, float3 posB, float V, VHFGateResult g)
{
    int lo, hi;
    vhfLOD(posA, lo, hi);
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
// INSERT with explicit LOD range.
// Coarse-to-fine cascaded variance gate: write L0, check its variance to
// decide L1, write L1, check its variance to decide L2, etc.
// Uses the post-increment packed value directly — no extra parent lookup.
// Single InterlockedAdd keeps vis and total always in sync.
// Inline overflow decay: subtract 1/8 when total > 0xE000.
// ---------------------------------------------------------------------------
void vhfInsertRange(float3 posA, float3 posB, float V, int loLvl, int hiLvl)
{
    uint visVal = (V > 0.5f) ? 1u : 0u;

    for (int lvl = loLvl; lvl <= hiLvl; lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa = jitterQuantize(posA, cs, 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(posB, cs, 0xBBu ^ uint(lvl));

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));
        int  slot = vhfFindSlot(addr, fp, /*allowInsert=*/true);

        if (slot < 0) continue;  // table full at this cell — skip

        // Set fingerprint if slot was empty
        if (gVHFTable[slot].fingerprint == 0u)
            gVHFTable[slot].fingerprint = fp;

        // Atomic packed increment: vis in high 16 bits, total in low 16 bits
        uint delta = (visVal << 16u) | 1u;
        uint prev;
        InterlockedAdd(gVHFTable[slot].packed, delta, prev);

        // Inline overflow decay: when total approaches uint16 max,
        // subtract 1/8 of both counters to keep counts near ceiling.
        // Integer shift-truncation preserves mean ratio within ~0.003%.
        uint cur = prev + delta;
        if ((cur & 0xFFFFu) > 0xE000u)
        {
            uint visHalf   = (cur >> 16u) >> 3u;
            uint totalHalf = (cur & 0xFFFFu) >> 3u;
            uint sub       = (visHalf << 16u) | totalHalf;
            InterlockedAdd(gVHFTable[slot].packed, -sub);
            cur = cur - sub;
        }

        // Cascaded gate: Bernoulli variance mu*(1-mu) of this level
        // decides whether to continue to the next finer level.
        // No extra lookup — uses post-increment packed value directly.
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

/// Convenience: insert using camera-distance LOD.
void vhfInsert(float3 posA, float3 posB, float V, float3 camPos)
{
    int lo, hi;
    vhfLOD_Camera(posA, camPos, lo, hi);
    vhfInsertRange(posA, posB, V, lo, hi);
}

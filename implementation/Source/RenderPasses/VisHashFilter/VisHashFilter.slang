/***************************************************************************
 * VisHashFilter.slang
 *
 * Multilevel Visibility Hash Filter — Core Data Structure
 * Kugelmann 2026, extending Kugelmann 2006
 *
 * Three-level spatial hash table caching pairwise visibility between
 * surface regions and light/secondary-hit regions.
 *
 * Addressing: jitter-before-quantize [Binder et al. 2018]
 * Hash:       PCG3D [Jarzynski & Olano 2020]
 * LOD:        distance-gated coarse-to-fine [Gautron 2020]
 * Estimator:  CV+RRR [Szirmay-Kalos et al. 2005 / Kugelmann 2006]
 ***************************************************************************/

#pragma once

// ---------------------------------------------------------------------------
// Cell sizes (world units) — calibrated for viewing distances 2–20 m,
// exterior/interior mixed scenes (Bistro, Sponza).
// Asymmetric: endpoint A (shading point) finer than B (light/secondary hit).
// See §5.2 and future-work note on camera-adaptive scaling.
// ---------------------------------------------------------------------------
static const uint  kNumLevels    = 3;
static const float kCellA[3]     = { 10.0f, 1.25f, 0.08f };  // metres
static const float kCellB[3]     = { 10.0f, 2.50f, 0.62f };

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
cbuffer VHFParams
{
    uint  gTableCapacity;   ///< Power-of-two entry count
    uint  gBootThreshold;   ///< Min total_count before entry is trusted (32)
    float gVarThreshold;    ///< Variance below which we stop refining (0.1)
    float gPMin;            ///< Minimum RR survival probability (0.05)
    float gFireflyBudget;   ///< Contribution scale for adaptive pMin
    uint  _pad0;
    uint  _pad1;
    uint  _pad2;
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
// Two different hash chains to keep them independent [Keller et al. 2016].
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

// ---------------------------------------------------------------------------
// Distance-gated LOD range [Gautron, SIGGRAPH Talks 2020]
// Returns [lo, hi] level indices; lo ≥ hi means query only one level.
// Footprint heuristic approximates projected cell size in pixels.
// TODO (future work): replace with exact FoV / CoC computation.
// ---------------------------------------------------------------------------
void vhfDistLOD(float3 posA, float3 camPos, out int loLvl, out int hiLvl)
{
    float d = length(posA - camPos);
    // Approximate pixel footprint at this distance (scene-scale heuristic)
    loLvl = clamp(int(log2(d / kFootprintMax)), 0, int(kNumLevels) - 1);
    hiLvl = clamp(int(log2(d / kFootprintMin)), 0, int(kNumLevels) - 1);
}

// ---------------------------------------------------------------------------
// Coarse-to-fine LOOKUP
// Returns the finest converged result within the distance-gated LOD range.
// Four stopping conditions: dist bounds, no entry, too few samples, low var.
// ---------------------------------------------------------------------------
VHFResult vhfLookup(float3 posA, float3 posB, float3 camPos)
{
    VHFResult best;
    best.mu    = 0.5f;
    best.var   = 1.0f;
    best.level = -1;
    best.valid = false;

    int lo, hi;
    vhfDistLOD(posA, camPos, lo, hi);

    for (int lvl = lo; lvl <= hi; lvl++)
    {
        int3 qa = jitterQuantize(posA, kCellA[lvl], 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(posB, kCellB[lvl], 0xBBu ^ uint(lvl));

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

        if (var < 0.01f) break;  // converged — no need to go finer
    }

    return best;
}

// ---------------------------------------------------------------------------
// INSERT (called after tracing a shadow ray)
// Variance-gated write depth: only writes fine levels at shadow boundaries.
// Single InterlockedAdd keeps vis and total always in sync.
// Inline overflow decay: subtract 1/8 when total > 0xE000.
// ---------------------------------------------------------------------------
void vhfInsert(float3 posA, float3 posB, float V, float3 camPos)
{
    int lo, hi;
    vhfDistLOD(posA, camPos, lo, hi);

    // Bootstrap or boundary check: determine max write depth
    int3 qa0 = jitterQuantize(posA, kCellA[lo], 0xAAu ^ uint(lo));
    int3 qb0 = jitterQuantize(posB, kCellB[lo], 0xBBu ^ uint(lo));
    uint fp0   = vhfFingerprint(qa0, qb0, uint(lo));
    uint addr0 = vhfAddr(qa0, qb0, uint(lo));
    int  slot0 = vhfFindSlot(addr0, fp0, false);

    int vmax;
    if (slot0 < 0)
    {
        vmax = int(kNumLevels) - 1;  // bootstrap: write all levels
    }
    else
    {
        uint total0 = gVHFTable[slot0].packed & 0xFFFFu;
        if (total0 < gBootThreshold)
        {
            vmax = int(kNumLevels) - 1;  // still bootstrapping
        }
        else
        {
            uint vis0 = gVHFTable[slot0].packed >> 16u;
            float mu0 = float(vis0) / float(total0);
            float var0 = mu0 * (1.0f - mu0);
            // Variance gate: only write fine levels at shadow boundaries
            vmax = (var0 > gVarThreshold) ? int(kNumLevels) - 1 : lo;
        }
    }

    uint visVal = (V > 0.5f) ? 1u : 0u;

    for (int lvl = lo; lvl <= min(hi, vmax); lvl++)
    {
        int3 qa = jitterQuantize(posA, kCellA[lvl], 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(posB, kCellB[lvl], 0xBBu ^ uint(lvl));

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
        }
    }
}

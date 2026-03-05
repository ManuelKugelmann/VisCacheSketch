// ═══════════════════════════════════════════════════════════════════
// VisibilityCache.hlsl — Multilevel Visibility Hash Filter
//
// Include from your shaders to access the cache API.
// Buffers/constants set globally by VisibilityCache.cs via Bind().
//
// Public API:
//   VCShadowQuery VCQueryShadow(posA, posB, contribution, rng01)
//   VCShadowQuery VCQueryShadowInf(posA, dirB, contribution, rng01)
//   void          VCRecordShadow(posA, posB, visible)
//   void          VCRecordShadowInf(posA, dirB, visible)
//   float         VCEstimate(query, tracedVisible)         // unbiased
//   float         VCEstimateClamped(query, tracedVisible)  // biased [0,1]
// ═══════════════════════════════════════════════════════════════════

#ifndef VISIBILITY_CACHE_HLSL
#define VISIBILITY_CACHE_HLSL

// ─── Configuration ──────────────────────────────────────────────
#define VC_NUM_LEVELS       3
#define VC_MAX_PROBES       8
#define VC_BOOT_THRESHOLD   8u      // samples before entry is mature
#define VC_MIN_WEIGHT       4u      // minimum total for a valid lookup
#define VC_OVERFLOW_TRIGGER 60000u  // ~92% of uint16 max
#define VC_OVERFLOW_SHIFT   3u      // subtract 1/8 on overflow
#define VC_EVICT_PROTECT    2u      // first N probe steps are protected
#define VC_TOMBSTONE        0xFFFFFFFEu  // deleted-but-chain-continues marker

// ─── Buffers (bound globally by C#) ─────────────────────────────
// Table: 2 uints per entry — [fingerprint, packed(vis16|total16)]
RWStructuredBuffer<uint> _VCTable;
// Stats: 6 atomic counters
RWStructuredBuffer<uint> _VCStats;

// ─── Constants (bound globally by C#) ───────────────────────────
uint    _VCTableSize;       // entry count (power of 2)
uint    _VCTableMask;       // _VCTableSize - 1
float4  _VCCameraPos;       // xyz = world position
float   _VCTanHalfFov;      // tan(camera.fieldOfView * 0.5 * DEG2RAD)
float   _VCScreenHeight;    // pixels
float   _VCMinPixels;       // 4.0  — skip LOD if cell < this many px
float   _VCMaxPixels;       // 64.0 — skip LOD if cell > this many px
float   _VCVarThreshold;    // tau_rr: RR gating threshold (e.g. 0.1)
float   _VCPMin;            // minimum survival probability (e.g. 0.05)
float   _VCFireflyBudget;   // adaptive p_min contribution ceiling
float4  _VCCellA;           // xyz = L0,L1,L2 cell sizes for endpoint A
float4  _VCCellB;           // xyz = L0,L1,L2 cell sizes for endpoint B
float4  _VCAngularRes;      // xyz = L0,L1,L2 angular cell in oct-space
uint    _VCFrame;           // bound by C#, available for user shaders
uint    _VCDecayOffset;     // start slot for this frame's decay pass
uint    _VCDecayCount;      // how many slots to decay this frame
uint    _VCDecayShift;      // right-shift for background decay (1=halve, 3=1/8)

// Stats buffer layout (indices).
// INSERTS + EVICTIONS are always on (autotune needs them).
// Others are opt-in, ranked by hot-path impact:
//   VC_STATS_PROBES  — per probe step in find/insert (highest cost)
//   VC_STATS_QUERIES — per lookup: LOOKUPS + MISSES (medium cost)
//   VC_STATS_DECAYS  — overflow decay events (background only, ~zero cost)
#define VC_STAT_INSERTS   0  // always on
#define VC_STAT_EVICTIONS 1  // always on
#define VC_STAT_MISSES    2  // #ifdef VC_STATS_QUERIES
#define VC_STAT_DECAYS    3  // #ifdef VC_STATS_DECAYS
#define VC_STAT_PROBES    4  // #ifdef VC_STATS_PROBES
#define VC_STAT_LOOKUPS   5  // #ifdef VC_STATS_QUERIES

// ─── Structs ────────────────────────────────────────────────────

struct VCShadowQuery
{
    float mean;         // cached mean visibility [0,1]
    float variance;     // mean*(1-mean)
    float survivalP;    // RR survival probability actually used
    bool  shouldTrace;  // true → caller must trace shadow ray
    bool  isMiss;       // true → no cache entry found
};

struct VCFindResult
{
    bool  found;
    uint  slot;
    float mean;
    float variance;
    uint  total;
};

// ═══════════════════════════════════════════════════════════════════
// HASH — pcg3d (Jarzynski & Olano, 2020)
// ═══════════════════════════════════════════════════════════════════

uint3 vc_pcg3d(uint3 v)
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

// ═══════════════════════════════════════════════════════════════════
// QUANTIZATION
// ═══════════════════════════════════════════════════════════════════

// Stochastic jitter-before-quantize.
// Seeded from raw float bits — each surface point gets independent jitter.
// Unlike cell-seeded jitter [Binder et al., 2018] which creates sharp step
// functions at (irregularly placed) cell boundaries, position-seeded jitter
// gives probabilistic cell membership near boundaries: an intrinsic box
// filter that eliminates boundary bias. The marginal variance increase from
// boundary dilution is noise (reduces with accumulation), while cell-seeded
// boundary steps are persistent bias.
int3 vc_quantize_pos(float3 pos, float cellSize)
{
    uint3  h      = vc_pcg3d(asuint(pos));
    float3 jitter = float3(h) * (1.0 / 4294967295.0) * cellSize;
    return int3(floor((pos + jitter) / cellSize));
}

// Octahedral mapping for infinite endpoints (IBL / directional).
int3 vc_quantize_dir(float3 dir, float angRes)
{
    float3 n = dir / (abs(dir.x) + abs(dir.y) + abs(dir.z));
    float2 oct;
    if (n.z >= 0.0)
    {
        oct = n.xy;
    }
    else
    {
        float2 s = float2(n.x >= 0.0 ? 1.0 : -1.0,
                          n.y >= 0.0 ? 1.0 : -1.0);
        oct = (1.0 - abs(n.yx)) * s;
    }
    uint3  h      = vc_pcg3d(asuint(dir));
    float2 jitter = float2(h.xy) * (1.0 / 4294967295.0) * angRes;
    int2   cell   = int2(floor((oct + jitter) / angRes));
    return int3(cell, 0x7FFF7FFF); // z sentinel marks angular quantization
}

// ═══════════════════════════════════════════════════════════════════
// ADDRESS + FINGERPRINT HASHING
// ═══════════════════════════════════════════════════════════════════

// Two independent hashes from the same quantized cell pair.
// isInf flag mixed in to prevent cross-space collisions.

uint vc_hash_addr(int3 qA, int3 qB, uint level, uint isInf)
{
    uint3 seed = uint3(qA) ^ (uint3(qB) * 2654435761u);
    seed.x ^= level * 0x9E3779B9u;
    seed.y ^= isInf * 0x85EBCA6Bu;
    uint3 h = vc_pcg3d(seed);
    return (h.x ^ h.y ^ h.z) & _VCTableMask;
}

uint vc_hash_fp(int3 qA, int3 qB, uint level, uint isInf)
{
    uint3 seed = uint3(qA) + uint3(qB) * 0x45D9F3Bu + level + isInf * 7u;
    uint3 h = vc_pcg3d(seed);
    uint fp = h.x ^ h.y ^ h.z;
    // Avoid sentinel values: 0 = empty, TOMBSTONE = deleted.
    if (fp == 0u || fp == VC_TOMBSTONE) fp = 1u;
    return fp;
}

// Double-hashing probe sequence. h2 forced odd for coprime with 2^n table.
uint vc_probe_slot(uint h1, uint fp, uint step)
{
    uint h2 = fp | 1u;
    return (h1 + step * h2) & _VCTableMask;
}

// ═══════════════════════════════════════════════════════════════════
// SAMPLE OPERATIONS
// ═══════════════════════════════════════════════════════════════════

// Unpack entry — vis in upper 16 bits, total in lower 16.
void vc_unpack(uint packed, out uint vis, out uint total)
{
    vis   = packed >> 16u;
    total = packed & 0xFFFFu;
}

// CAS loop to subtract 1/8 of both counters. Bounded attempts.
void vc_overflow_decay(uint slot)
{
    uint idx = slot * 2u + 1u;
    [loop] for (uint attempt = 0; attempt < 4u; attempt++)
    {
        uint oldVal = _VCTable[idx];
        uint vis, total;
        vc_unpack(oldVal, vis, total);
        if (total <= VC_OVERFLOW_TRIGGER)
            return; // another thread decayed first
        vis   -= vis   >> VC_OVERFLOW_SHIFT;
        total -= total >> VC_OVERFLOW_SHIFT;
        uint newVal = (vis << 16u) | total;
        uint prev;
        InterlockedCompareExchange(_VCTable[idx], oldVal, newVal, prev);
        if (prev == oldVal)
        {
#ifdef VC_STATS_DECAYS
            InterlockedAdd(_VCStats[VC_STAT_DECAYS], 1u);
#endif
            return;
        }
    }
}

// Add one sample. V=1 → delta=0x00010001, V=0 → delta=0x00000001.
void vc_add_sample(uint slot, bool visible)
{
    uint delta = visible ? 0x00010001u : 0x00000001u;
    uint prev;
    InterlockedAdd(_VCTable[slot * 2u + 1u], delta, prev);

    // Inline overflow decay: if total exceeds trigger, subtract 1/8.
    uint newTotal = ((prev & 0xFFFFu) + 1u);
    if (newTotal > VC_OVERFLOW_TRIGGER)
        vc_overflow_decay(slot);

    InterlockedAdd(_VCStats[VC_STAT_INSERTS], 1u);
}

// ═══════════════════════════════════════════════════════════════════
// FIND — probe sequence with fingerprint match
// ═══════════════════════════════════════════════════════════════════

VCFindResult vc_find(uint addr, uint fp)
{
    VCFindResult r;
    r.found = false;
    r.slot  = 0;
    r.mean  = 0.0;
    r.variance = 0.25; // worst case
    r.total = 0;

    [loop] for (uint step = 0; step < VC_MAX_PROBES; step++)
    {
        uint s = vc_probe_slot(addr, fp, step);
        uint storedFp = _VCTable[s * 2u];

        if (storedFp == 0u)
            return r; // empty → not in table (chain ends)

        if (storedFp == VC_TOMBSTONE)
            continue; // deleted → chain continues past here

        if (storedFp == fp)
        {
            uint packed = _VCTable[s * 2u + 1u];
            uint vis, total;
            vc_unpack(packed, vis, total);
            r.found = true;
            r.slot  = s;
            r.total = total;
            if (total > 0u)
            {
                r.mean     = (float)vis / (float)total;
                r.variance = r.mean * (1.0 - r.mean);
            }
            return r;
        }
#ifdef VC_STATS_PROBES
        InterlockedAdd(_VCStats[VC_STAT_PROBES], 1u);
#endif
    }
    return r; // probes exhausted, not found
}

// ═══════════════════════════════════════════════════════════════════
// INSERT — CAS fingerprint, add sample, pressure-scaled eviction
// ═══════════════════════════════════════════════════════════════════

void vc_insert_at_level(int3 qA, int3 qB, bool visible, uint level, uint isInf)
{
    uint addr = vc_hash_addr(qA, qB, level, isInf);
    uint fp   = vc_hash_fp  (qA, qB, level, isInf);

    uint firstTombstone = VC_MAX_PROBES; // sentinel: none found yet

    [loop] for (uint step = 0; step < VC_MAX_PROBES; step++)
    {
        uint s = vc_probe_slot(addr, fp, step);
        uint existingFp = _VCTable[s * 2u];

        // Remember first tombstone for potential reuse.
        if (existingFp == VC_TOMBSTONE && firstTombstone == VC_MAX_PROBES)
        {
            firstTombstone = step;
            continue; // keep probing — our entry might be further along
        }

        if (existingFp == fp)
        {
            // Found existing entry — add sample.
            vc_add_sample(s, visible);
            return;
        }

        if (existingFp == 0u)
        {
            // Empty slot. If we passed a tombstone, reclaim that instead
            // (earlier in chain = shorter future probes).
            if (firstTombstone < VC_MAX_PROBES)
            {
                uint ts = vc_probe_slot(addr, fp, firstTombstone);
                uint prev;
                InterlockedCompareExchange(_VCTable[ts * 2u], VC_TOMBSTONE, fp, prev);
                if (prev == VC_TOMBSTONE)
                {
                    _VCTable[ts * 2u + 1u] = 0u;
                    vc_add_sample(ts, visible);
                    return;
                }
                // Lost race on tombstone — fall through to claim this empty.
            }
            // Claim empty slot via CAS(0 → fp).
            uint prev;
            InterlockedCompareExchange(_VCTable[s * 2u], 0u, fp, prev);
            if (prev == 0u || prev == fp)
            {
                vc_add_sample(s, visible);
                return;
            }
            // Lost race — slot now occupied, continue probing.
            continue;
        }

        // Pressure-scaled eviction (steps >= VC_EVICT_PROTECT).
        // Threshold doubles per step → long chains self-heal.
        if (step >= VC_EVICT_PROTECT)
        {
            uint threshold = VC_BOOT_THRESHOLD << (step - VC_EVICT_PROTECT);
            uint packed = _VCTable[s * 2u + 1u];
            uint total  = packed & 0xFFFFu;
            if (total < threshold)
            {
                // Evict: overwrite fingerprint and reset counters.
                uint evictedFp;
                InterlockedExchange(_VCTable[s * 2u],      fp, evictedFp);
                InterlockedExchange(_VCTable[s * 2u + 1u], 0u, packed);
                vc_add_sample(s, visible);
                InterlockedAdd(_VCStats[VC_STAT_EVICTIONS], 1u);
                return;
            }
        }
#ifdef VC_STATS_PROBES
        InterlockedAdd(_VCStats[VC_STAT_PROBES], 1u);
#endif
    }

    // All probes exhausted — try tombstone if we found one.
    if (firstTombstone < VC_MAX_PROBES)
    {
        uint ts = vc_probe_slot(addr, fp, firstTombstone);
        uint prev;
        InterlockedCompareExchange(_VCTable[ts * 2u], VC_TOMBSTONE, fp, prev);
        if (prev == VC_TOMBSTONE)
        {
            _VCTable[ts * 2u + 1u] = 0u;
            vc_add_sample(ts, visible);
            return;
        }
    }
    // Sample lost. Correctness unaffected.
}

// ═══════════════════════════════════════════════════════════════════
// DISTANCE-GATED LOD
// ═══════════════════════════════════════════════════════════════════

// Returns (lo, hi) valid LOD range. lo > hi means no valid level.
// Cells are ordered L0=coarsest → L2=finest.
uint2 vc_dist_lod(float3 posA)
{
    float dist = distance(posA, _VCCameraPos.xyz);
    // World-space size of one pixel at this distance.
    float pixelSize = 2.0 * dist * _VCTanHalfFov / _VCScreenHeight;
    // Guard against zero/near-zero distance.
    pixelSize = max(pixelSize, 1e-8);

    float cellSizes[VC_NUM_LEVELS] = { _VCCellA.x, _VCCellA.y, _VCCellA.z };

    uint lo = VC_NUM_LEVELS; // sentinel: no valid level
    uint hi = 0;
    [unroll] for (uint l = 0; l < VC_NUM_LEVELS; l++)
    {
        float cellPx = cellSizes[l] / pixelSize;
        if (cellPx >= _VCMinPixels && cellPx <= _VCMaxPixels)
        {
            lo = min(lo, l);
            hi = l;
        }
    }
    return uint2(lo, hi);
}

// ═══════════════════════════════════════════════════════════════════
// LOOKUP — coarse-to-fine within distance-gated range
// ═══════════════════════════════════════════════════════════════════

struct VCLookup
{
    bool  found;
    float mean;
    float variance;
    uint  total;
    uint  lodLo;
    uint  lodHi;
};

VCLookup vc_lookup_internal(float3 posA, float3 endpointB,
                            uint isInf)
{
    VCLookup result;
    result.found    = false;
    result.mean     = 0.0;
    result.variance = 0.25;
    result.total    = 0;

#ifdef VC_STATS_QUERIES
    InterlockedAdd(_VCStats[VC_STAT_LOOKUPS], 1u);
#endif

    uint2 di = vc_dist_lod(posA);
    result.lodLo = di.x;
    result.lodHi = di.y;

    if (di.x > di.y)
    {
#ifdef VC_STATS_QUERIES
        InterlockedAdd(_VCStats[VC_STAT_MISSES], 1u);
#endif
        return result; // no valid LOD for this distance
    }

    float cellA[VC_NUM_LEVELS] = { _VCCellA.x, _VCCellA.y, _VCCellA.z };
    float cellB[VC_NUM_LEVELS] = { _VCCellB.x, _VCCellB.y, _VCCellB.z };
    float angR [VC_NUM_LEVELS] = { _VCAngularRes.x, _VCAngularRes.y, _VCAngularRes.z };

    [loop] for (uint lvl = di.x; lvl <= di.y; lvl++)
    {
        int3 qA = vc_quantize_pos(posA, cellA[lvl]);
        int3 qB = isInf ? vc_quantize_dir(endpointB, angR[lvl])
                        : vc_quantize_pos(endpointB, cellB[lvl]);

        uint addr = vc_hash_addr(qA, qB, lvl, isInf);
        uint fp   = vc_hash_fp  (qA, qB, lvl, isInf);

        VCFindResult f = vc_find(addr, fp);
        if (!f.found)
            break; // no entry at this level → stop

        if (f.total < VC_MIN_WEIGHT)
            break; // too few samples

        result.found    = true;
        result.mean     = f.mean;
        result.variance = f.variance;
        result.total    = f.total;

        if (f.variance < _VCVarThreshold)
            break; // converged, no need for finer level
    }

    if (!result.found)
#ifdef VC_STATS_QUERIES
        InterlockedAdd(_VCStats[VC_STAT_MISSES], 1u);
#endif

    return result;
}

// ═══════════════════════════════════════════════════════════════════
// INSERT dispatch — multi-level with variance gating
// ═══════════════════════════════════════════════════════════════════

void vc_record_internal(float3 posA, float3 endpointB,
                        bool visible, uint isInf)
{
    uint2 di = vc_dist_lod(posA);
    if (di.x > di.y) return;

    float cellA[VC_NUM_LEVELS] = { _VCCellA.x, _VCCellA.y, _VCCellA.z };
    float cellB[VC_NUM_LEVELS] = { _VCCellB.x, _VCCellB.y, _VCCellB.z };
    float angR [VC_NUM_LEVELS] = { _VCAngularRes.x, _VCAngularRes.y, _VCAngularRes.z };

    // Variance gate: read L0 to decide write depth.
    int3 qA0 = vc_quantize_pos(posA, cellA[di.x]);
    int3 qB0 = isInf ? vc_quantize_dir(endpointB, angR[di.x])
                      : vc_quantize_pos(endpointB, cellB[di.x]);
    uint addr0 = vc_hash_addr(qA0, qB0, di.x, isInf);
    uint fp0   = vc_hash_fp  (qA0, qB0, di.x, isInf);
    VCFindResult l0 = vc_find(addr0, fp0);

    uint vmax;
    if (!l0.found || l0.total < VC_BOOT_THRESHOLD)
        vmax = di.y; // bootstrap: write all levels
    else if (l0.variance > _VCVarThreshold)
        vmax = di.y; // shadow boundary: write all levels
    else
        vmax = di.x; // smooth region: coarsest only

    [loop] for (uint lvl = di.x; lvl <= min(di.y, vmax); lvl++)
    {
        int3 qA = (lvl == di.x) ? qA0 : vc_quantize_pos(posA, cellA[lvl]);
        int3 qB;
        if (lvl == di.x)
            qB = qB0;
        else
            qB = isInf ? vc_quantize_dir(endpointB, angR[lvl])
                       : vc_quantize_pos(endpointB, cellB[lvl]);

        vc_insert_at_level(qA, qB, visible, lvl, isInf);
    }
}

// ═══════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════

// ── Query: should I trace this shadow ray? ──────────────────────
// posA         = shading point
// posB         = light/secondary hit position (finite)
// contribution = BRDF * Le * G magnitude (for firefly-adaptive p_min)
// rng01        = caller-provided uniform random in [0,1)

VCShadowQuery VCQueryShadow(float3 posA, float3 posB,
                             float contribution, float rng01)
{
    VCShadowQuery q;
    VCLookup r = vc_lookup_internal(posA, posB, 0u);

    if (!r.found)
    {
        q.mean        = 0.0;
        q.variance    = 0.25;
        q.survivalP   = 1.0;
        q.shouldTrace = true;
        q.isMiss      = true;
        return q;
    }

    q.isMiss   = false;
    q.mean     = r.mean;
    q.variance = r.variance;

    float p = saturate(r.variance / _VCVarThreshold);
    float pFloor = saturate(contribution / _VCFireflyBudget);
    p = max(p, max(pFloor, _VCPMin));
    q.survivalP   = p;
    q.shouldTrace = (rng01 < p);

    return q;
}

// Infinite endpoint variant (IBL / directional light).
VCShadowQuery VCQueryShadowInf(float3 posA, float3 dirB,
                                float contribution, float rng01)
{
    VCShadowQuery q;
    VCLookup r = vc_lookup_internal(posA, dirB, 1u);

    if (!r.found)
    {
        q.mean        = 0.0;
        q.variance    = 0.25;
        q.survivalP   = 1.0;
        q.shouldTrace = true;
        q.isMiss      = true;
        return q;
    }

    q.isMiss   = false;
    q.mean     = r.mean;
    q.variance = r.variance;

    float p = saturate(r.variance / _VCVarThreshold);
    float pFloor = saturate(contribution / _VCFireflyBudget);
    p = max(p, max(pFloor, _VCPMin));
    q.survivalP   = p;
    q.shouldTrace = (rng01 < p);

    return q;
}

// ── Record: insert traced result into cache ─────────────────────
// Call only when shouldTrace was true OR on isMiss.

void VCRecordShadow(float3 posA, float3 posB, bool visible)
{
    vc_record_internal(posA, posB, visible, 0u);
}

void VCRecordShadowInf(float3 posA, float3 dirB, bool visible)
{
    vc_record_internal(posA, dirB, visible, 1u);
}

// ── Estimate: compute unbiased CV+RRR result ────────────────────
// Call after trace. Returns the visibility estimate to multiply
// with analytic lighting (BRDF × Le × G).
// WARNING: return value can be <0 or >1 (unbiased but high variance).
// Use VCEstimateClamped for a biased but bounded alternative.

float VCEstimate(VCShadowQuery q, bool tracedVisible)
{
    float V = tracedVisible ? 1.0 : 0.0;
    if (q.isMiss)
        return V;
    return q.mean + (V - q.mean) / q.survivalP;
}

// Biased safety net: clamp to [0,1]. Bias bounded by 1/survivalP
// per clamped sample. Prevents negative radiance and fireflies.
float VCEstimateClamped(VCShadowQuery q, bool tracedVisible)
{
    return saturate(VCEstimate(q, tracedVisible));
}

// ═══════════════════════════════════════════════════════════════════
// COMPUTE HELPERS — used by VisibilityCache.compute kernels
// ═══════════════════════════════════════════════════════════════════

void vc_clear_entry(uint slot)
{
    _VCTable[slot * 2u]     = 0u;
    _VCTable[slot * 2u + 1u] = 0u;
}

// Background decay: reduce counts by right-shifting _VCDecayShift bits.
// On reaching zero → write tombstone (preserves probe chains).
void vc_decay_entry(uint slot)
{
    // Skip empty and already-tombstoned slots.
    uint fp = _VCTable[slot * 2u];
    if (fp == 0u || fp == VC_TOMBSTONE) return;

    uint idx = slot * 2u + 1u;
    [loop] for (uint attempt = 0; attempt < 4u; attempt++)
    {
        uint oldVal = _VCTable[idx];
        if (oldVal == 0u) return;

        uint vis, total;
        vc_unpack(oldVal, vis, total);
        vis   -= vis   >> _VCDecayShift;
        total -= total >> _VCDecayShift;

        if (total == 0u)
        {
            // Decayed to zero → tombstone the slot (chain stays intact).
            uint prevFp;
            InterlockedExchange(_VCTable[slot * 2u], VC_TOMBSTONE, prevFp);
            InterlockedExchange(_VCTable[idx],       0u, oldVal);
            return;
        }

        uint newVal = (vis << 16u) | total;
        uint prev;
        InterlockedCompareExchange(_VCTable[idx], oldVal, newVal, prev);
        if (prev == oldVal)
            return; // success
    }
}

#endif // VISIBILITY_CACHE_HLSL

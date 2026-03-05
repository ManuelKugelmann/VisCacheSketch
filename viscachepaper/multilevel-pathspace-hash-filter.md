# Multilevel Path-Space Hash Filter

## Design Document — Implementation Reference

---

## 1. Problem Statement

Real-time path tracing produces noisy images due to low sample counts. Path-space filtering reduces noise by accumulating and sharing radiance samples across spatially and directionally similar shading points. The challenge is building a GPU-friendly data structure that:

- Stores filtered radiance at multiple resolutions
- Adapts resolution to local signal complexity (shadow boundaries need fine cells, diffuse walls need coarse)
- Supports massively parallel atomic writes from path tracing shaders
- Provides fast lookups with automatic level-of-detail selection
- Handles dynamic lighting via temporal decay

---

## 2. Architecture Overview

One flat hash table with open addressing. No trees, no heaps, no pointers. Each sample writes to multiple coupled LOD levels simultaneously. Read-time coarse-to-fine traversal with early termination selects the best level.

```
Sample (pos, dir, value)
        │
        ├──► L0 entry (coarse spatial, coarse directional)
        ├──► L1 entry (medium spatial, medium directional)
        └──► L2 entry (fine spatial, fine directional)

Lookup (pos, dir)
        │
        ├──► Try L0 → good enough? return
        ├──► Try L1 → good enough? return
        └──► Try L2 → return finest available
```

All levels coexist in the same flat buffer. No commitment to a single resolution per region — the read side picks the best available.

---

## 3. Data Structures

### 3.1 Entry

```hlsl
struct Entry {
    uint  fingerprint;   // collision detection, always full resolution
    float sum;           // accumulated weighted radiance
    float sum_sq;        // accumulated weighted radiance squared (for variance)
    float weight_sum;    // accumulated solid-angle-compensated weight (replaces integer count)
    uint  last_frame;    // timestamp for temporal decay
};
// 20 bytes per entry
```

**Why these fields:**
- `fingerprint`: sole authority for distinguishing entries that hash to the same slot. No stored keys — saves memory, fingerprint is sufficient given its width (32-bit fingerprint vs ~20-bit address space).
- `sum / weight_sum` = mean radiance. `sum_sq / weight_sum - mean²` = variance. Both computable from three atomically-updatable accumulators.
- `weight_sum` instead of integer `count`: enables solid-angle compensation for octahedral directional quantization (see §4.2). Parent `weight_sum` ≥ sum of children's `weight_sum` — the upper-bound property still holds.
- `last_frame`: enables temporal decay without touching every entry every frame.

### 3.2 LOD Configuration

```hlsl
struct LODConfig {
    uint spatial_log2;   // log2 of spatial grid resolution per axis
    uint dir_log2;       // log2 of directional grid resolution per axis (octahedral 2D)
};

// Coupled diagonal: spatial refines ~2x faster than directional
static const LODConfig lods[N_LEVELS] = {
    { 2, 2},   // L0: 4³ = 64 spatial cells,     4×4 = 16 dir bins
    { 5, 3},   // L1: 32³ = 32K spatial cells,   8×8 = 64 dir bins
    { 8, 4},   // L2: 256³ = 16M spatial cells, 16×16 = 256 dir bins
};

#define N_LEVELS  3
#define MAX_PROBE 4
```

**Why coupled diagonal:**
Spatial and directional signal frequency are physically correlated in most scenes. Shadow boundaries are sharp in both space and angle. Glossy reflections are localized in both. Diffuse interreflection is smooth in both. The main exception (directional lights on flat diffuse surfaces) is benign — the coupled LOD wastes a few directional bits at shadow boundaries but the cost is negligible.

Full Cartesian product (N_spatial × N_directional independent levels) would require 12+ writes per sample — impractical for GPU. Coupled diagonal gives 3 writes with the right physical tradeoffs.

**Why spatial leads:**
Spatial variation has more dynamic range (scenes span meters, directions are bounded to a hemisphere). Direction saturates earlier — beyond ~256 angular bins you exceed typical BRDF lobe resolution. The resolution ratios (spatial jumps 3 log2 steps per level, direction jumps 1) encode this asymmetry.

---

## 4. Addressing

### 4.1 Spatial Quantization

Direct `int3` quantization at each level's resolution. No Morton codes.

```hlsl
int3 quantize_spatial(float3 pos, float3 scene_min, float3 scene_extent, uint lvl) {
    float3 norm = (pos - scene_min) / scene_extent;  // [0,1]³
    uint res = 1 << lods[lvl].spatial_log2;
    return int3(floor(norm * res));
}
```

**Why no Morton codes:**
Morton codes provide two properties: (1) hierarchy via bit truncation, (2) spatial locality in 1D ordering. With LOD-in-hash, the hash function destroys locality (property 2). Hierarchy (property 1) is achieved trivially by quantizing at different cell sizes — power-of-2 resolution ratios mean a coarse cell exactly covers a block of fine cells. `floor(pos / large_cell)` naturally groups all `floor(pos / small_cell)` within it. No bit interleaving needed.

**Why cubic grid (not BCC/FCC/hex):**
Alternative lattices (BCC, FCC, hexagonal close-packed) offer more isotropic cell shapes and better sampling theorems. But:
- FCC/HCP don't subdivide cleanly into finer versions of themselves — multilevel hierarchy is messy
- Indexing requires non-orthogonal basis vectors — more complex hash keys
- The quantization error matters less than the statistical quality of aggregation — a slightly anisotropic cubic cell is handled fine by the variance/count logic

Simplicity wins.

### 4.2 Directional Quantization — Octahedral with Solid Angle Compensation

Octahedral mapping projects the sphere to a unit square, then uniformly subdivides:

```hlsl
float2 octahedral_map(float3 dir) {
    dir /= (abs(dir.x) + abs(dir.y) + abs(dir.z));
    float2 oct = dir.z >= 0 ? dir.xy : (1 - abs(dir.yx)) * sign(dir.xy);
    return oct * 0.5 + 0.5;  // [0,1]²
}

uint quantize_direction(float3 dir, uint lvl) {
    float2 oct = octahedral_map(dir);
    uint res = 1 << lods[lvl].dir_log2;
    uint2 grid = uint2(floor(oct * res));
    return grid.y * res + grid.x;
}
```

**Multilevel**: power-of-2 subdivision of the 2D grid. Each parent cell has 4 directional children. Natural hierarchy, no special indexing.

**Area distortion and compensation**: octahedral mapping has ~2:1 solid angle variation across cells. This is known and analytically compensatable. Each sample is weighted by the inverse of its cell's solid angle, derived from the Jacobian of the octahedral mapping:

```hlsl
float solid_angle_weight(float2 oct_uv) {
    float2 p = oct_uv * 2 - 1;  // [-1,1]²
    float denom = 1.0 + abs(p.x) + abs(p.y);
    return denom * denom;  // proportional to 1/solid_angle
}
```

This makes `weight_sum` represent effective uniform-solid-angle sample count. Equal-area statistics without needing HEALPix complexity.

**Why not HEALPix:**
HEALPix has native equal-area cells and a NESTED indexing scheme with bit-truncation hierarchy. But encoding a direction to a HEALPix pixel index involves `atan2`, conditionals, and ring/zone calculations — branchy and expensive on GPU. Octahedral + analytic compensation achieves the same statistical fairness with cheaper encoding.

**Why not cube map:**
~3:1 area distortion (worse than octahedral), face-edge discontinuities, and 6 disjoint 2D grids complicate the hash.

### 4.3 Hash Function

```hlsl
uint get_addr(float3 pos, float3 dir, uint lvl, uint table_size) {
    int3 s = quantize_spatial(pos, scene_min, scene_extent, lvl);
    uint d = quantize_direction(dir, lvl);
    return hash(s.x, s.y, s.z, d, lvl) % table_size;
}
```

LOD is baked into the hash — different levels produce different addresses for the same sample. Different levels of the same spatial region are independent entries scattered across the table. No parent-child pointer relationships.

### 4.4 Fingerprint

```hlsl
uint get_fp(float3 pos, float3 dir, uint lvl) {
    // Always quantize at finest level for fingerprint
    int3 s = quantize_spatial(pos, scene_min, scene_extent, N_LEVELS - 1);
    uint d = quantize_direction(dir, N_LEVELS - 1);
    return hash2(s.x, s.y, s.z, d, lvl);
}
```

**Always full resolution**, regardless of level. The address is level-dependent (coarse quantization), but the fingerprint uses finest-level quantization plus the level ID.

**Why full-resolution fingerprint:**
Two different fine-grained cells that map to the same coarse address must not collide in fingerprint. If the fingerprint also used coarse quantization, different L2 children sharing an L1 parent could have identical fingerprints when displaced into the same probe sequence — false matches, corrupted data.

The fingerprint is wider than the address space (32-bit vs ~20-bit), so collision probability is ~2⁻³² per probe step. In practice, collisions are never observed (confirmed by Binder 2019).

### 4.5 Addressing Strategy: LOD-in-Hash vs Structured Offsets

Two valid approaches were considered:

**LOD-in-hash** (chosen): each level hashes independently to a random table location.
```hlsl
addr_L0 = hash(cell_coarse, dir_coarse, 0) % table_size
addr_L1 = hash(cell_medium, dir_medium, 1) % table_size   // independent
addr_L2 = hash(cell_fine,   dir_fine,   2) % table_size   // independent
```

**Structured offsets**: child levels start probing near parent's address.
```hlsl
addr_L0 = hash(cell_coarse, dir_coarse) % table_size
addr_L1 = addr_L0 + deterministic_offset_from_subdivision_bits
addr_L2 = addr_L0 + larger_offset
// Then standard open-addressing probe from each start address
```

Both use the same open-addressing probe sequence from their start address. Both have the same load factor — no reserved slots, no wasted space. Both use probing.

| | Structured offsets | LOD-in-hash |
|---|---|---|
| Multi-level cache coherence | Good — probes start in same region | Poor — 3 random locations |
| Inter-level probe contamination | Possible — displaced L1 entry sits where L2 probes | Impossible — independent regions |
| Code complexity | Offset arithmetic | Just hash with different level parameter |
| Single-level lookup | Must compute base address first | Direct, one hash call |

**The tradeoff is close.** With early termination usually stopping at L0 or L1, the cache coherence benefit of structured offsets is real but exercised infrequently. The contamination risk is manageable at <60% load. LOD-in-hash was chosen for simplicity, but structured offsets are a viable alternative worth revisiting if cache performance is a bottleneck.

---

## 5. Collision Resolution

### 5.1 Open Addressing with Linear Probing

```hlsl
int find(uint fp, uint addr, uint table_size, StructuredBuffer<Entry> table) {
    for (uint step = 0; step < MAX_PROBE; step++) {
        uint slot = (addr + step) % table_size;
        if (table[slot].fingerprint == fp) return slot;   // found
        if (table[slot].fingerprint == 0)  return -1;     // empty = absent
    }
    return -1;  // probe limit exceeded
}
```

**Why open addressing (not chaining):**
- No pointer indirection — GPU-friendly sequential memory access
- Predictable probe pattern — bounded worst case (MAX_PROBE steps)
- Cache-friendly — linear probing reads contiguous memory
- No dynamic allocation — the table is a fixed-size buffer

**Why fingerprint-only (no stored keys):**
Storing full keys (int3 spatial + uint direction + uint level) would cost 20+ bytes per entry. The 32-bit fingerprint serves the same purpose with negligible false positive rate and saves memory.

**Why MAX_PROBE = 4:**
At 50-60% load factor, average probe length is ~1.5 for linear probing. MAX_PROBE = 4 covers >99.9% of lookups. Failed probes (entry not found) terminate early on empty slots.

---

## 6. Insert

```hlsl
void insert(float3 pos, float3 dir, float value,
            RWStructuredBuffer<Entry> table, uint table_size,
            uint min_level, uint frame) {

    // Solid angle compensation weight (level-independent)
    float2 oct_uv = octahedral_map(dir);
    float w = solid_angle_weight(oct_uv);

    for (uint lvl = min_level; lvl < N_LEVELS; lvl++) {
        // LOD-coupled jitter: magnitude proportional to cell size
        float cell_size = scene_extent / float(1 << lods[lvl].spatial_log2);
        float3 jittered = pos + (hash_noise(pos, frame) - 0.5) * cell_size;

        uint fp   = get_fp(pos, dir, lvl);   // always full resolution
        uint addr = get_addr(jittered, dir, lvl, table_size);

        for (uint step = 0; step < MAX_PROBE; step++) {
            uint slot = (addr + step) % table_size;
            uint existing = 0;
            InterlockedCompareExchange(table[slot].fingerprint, 0, fp, existing);
            if (existing == 0 || existing == fp) {
                InterlockedAdd_float(table[slot].sum, value * w);
                InterlockedAdd_float(table[slot].sum_sq, value * value * w);
                InterlockedAdd_float(table[slot].weight_sum, w);
                table[slot].last_frame = frame;
                break;
            }
        }
    }
}
```

### 6.1 Write-All-Levels

Every sample writes to all levels (or all above `min_level`). Parents accumulate everything their children accumulate, plus more (samples from other children). This guarantees:
- Parent `weight_sum` ≥ any child's `weight_sum` (upper bound property)
- Parent always exists if any child exists
- Read-time level selection without write-time commitment

**Why write-all (not Binder's single-level write):**
Binder picks one LOD at write time based on camera distance. If the choice is wrong, data is lost — you can't reconstruct a finer or coarser view from a single level. Write-all costs 3× the writes but gives strictly more flexibility at read time.

**Why write-all (not MrHash's refine-then-commit):**
MrHash starts fine, observes variance, then explicitly coarsens (deallocate fine block, allocate coarse block, downsample). This involves GPU memory management (heap alloc/dealloc) and is irreversible without re-splitting. Our approach avoids commitment entirely — all levels always exist, the read side picks.

MrHash's commit approach makes sense for TSDF where the surface converges after many frames. For stochastic radiance, the signal is noisier and view-dependent — deferring the decision is more robust.

### 6.2 LOD-Coupled Jitter

Jitter magnitude equals cell size at that level:

```hlsl
float cell_size = scene_extent / float(1 << lods[lvl].spatial_log2);
float3 jittered = pos + (hash_noise(pos, frame) - 0.5) * cell_size;
```

**Why jitter:**
Quantization creates hard cell boundaries. Samples near boundaries always hash to the same cell, creating discontinuities in the filtered result. Jitter randomizes which cell a boundary sample falls into, softening the transition over multiple frames.

**Why couple jitter to LOD:**
Large cells (coarse LOD) need large jitter to cover the boundary zone. Fine cells need small jitter to preserve spatial precision. Coupling jitter magnitude to cell size is self-consistent and requires no feedback from previous frames.

This follows Binder 2019's approach (jitter before quantize, scaled by cell size) but applied systematically across all levels during the write-all phase.

### 6.3 Solid Angle Compensation

```hlsl
float solid_angle_weight(float2 oct_uv) {
    float2 p = oct_uv * 2 - 1;
    float denom = 1.0 + abs(p.x) + abs(p.y);
    return denom * denom;
}
```

Each sample is weighted by the inverse of its directional cell's solid angle. This compensates for the octahedral mapping's ~2:1 area distortion, making `weight_sum` represent effective equal-solid-angle sample count.

**Impact on statistics:**
- `mean = sum / weight_sum` — solid-angle-fair average
- `variance = sum_sq / weight_sum - mean²` — solid-angle-fair variance
- Children-starved heuristic uses `weight_sum` — still valid, parent ≥ sum of children

**Cost:** `weight_sum` is a float instead of integer `count`, requiring a float atomic. But `sum` and `sum_sq` already use float atomics, so no additional cost class.

### 6.4 Atomic Accumulation

`sum`, `sum_sq`, and `weight_sum` are updated with independent atomics. No dependencies between fields — all three can be written concurrently by different threads hitting the same cell. The `InterlockedCompareExchange` on the fingerprint handles the create-or-update decision atomically.

```hlsl
// Float atomic via CAS loop (or native float atomics on SM 6.6+ / RDNA3+)
void InterlockedAdd_float(RWStructuredBuffer<uint> buf, uint idx, float val) {
    uint expected, replaced;
    do {
        expected = buf[idx];
        replaced = asuint(asfloat(expected) + val);
    } while (expected != replaced &&
             InterlockedCompareExchange(buf[idx], expected, replaced, replaced));
}
```

**Why not Welford's algorithm:**
Welford requires reading the old mean before computing the update, then writing the new mean — a read-modify-write dependency that serializes concurrent writes. Our independent-accumulator approach allows fully parallel updates at the cost of slightly less numerical stability (catastrophic cancellation when variance << mean²). For radiance values, this is acceptable — variance is typically significant relative to mean.

### 6.5 min_level and Capacity-Driven Pruning

Under memory pressure, skip fine writes:

```hlsl
uint min_level = 0;
if (load_factor > 0.5) min_level = max(min_level, distance_based_min(dist));
if (load_factor > 0.7) min_level = 1;
if (load_factor > 0.85) min_level = N_LEVELS - 2;
```

**Why:**
Write-all costs 3 entries per sample. At high table occupancy, this accelerates saturation. Progressively skipping fine levels reduces write pressure while preserving coarse fallback data. The lookup code is unchanged — it naturally falls back to whatever levels are populated.

This combines Binder's distance-based LOD (far objects get coarser representation) with MrHash's capacity-driven adaptation (85% threshold triggers action), but without MrHash's heavyweight split/merge operations.

---

## 7. Lookup

```hlsl
LookupResult lookup(float3 pos, float3 dir,
                    StructuredBuffer<Entry> table, uint table_size,
                    float var_threshold, float min_weight) {

    LookupResult best = MISS;

    for (uint lvl = 0; lvl < N_LEVELS; lvl++) {
        uint fp   = get_fp(pos, dir, lvl);
        uint addr = get_addr(pos, dir, lvl, table_size);

        int slot = find(fp, addr, table_size, table);
        if (slot < 0) break;  // no entry at this level → no finer levels either

        Entry e = table[slot];
        best = make_result(e, lvl);

        // Early termination: variance check
        float mean = e.sum / e.weight_sum;
        float var  = e.sum_sq / e.weight_sum - mean * mean;
        if (var < var_threshold) break;  // signal is clean at this level

        // Early termination: children would be starved
        uint s_children = 1 << ((lods[lvl+1].spatial_log2 - lods[lvl].spatial_log2) * 3);
        uint d_children = 1 << ((lods[lvl+1].dir_log2     - lods[lvl].dir_log2)     * 2);
        float children_factor = float(s_children * d_children);
        if (e.weight_sum < min_weight * children_factor) break;
    }
    return best;
}
```

### 7.1 Coarse-to-Fine with Early Termination

Start at L0 (coarsest). If variance is low, the signal is spatially/directionally uniform at this scale — no need to refine. If variance is high but weight_sum is too low, children won't have enough samples to be reliable.

**Key insight: parent weight_sum bounds children.** If L0 has weight_sum 100 and the next level subdivides into `children_factor` children, each child gets `~100/children_factor` weight on average. Below `min_weight`, the per-child estimate is dominated by noise. Refining would make things worse.

The sweet spot for refinement: **high variance AND high weight_sum at parent.** This indicates a genuine signal boundary (e.g., shadow edge) where children on each side will be individually clean (consistently lit or consistently shadowed) even though the parent mixes both.

### 7.2 Optional: Confidence-Weighted Blending

Instead of hard level switching, blend adjacent levels weighted by confidence:

```hlsl
LookupResult result = { 0, 0 };
float total_confidence = 0;

for (uint lvl = 0; lvl < N_LEVELS; lvl++) {
    int slot = find(fp[lvl], addr[lvl], table_size, table);
    if (slot < 0) break;

    Entry e = table[slot];
    float mean = e.sum / e.weight_sum;
    float var  = e.sum_sq / e.weight_sum - mean * mean;
    float confidence = e.weight_sum / (1.0 + var * var_sensitivity);

    result.value += mean * confidence;
    total_confidence += confidence;

    if (var < var_threshold && e.weight_sum > min_weight) break;
}

result.value /= max(total_confidence, 1e-6);
```

**Why blending:**
Avoids popping artifacts when a cell transitions between levels across frames. Smooth transitions both within levels (via jitter) and between levels (via blending).

---

## 8. Temporal Decay

### 8.1 Periodic Halving

```hlsl
[numthreads(256,1,1)]
void DecayPass(uint id : SV_DispatchThreadID) {
    if (table[id].fingerprint == 0) return;

    table[id].sum        *= 0.5;
    table[id].sum_sq     *= 0.5;
    table[id].weight_sum *= 0.5;

    if (table[id].weight_sum < eviction_threshold)
        table[id].fingerprint = 0;  // evict stale entry
}
```

Run every N frames (tunable). One parallel pass over the entire table.

**Why halving works:**
- `mean = sum / weight_sum` is invariant under uniform scaling
- `variance = sum_sq / weight_sum - mean²` is also invariant (both terms scale identically)
- Old data's influence decreases geometrically: after K halvings, original contribution is 2⁻ᴷ
- Entries that stop receiving samples naturally decay and get evicted
- New samples in active areas dominate quickly (fresh data is full-weight, old data is halved)

**Why not exponential decay on values:**
Applying `value *= alpha` every frame requires touching every entry every frame. Halving every N frames is cheaper and achieves the same geometric decay.

**Why not frame-age eviction only:**
Eviction (`if (frame - last_frame > max_age) → delete`) loses accumulated statistics abruptly. Halving degrades gracefully — a stale entry with weight_sum 1000 becomes 500, then 250, still useful as a coarse estimate until it naturally evicts.

### 8.2 Optional: Between-Frame Statistics Merge

For higher numerical stability at very low variance, separate frame accumulators from running statistics:

```hlsl
[numthreads(256,1,1)]
void MergeFrameStats(uint id : SV_DispatchThreadID) {
    Entry e = table[id];
    if (e.fingerprint == 0 || e.frame_weight == 0) return;

    // Welford-style merge of this frame's batch
    float frame_mean = e.frame_sum / e.frame_weight;
    float alpha = min(0.1, e.frame_weight / (e.total_weight + e.frame_weight));

    e.running_mean = lerp(e.running_mean, frame_mean, alpha);
    e.total_weight += e.frame_weight;

    // Reset frame accumulators
    e.frame_sum = e.frame_sum_sq = 0;
    e.frame_weight = 0;

    table[id] = e;
}
```

**When to use:** Only if variance precision matters near zero (e.g., perfectly flat diffuse surfaces). For most real-time applications, the simpler `sum/sum_sq/weight_sum` approach is sufficient.

---

## 9. Application: Control Variate with Variance-Driven Russian Roulette

The hash filter naturally serves as a control variate for direct lighting evaluation at eye-ray hits. The cached mean provides a low-variance baseline; only the residual needs to be estimated via ray tracing, and the stored variance gates whether to trace at all.

### 9.1 Control Variate Formulation

The cached mean μ = sum/weight_sum at the lookup cell is the control variate. The estimator is:

```
L_cv = μ + (L_sample − μ)
```

This is an unbiased β=1 control variate with known expectation. The residual `L_sample − μ` has variance Var(L) + Var(μ) − 2·Cov(L, μ), which is much smaller than Var(L) when the cache is accurate — same cell, high correlation by construction.

### 9.2 Variance-Driven Russian Roulette on the Residual

The stored σ² directly gates whether to trace direct lighting at all:

```hlsl
LookupResult r = lookup(pos, dir, table, table_size, var_threshold, min_weight);

if (r.level == MISS) {
    // Cold start: no cache, must trace
    float L_traced = trace_direct_lighting(hit);
    insert(pos, dir, L_traced, table, table_size, 0, frame);
    result = L_traced;
} else {
    float mu = r.mean;
    float sigma2 = r.variance;

    // Survival probability proportional to variance
    float p_survive = clamp(sigma2 / tau_rr, P_MIN, 1.0);

    if (random() < p_survive) {
        float L_traced = trace_direct_lighting(hit);
        float residual = (L_traced - mu) / p_survive;  // RR-weighted
        result = mu + residual;
        // Feed back into cache — only traced values
        insert(pos, dir, L_traced, table, table_size, 0, frame);
    } else {
        result = mu;  // Trust the cache
        // No insert — didn't trace, nothing to contribute
    }
}
```

**Unbiased:** Russian roulette with p > 0 preserves expectation. The 1/p_survive weighting on the residual ensures E[result] = E[L]. The minimum survival probability P_MIN guarantees eventual correction even when the cache is stale.

### 9.3 Self-Regulating Feedback Loop

The system forms a closed-loop controller:

1. **Low σ²** → high kill probability → fewer traces → compute saved on smooth regions
2. **High σ²** → always trace → residuals update cache → σ² drops as estimates converge → kill probability rises
3. **Lighting change** → traced values diverge from cache → σ² increases (new samples disagree with old mean) → more traces allocated → cache re-converges

Shadow boundaries get hammered with traces until the fine-level cells on each side individually converge (one side consistently lit, the other consistently shadowed), then RR kicks in and suppresses further tracing.

### 9.4 Interaction with Coarse-to-Fine Lookup

The LOD selection integrates directly with the RR decision:

- **L0 low variance** → confident coarse estimate → aggressive RR, almost never trace
- **L0 high variance, L2 low variance** → shadow boundary resolved at fine level → use L2 mean, moderate RR based on L2's (lower) variance
- **All levels high variance** → new/changing region → always trace, bootstrap the cache

The variance used for the RR gate is the variance at the *selected* level (the level where early termination stopped), not necessarily L0's variance. This means the system naturally allocates trace budget proportionally to the local signal complexity at the appropriate resolution.

### 9.5 Correctness Considerations

**Only traced values are inserted.** When RR kills a trace and returns μ, the cached mean is *not* re-inserted into the table. Inserting μ would create a feedback loop where the cache reinforces itself, biasing σ² toward zero and permanently suppressing traces. Only actual traced radiance values enter the cache, preserving it as an unbiased estimator.

**Cold start:** First frame has no cache entries → all lookups miss → p_survive = 1.0 → trace everything → cache fills. Second frame already benefits from cached means. Warm-up cost is exactly one frame.

**Minimum survival probability P_MIN:** Without P_MIN, a stale cache with artificially low variance (from before a lighting change) would suppress traces indefinitely. P_MIN ≈ 0.05–0.1 ensures at least some traces always flow through, detecting changes. The temporal decay halving reinforces this — old confidence decays, weight_sum drops, variance estimate becomes less reliable, p_survive rises toward 1.0.

**Numerical stability of the residual:** When μ is large and σ² is small, the residual L_traced − μ can suffer cancellation. Since it is used additively (μ + residual/p), not as a ratio of small quantities, this is benign.

### 9.6 Configuration

```hlsl
#define TAU_RR   0.01   // variance threshold for RR gating (same scale as VAR_THRESHOLD)
#define P_MIN    0.05   // minimum survival probability (5% of pixels always trace)
```

TAU_RR can be set equal to VAR_THRESHOLD for consistency: the same variance threshold that stops coarse-to-fine refinement also triggers aggressive RR. Alternatively, TAU_RR can be set lower than VAR_THRESHOLD to allow moderate RR even when the lookup hasn't fully converged.

---

## 10. Table Sizing

```hlsl
// Budget: N_LEVELS entries per unique spatial-directional cell
// Load factor: keep below 60% for open addressing performance
uint expected_unique_cells = pixel_count * avg_bounces * unique_cell_ratio;
uint table_size = N_LEVELS * expected_unique_cells * 2;  // 2x for ~50% load
```

For a 1080p frame with 2 bounces and ~30% unique cell ratio:
- ~1920×1080 × 2 × 0.3 ≈ 1.2M unique cells
- × 3 levels × 2 (load factor) ≈ 7.5M entries
- × 20 bytes ≈ 150MB

Adjust base spatial resolution (`spatial_log2` at finest level) to control memory vs quality tradeoff.

---

## 11. GPU Implementation Notes

### 10.1 Float Atomics

```hlsl
// Float atomic via CAS loop (fallback for hardware without native float atomics)
void InterlockedAdd_float(RWStructuredBuffer<uint> buf, uint idx, float val) {
    uint expected, replaced;
    do {
        expected = buf[idx];
        replaced = asuint(asfloat(expected) + val);
    } while (expected != replaced &&
             InterlockedCompareExchange(buf[idx], expected, replaced, replaced));
}
// On SM 6.6+ / RDNA3+: use native InterlockedAddF32
```

### 10.2 Warp Divergence

The coarse-to-fine lookup has variable iteration count (1-3 levels) depending on early termination. In practice, adjacent pixels tend to terminate at the same level (smooth regions all stop at L0, boundary regions all go to L2), so warp divergence is limited.

### 10.3 Memory Access Pattern

LOD-in-hash scatters levels across the table. A single lookup does 1-3 random reads. This is worse than structured offsets for cache coherence, but:
- L0 often suffices (1 read, same as any hash lookup)
- GPU latency hiding via warp scheduling absorbs the random access cost
- The simplicity benefit (no offset arithmetic, no inter-level interference) outweighs the cache cost

### 10.4 Hash Functions

```hlsl
// Address hash: Teschner-style spatial hash (standard in graphics)
uint hash(int x, int y, int z, uint d, uint lvl) {
    return uint(x) * 73856093u ^ uint(y) * 19349669u ^
           uint(z) * 83492791u ^ d * 2246822519u ^ lvl * 3266489917u;
}

// Fingerprint hash: higher quality, more avalanche
uint hash2(int x, int y, int z, uint d, uint lvl) {
    uint h = uint(x) * 2654435761u;  // Knuth multiplicative
    h ^= uint(y) * 2246822519u;
    h ^= uint(z) * 3266489917u;
    h ^= d * 668265263u;
    h ^= lvl * 374761393u;
    h ^= h >> 16;
    h *= 0x45d9f3bu;
    h ^= h >> 16;
    return h == 0 ? 1 : h;  // reserve 0 as empty sentinel
}
```

Fingerprint hash must be higher quality than address hash (more avalanche) because it's the sole collision detector. Address hash just needs reasonable distribution.

---

## 12. Prior Art and Differentiation

### Binder 2019 — Path Space Filtering

- Fingerprint-based collision detection in spatial hash (we adopt this)
- Jitter before quantization, scaled by cell size (we adopt, extend to all levels)
- Single LOD per sample chosen at write time by camera distance
- **We extend:** write all levels, read-time selection, coupled spatial-directional LOD

### Gautron 2021 — Ray Tracing Gems 2

- LOD index in hash function (we adopt this principle)
- Normal folded into address hash
- Discusses rehashing vs linear probing tradeoffs
- **We extend:** variance/weight-driven early termination, temporal decay, coupled LOD

### MrHash 2025 — Variance-Adaptive Voxel Hashing

- Variance-driven adaptation in flat hash table (parallel insight, different domain — TSDF)
- Welford's algorithm for online variance
- Capacity-driven streaming at 85% occupancy
- Single level per region, explicit coarsen/refine transitions via heap reallocation
- **We extend:** simultaneous multi-level storage, no commitment, no heap management, temporal decay

### Instant-NGP 2022 — Multi-Resolution Hash Encoding

- Multiple resolution levels in hash tables, write all levels
- Neural network combines level information via concatenation + MLP
- **We replace:** neural combination with statistical early termination (no MLP, no training)

### Key Novel Contributions

1. **Write-all + read-time coarse-to-fine selection** — vs Binder's write-one, MrHash's refine-then-commit, NGP's neural combination
2. **Weight-as-upper-bound reasoning** — parent weight_sum predicts child starvation, enabling principled early termination
3. **Coupled spatial-directional LOD** — single LOD index controls both axes at physically motivated rates, avoiding Cartesian product explosion
4. **LOD-coupled jitter** — cell-proportional jitter at every level, no feedback needed
5. **Capacity-driven level pruning** — graceful degradation without explicit split/merge
6. **Full-resolution fingerprint across all levels** — solves cross-level collision in shared table
7. **Temporal decay via halving** — preserves variance ratios, cheap, naturally evicts stale data
8. **Octahedral solid angle compensation** — analytic weighting corrects area distortion, avoids need for equal-area projections like HEALPix
9. **Control variate with variance-driven Russian roulette** — cached mean as control variate, stored variance gates trace probability, self-regulating feedback loop

---

## 13. Configuration Defaults

```hlsl
#define N_LEVELS            3
#define MAX_PROBE           4
#define VAR_THRESHOLD       0.01   // relative to signal range, tune per use case
#define MIN_WEIGHT          4.0    // minimum useful effective sample weight per cell
#define DECAY_INTERVAL      30     // frames between halving passes
#define EVICTION_THRESHOLD  0.5    // minimum weight_sum before entry is evicted
#define LOAD_FACTOR_WARN    0.5    // start distance-based pruning
#define LOAD_FACTOR_CRIT    0.85   // aggressive pruning
#define TAU_RR              0.01   // variance threshold for RR gating
#define P_MIN               0.05   // minimum survival probability

static const LODConfig lods[N_LEVELS] = {
    { 2, 2},   // L0: 4³ spatial, 4×4 directional
    { 5, 3},   // L1: 32³ spatial, 8×8 directional
    { 8, 4},   // L2: 256³ spatial, 16×16 directional
};
```

---

## 14. Integration Checklist

1. **Allocate** flat `RWStructuredBuffer<Entry>` of `table_size` entries, zero-initialized (fingerprint = 0 means empty)
2. **On each eye-ray hit:** call `lookup()` to get cached mean μ and variance σ²
3. **RR decision:** compute p_survive = clamp(σ² / TAU_RR, P_MIN, 1.0); if random < p_survive, trace direct lighting and compute result = μ + (L_traced − μ) / p_survive; otherwise result = μ
4. **On each traced sample:** call `insert()` with the actual traced radiance value (never insert the cached mean)
5. **Every DECAY_INTERVAL frames:** dispatch `DecayPass` over entire table
6. **Monitor load factor:** count non-zero fingerprints, adjust `min_level` threshold
7. **Tune:** `spatial_log2` at finest level for spatial resolution, `VAR_THRESHOLD` / `TAU_RR` for quality vs compute, `P_MIN` for change detection responsiveness

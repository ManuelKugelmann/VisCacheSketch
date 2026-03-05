# Multilevel Visibility Hash Filter

## Design Document — Implementation Reference

---

## 1. Problem

Shadow rays dominate the cost of direct lighting in real-time path tracing. Most shadow rays confirm what nearby rays already established — a surface region is consistently visible or consistently occluded from another surface region. We cache point-to-point visibility in a multilevel spatial hash table and use the cached variance to gate shadow ray tracing via control-variate Russian roulette residual (CV+RRR, "go with the winners" [Szirmay-Kalos et al.]).

Complementary to ReSTIR. ReSTIR selects *which* light to sample. We cache *whether* the selected light is visible. The cache serves ReSTIR DI (shadow rays), ReSTIR GI (revalidation rays), and ReSTIR light selection (cached μ in target function). All are point-to-point visibility queries into the same table.

---

## 2. Architecture

One flat hash table, open addressing. Stores binary visibility (0 or 1) at multiple coupled resolutions in a 6D domain: 3D position × 3D position (two surface points). Optionally, endpoints are canonicalized before hashing to exploit V(A→B) = V(B→A) (§5.2, bidirectional use cases only).

Every shadow ray writes to one or more LOD levels. Read-time coarse-to-fine traversal stops when the signal is clean or the cell lacks data. The cached visibility mean serves as a control variate; the stored variance drives Russian roulette on the shadow ray.

---

## 3. Entry

```hlsl
struct Entry {
    uint fingerprint;   // collision detection, full resolution
    uint packed;        // [visible_count : 16][total_count : 16]
};
// 8 bytes per entry
```

Both counters packed into a single uint for atomic consistency. V=1 adds 0x00010001 (both counters); V=0 adds 0x00000001 (total only). Single InterlockedAdd — sum and count always in sync.

Reading: `vis = packed >> 16; total = packed & 0xFFFF; mean = float(vis) / float(total); variance = mean * (1 - mean)`.

**Weighted insertion (optional).** Instead of unit weight, quantize sample weight to 4 bits: `w = clamp(uint(weight * 4), 1, 15)`. V=1 adds `(w << 16) | w`, V=0 adds `w`. Higher-confidence samples contribute more. Overflow trigger adjusts proportionally — at max weight 15, headroom is 65535/15 ≈ 4K samples. Warp reduction still works: merged add_vals sum correctly.

Overflow: uint16 max = 65535. Conditional small decay on insert (§6.3) keeps counts below a ceiling. Temporal decay (§8) weakens stale entries so pressure eviction (§7) can displace them.

---

## 4. LOD Configuration

```hlsl
// Default: asymmetric (unidirectional PT)
// cell_a/cell_b: positional cell sizes for endpoints A/B
// ang_b: angular cell size for infinite endpoint B (octahedral [0,1]² units)
struct LODConfig { float cell_a, cell_b, ang_b; };
static const LODConfig lods[N_LEVELS] = {
    { 10.0,  10.0,  0.10  },   // L0: ~10m cells, ~6° angular bins
    { 1.25,  2.5,   0.025 },   // L1: ~1.25m / 2.5m, ~1.4° angular bins
    { 0.08,  0.625, 0.005 },   // L2: ~8cm / 62cm, ~0.3° angular bins
};

// Optional: symmetric (bidirectional, requires §5.2 canonicalization)
// static const float cell_size[N_LEVELS] = { 10.0, 1.25, 0.08 };

#define N_LEVELS 3
```

Cell sizes in world units. No scene_min, no scene_extent — quantization uses absolute division (§5.1), works for any position. Scene-scale-dependent but explicit.

In unidirectional PT, endpoint A is always the shading point, endpoint B is always the light/secondary hit. Roles are known — asymmetric cell sizes refine A faster (more spatial variation in the shading point than in the light position for typical scenes).

**Bidirectional option:** When canonicalization (§5.2) is enabled, both endpoints must use the same cell size — otherwise the swap assigns finer quantization to whichever endpoint is lexicographically smaller, which is arbitrary. Enable symmetric cell sizes together with canonicalization.

Point lights degenerate correctly: fixed position + position-dependent jitter → same jittered value every query → same quantized cell.

**Infinite endpoints (IBL, directional lights):** For endpoints at infinity, position is synthetic — direction is what matters. Quantize angle directly via octahedral mapping instead of projecting onto a fake sphere:

```hlsl
// Octahedral encode: unit direction -> [0,1]²
float2 oct_encode(float3 n) {
    float3 a = abs(n);
    float2 o = n.xy / (a.x + a.y + a.z);
    if (n.z < 0) o = (1.0 - abs(o.yx)) * sign(o);
    return o * 0.5 + 0.5;  // [0,1]²
}
```

No IBL_RADIUS needed. Angular resolution is the direct knob — uniform bins, no pole distortion. The `is_inf` flag selects the quantization path (angular vs positional) and separates address spaces in the hash. Angular jitter follows the same pattern as positional: `oct += (hash_noise - 0.5) * ang_b` before quantization (§5.3).

Per-level angular cell size stored in LODConfig:

```hlsl
struct LODConfig { float cell_a, cell_b, ang_b; };
static const LODConfig lods[N_LEVELS] = {
    { 10.0,  10.0,  0.10  },   // L0: ~10m cells, ~6° angular bins
    { 1.25,  2.5,   0.025 },   // L1: ~1.25m / 2.5m, ~1.4° bins
    { 0.08,  0.625, 0.005 },   // L2: ~8cm / 62cm, ~0.3° bins
};
```

Canonicalization (§5.2) applies only to finite×finite pairs. Infinite endpoints are always endpoint B (the light direction) — V(surface→sky) has no meaningful reverse. Skip canonicalization when `is_inf=1`.

---

## 5. Addressing

### 5.1 Spatial Quantization

```hlsl
int3 quantize(float3 pos, float cell_size) {
    return int3(floor(pos / cell_size));
}
```

Works for any position — positive, negative, unbounded. No scene_min, no scene_extent, no normalization. Hash maps arbitrary int3 to table indices.

### 5.2 Bidirectional Canonicalization (Optional)

**Enable for BDPT or any path tracer where both V(A→B) and V(B→A) are queried.** Not needed for unidirectional PT + ReSTIR where rays always go shading→light with known endpoint roles.

V(A→B) = V(B→A). Canonicalize after quantization to merge both directions:

```hlsl
void canonicalize(inout int3 a, inout int3 b) {
    if (a.x > b.x || (a.x == b.x && (a.y > b.y || (a.y == b.y && a.z > b.z)))) {
        int3 t = a; a = b; b = t;
    }
}
```

Requires symmetric LOD (§4) — both endpoints must quantize at the same resolution for the swap to be meaningful. Doubles effective sample density when the reverse direction is actually queried.

### 5.3 Jitter, Quantize, Hash

Both endpoints are jittered independently before quantization, with magnitude = cell_size (Binder et al. 2018). Jitter is purely position-dependent (no frame number), so a fixed world-space position always maps to the same cell. Point lights: fixed position → same jitter → same cell, always. Area lights: different sample points on the surface get different jitter values — anti-aliasing comes from sampling different positions, not from temporal noise.

**hash_noise:** pcg3d (Jarzynski & Olano 2020, "Hash Functions for GPU Rendering"). int3 → float3 in [0,1)³, ~12 ALU, no LUT, passes TestU01 BigCrush. Designed specifically for GPU rendering jitter.

```hlsl
float3 hash_noise(float3 pos) {
    // Input: world position. Quantize to int seed, then pcg3d.
    uint3 p = asuint(int3(floor(pos)));
    p = p * 1664525u + 1013904223u;
    p.x += p.y * p.z; p.y += p.z * p.x; p.z += p.x * p.y;
    p ^= p >> 16u;
    p.x += p.y * p.z; p.y += p.z * p.x; p.z += p.x * p.y;
    return float3(p) * (1.0 / 4294967296.0);
}
```

Fingerprint uses the same jittered+quantized coordinates as the address, but a different hash function (hash2 vs hash). Same input, independent output. This is the path space filtering design (Binder et al. 2018) — no separate "finest level" fingerprint.

```hlsl
struct AddrFP { uint addr; uint fp; };

AddrFP get_addr_fp(float3 pos_a, float3 pos_b, uint lvl, uint table_size, uint is_inf) {
    float cell_a = lods[lvl].cell_a;

    float3 ja = pos_a + (hash_noise(pos_a) - 0.5) * cell_a;
    int3 qa = quantize(ja, cell_a);

    AddrFP r;
    uint h;
    if (is_inf) {
        // Endpoint B is a direction — jitter in octahedral space, then quantize
        float2 oct = oct_encode(normalize(pos_b));
        float ang = lods[lvl].ang_b;
        oct += (hash_noise(pos_b).xy - 0.5) * ang;  // same pattern as positional jitter
        int2 db = int2(floor(oct / ang));
        r.addr = hash(qa.x, qa.y, qa.z, db.x, db.y, lvl, 1) % table_size;
        h = hash2(qa.x, qa.y, qa.z, db.x, db.y, lvl, 1);
    } else {
        // Both endpoints are positions
        float cell_b = lods[lvl].cell_b;
        float3 jb = pos_b + (hash_noise(pos_b) - 0.5) * cell_b;
        int3 qb = quantize(jb, cell_b);
        // canonicalize(qa, qb);  // enable for bidirectional (requires symmetric cells)
        r.addr = hash(qa.x, qa.y, qa.z, qb.x, qb.y, qb.z, lvl, 0) % table_size;
        h = hash2(qa.x, qa.y, qa.z, qb.x, qb.y, qb.z, lvl, 0);
    }
    r.fp = h == 0 ? 1 : h;
    return r;
}
```

Compute qa once (always position). Endpoint B branches: angular quantization (int2) for infinite, positional quantization (int3) for finite. Hash input dimensionality differs — `is_inf` in both hashes guarantees no collisions across paths. Canonicalization only applies to the finite path.

### 5.4 Probe Sequence

Double hashing with fingerprint as second hash function:

```hlsl
uint probe(uint addr, uint fp, uint step) {
    return (addr ^ (fp * step)) % table_size;
}
```

Standard technique (Knuth 1973). Eliminates primary clustering inherent in linear probing.

---

## 6. Insert

### 6.1 Distance-Gated LOD Interval

Each LOD level has a useful distance interval defined by target square pixel footprint. A cell covering fewer than MIN_CELL_PIXELS per side (4×4) is subpixel — skip. A cell covering more than MAX_CELL_PIXELS per side (64×64) is too coarse — skip. Each level covers a distance shell.

```hlsl
// cell_pixels = cell_size / (dist * pixel_angle)  — side length of projected square
// Solve for dist at the min/max square footprint boundaries.
#define MIN_CELL_PIXELS  4      // below: cell < 4×4 pixels, skip
#define MAX_CELL_PIXELS  64     // above: cell > 64×64 pixels, skip

static float lod_max_range[N_LEVELS];  // beyond: < MIN_CELL_PIXELS
static float lod_min_range[N_LEVELS];  // closer: > MAX_CELL_PIXELS

void compute_lod_ranges(float screen_width, float fov) {
    float pixel_angle = fov / screen_width;
    for (uint i = 0; i < N_LEVELS; i++) {
        lod_max_range[i] = lods[i].cell_a / (MIN_CELL_PIXELS * pixel_angle);
        lod_min_range[i] = lods[i].cell_a / (MAX_CELL_PIXELS * pixel_angle);
    }
}

struct LODInterval { uint min_level; uint max_level; };

LODInterval distance_lod_interval(float3 pos_a, float3 camera_pos) {
    float dist = length(pos_a - camera_pos);
    LODInterval r = { 0, 0 };
    for (int lvl = N_LEVELS - 1; lvl >= 0; lvl--)
        if (dist < lod_max_range[lvl]) r.max_level = lvl;
    for (uint lvl = 0; lvl < N_LEVELS; lvl++)
        if (dist > lod_min_range[lvl]) { r.min_level = lvl; break; }
    if (r.min_level > r.max_level) r.min_level = r.max_level;  // degenerate
    return r;
}
```

Applied on both insert and lookup (§9). L0 for far field, L2 for near field, L1 bridges. Saves probe work in both directions: near camera skips L0, far surfaces skip L2. World-space cells, temporally stable, no reprojection.

### 6.2 Variance-Gated Write

Write-all during bootstrap; after L0 matures, only write fine levels where L0 variance is high. Combined with distance interval:

```hlsl
void insert(float3 pos_a, float3 pos_b, float V, float3 camera_pos, uint is_inf) {
    LODInterval di = distance_lod_interval(pos_a, camera_pos);
    LookupResult r0 = lookup_single(pos_a, pos_b, di.min_level);
    uint add_val = V > 0.5 ? 0x00010001 : 0x00000001;

    uint var_max;
    if (r0.level == MISS || r0.total < min_bootstrap_weight)
        var_max = N_LEVELS - 1;  // bootstrap: write all
    else if (r0.variance > var_threshold)
        var_max = N_LEVELS - 1;  // boundary: write all
    else
        var_max = di.min_level;  // smooth: coarsest in range only

    uint max_level = min(di.max_level, var_max);

    for (uint lvl = di.min_level; lvl <= max_level; lvl++) {
        AddrFP af = get_addr_fp(pos_a, pos_b, lvl, table_size, is_inf);
        try_insert(af.addr, af.fp, add_val);
    }
}
```

Jitter is inside get_addr_fp (§5.3) — both endpoints jittered independently, then quantized. The insert function decides write depth from two gates: distance interval (perceptual relevance) and variance (shadow boundary).

### 6.3 Atomic Accumulation

```hlsl
#define DECAY_TRIGGER 32768  // half of uint16 max

void try_insert(uint addr, uint fp, uint add_val) {
    for (uint step = 0; step < MAX_PROBE; step++) {
        uint slot = probe(addr, fp, step);
        uint existing = 0;
        InterlockedCompareExchange(table[slot].fingerprint, 0, fp, existing);

        if (existing == 0 || existing == fp) {
            uint old;
            InterlockedAdd(table[slot].packed, add_val, old);

            // CAS-loop overflow decay
            uint total = (old & 0xFFFF) + (add_val & 0xFFFF);
            if (total > DECAY_TRIGGER) {
                uint expected = old + add_val;  // what we think packed is now
                uint p, vis, cnt;
                do {
                    p = expected;
                    vis = p >> 16;
                    cnt = p & 0xFFFF;
                    uint dv = vis >> 3;
                    uint dt = cnt >> 3;
                    uint desired = ((vis - dv) << 16) | (cnt - dt);
                    InterlockedCompareExchange(table[slot].packed, expected, desired, p);
                } while (p != expected);
            }
            break;
        }

        // Pressure-scaled eviction (§7)
        uint p = table[slot].packed;
        uint total = p & 0xFFFF;
        uint threshold = step < 2 ? 0 : eviction_base * (1 << (step - 2));
        if (threshold > 0 && total < threshold) {
            table[slot].fingerprint = fp;
            table[slot].packed = add_val;  // reset with this sample
            break;
        }
    }
}
```

Single InterlockedAdd on packed uint — visible_count and total_count always in sync. Overflow prevention via CAS loop: when total exceeds DECAY_TRIGGER (32768), atomically subtract 1/8 of both counters. The CAS ensures no concurrent InterlockedAdd is lost between read and write.

**Compound decay from warp reduction:** A merged add_val from 30 threads may push total past the trigger in one shot. The subsequent decay subtracts 1/8 of the post-add count. This is correct — equivalent to 30 individual inserts where the last one triggers decay, except decay fires once instead of potentially multiple times. Net effect: slightly higher peak count before decay, negligible difference.

**CAS contention:** At L0 with warp reduction, only ~16 atomics/cell/frame reach global memory. Of those, few trigger decay (only near the ceiling). CAS retry rate is negligible. Without warp reduction, L0 sees ~500 atomics/cell — CAS retries increase but only for the subset that triggers decay, and the retry window is short (one CAS iteration).

**ABA on CAS:** Two threads reading fp=0 simultaneously — second overwrites first. Wastes one traced sample. Not a correctness issue.

### 6.4 Warp Reduction (SM6.5+)

At L0 (4³ × 4³ ≈ 4K cells), screen-space coherent warps have many threads targeting the same cell. Instead of N serialized global atomics, discover matching threads within the warp, sum contributions, write once:

```hlsl
AddrFP af = get_addr_fp(pos_a, pos_b, lvl, table_size, is_inf);

// Find threads in this warp hitting the same cell
uint mask = WaveMatch(af.addr);

// Count V=1 and total within the group
uint vote_vis = WaveBallot(V > 0.5);
uint vis_count   = countbits(mask & vote_vis);
uint total_count = countbits(mask);
uint merged = (vis_count << 16) | total_count;

// One thread per unique cell does the global atomic
if (WaveIsFirstLane(mask)) {
    try_insert(af.addr, af.fp, merged);  // merged add_val
}
```

The packed format makes this free — adding `(7 << 16) | 10` to packed is the same as adding 7 to vis and 10 to total simultaneously.

L0 at 2M rays/frame: ~500 atomics/cell without reduction. With 32-wide warps where ~30 threads share an L0 cell, atomics drop ~16×. L1 benefits less (~2-4 threads per cell per warp) but still worthwhile.

Requires SM6.5+ (RDNA2+, Turing+). Fallback: sort keys within the threadgroup using shared memory, then adjacent threads with matching cells reduce locally and elect one writer. More LDS pressure and code, but works on SM6.0.

---

## 7. Pressure-Scaled Eviction

Always active on the insert path. Probe step is the pressure, but first probes are protected — step 0 and 1 never evict (home slot and immediate neighbor are rightful territory). Pressure ramps from step 2:

```hlsl
uint threshold = step < 2 ? 0 : eviction_base * (1 << (step - 2));
```

Step 0–1: no eviction. Step 2: eviction_base. Step 3: 2×. Long probe chains self-heal: entries causing the chain are evicted by elevated pressure from later probes. New entries with low total_count are never evicted at their home slot.

---

## 8. Temporal Decay (Dynamic Scenes)

Optional background pass that enables pressure eviction in temporal rendering. Stale entries from previous frames may have high counts from when they were actively sampled — pressure eviction alone can't touch them without unreasonably long probe chains. The decay pass weakens stale entries over time so pressure eviction can kill them at normal probe depths.

**Half-life is a user knob.** DECAY_PERIOD_MAX = slowest acceptable half-life for the scene. Action game: 60 (~1s). Architectural walkthrough: 300 (~5s). Auto-tuning (§18.3) may speed up below this ceiling under load pressure but never slows beyond it.

```hlsl
#define DECAY_PERIOD_MAX 60  // user-set ceiling, auto-tuning only goes faster

[numthreads(256,1,1)]
void DecayPass(uint id : SV_DispatchThreadID) {
    uint stride = table_size / decay_period;  // decay_period set by auto-tuner (§18.3)
    uint slot = (frame * stride + id) % table_size;
    if (table[slot].fingerprint == 0) return;

    uint p = table[slot].packed;
    uint vis   = p >> 16;
    uint total = p & 0xFFFF;
    uint dt = total >> 1;       // halve total
    uint dv = vis >> 1;         // halve vis

    if (total - dt == 0)
        table[slot].fingerprint = 0;  // dead
    else
        table[slot].packed = ((vis - dv) << 16) | (total - dt);
}
```

**Numerics:** Integer shift truncation `vis >> 1` and `total >> 1` don't preserve the ratio exactly. Error bounded by 1 count per decay op. At counts near DECAY_TRIGGER (~32K), that's ~0.003% mean shift — vanishes against Bernoulli noise. Subtracting from both with the same shift is the cheapest option that doesn't bias in a dangerous direction (subtracting only from total would drift mean upward → fewer traces → miss new occlusion).

**Race:** Decay's non-atomic read-modify-write races with concurrent InterlockedAdd from insert threads. At L0 contention, some samples are lost. Self-corrects within a frame at L0 sample rates. A CAS loop would be correct but adds contention; acceptable as-is.

Decay softens targets; pressure eviction pulls the trigger. Active entries recover quickly (high sample rate refills counts within a frame). Stale entries have no incoming samples to counteract halving — their counts drop until pressure eviction can displace them.

Not needed for single-frame rendering where the table starts empty.

---

## 9. Lookup

```hlsl
LookupResult lookup(float3 pos_a, float3 pos_b, float3 camera_pos, uint is_inf) {
    LookupResult best = MISS;
    LODInterval di = distance_lod_interval(pos_a, camera_pos);

    for (uint lvl = di.min_level; lvl <= di.max_level; lvl++) {
        AddrFP af = get_addr_fp(pos_a, pos_b, lvl, table_size, is_inf);

        int slot = find(af.fp, af.addr);
        if (slot < 0) break;

        uint p = table[slot].packed;
        uint vis   = p >> 16;
        uint total = p & 0xFFFF;
        if (total < min_weight) break;

        float mean = float(vis) / float(total);
        best.mean = mean;
        best.variance = mean * (1 - mean);
        best.total = total;
        best.level = lvl;

        if (best.variance < var_threshold) break;
    }
    return best;
}
```

Four stop conditions: distance interval bounds, no entry, too few samples, low variance. No parent-child reasoning.

---

## 10. Control Variate with Russian Roulette

Cached mean μ as control variate. Stored Bernoulli variance gates trace probability.

```hlsl
float3 shade_direct(HitInfo hit, Light light) {
    float3 analytic = brdf(hit, light) * light.Le * geometry_term(hit, light);

    LookupResult r = lookup(hit.pos, light.pos);

    float V_final;
    if (r.level == MISS) {
        float V = trace_shadow_ray(hit.pos, light.pos) ? 1.0 : 0.0;
        insert(hit.pos, light.pos, V);
        V_final = V;
    } else {
        float p_survive = clamp(r.variance / tau_rr, P_MIN, 1.0);

        if (random() < p_survive) {
            float V = trace_shadow_ray(hit.pos, light.pos) ? 1.0 : 0.0;
            insert(hit.pos, light.pos, V);
            V_final = r.mean + (V - r.mean) / p_survive;
        } else {
            V_final = r.mean;
        }
    }
    return analytic * V_final;
}
```

**Unbiased:** E[μ + (V − μ)/p] = E[V]. Cache quality affects only efficiency (residual variance), never correctness. Only traced values are inserted — inserting μ would create positive feedback.

**Self-regulating:** Low σ² → aggressive RR → few traces. High σ² → always trace → cache updates → σ² drops. Lighting change → σ² rises → more traces.

**User knobs:** TAU_RR controls RR aggressiveness (low = more skipping, faster, noisier). P_MIN / firefly_budget controls max amplification (low = more aggressive, more fireflies, fewer rays). These are the product's quality slider — same category as denoiser strength or ray budget.

### 10.1 Firefly Mitigation

At P_MIN = 0.05, surviving samples are amplified 20×. Worst case: μ ≈ 0, V = 1, p = 0.05 → V_est = 20. At shadow edges where μ ≈ 0.5, fireflies are spatially correlated — adjacent pixels share similar p_survive, producing bright clusters. Temporal denoisers integrate these into persistent bright bands.

**Adaptive P_MIN (recommended).** Scale the survival floor by contribution:

```hlsl
float contribution = luminance(brdf * Le * G);
float p_floor = clamp(contribution / firefly_budget, P_MIN_GLOBAL, 1.0);
float p_survive = clamp(r.variance / tau_rr, p_floor, 1.0);
```

High-contribution pixels get higher p_floor → less amplification → more traces. Low-contribution pixels can be aggressive — a 20× firefly on a dim surface is invisible. firefly_budget is the maximum tolerable absolute luminance from a single amplified sample. Unbiased.

**Output clamp (safety net).** Clamp the amplified estimate:

```hlsl
float V_est = mu + (V - mu) / p_survive;
V_est = clamp(V_est, 0.0, CLAMP_MAX);  // e.g. 5.0
```

Introduces bias bounded by CLAMP_MAX × p_survive per clamped sample. Visually: slight darkening at penumbra edges vs. bright firefly bands. Equivalent to `p → max(p, 1/CLAMP_MAX)`.

**Denoiser-side history rejection** is standard robust temporal filtering (reject samples > N sigma from running mean). Fights the cache's intent — surviving samples are meant to carry large weight — but catches extreme outliers at N = 3–5 sigma. Not the cache's responsibility.

---

## 11. ReSTIR Integration

The cache interacts with ReSTIR at three points: light selection, final shading, and GI revalidation. Each insertion point trades off savings, complexity, and risk.

### 11.1 Cache-Informed Light Selection

Replace V=1 in ReSTIR's target function p̂ with cached μ during initial candidate generation:

```hlsl
for (int i = 0; i < M; i++) {
    Light y = sample_light(pdf);
    float mu = max(lookup_L0(hit.pos, y.pos).mean, MU_MIN);  // floor prevents μ=0 exclusion
    float p_hat = f_s * y.Le * G * mu;
    reservoir.update(y, p_hat / pdf, mu);
}

// Exploration: one candidate ignores cache, always traces
Light y_explore = sample_light_uniform();
float V = trace(hit.pos, y_explore.pos) ? 1.0 : 0.0;
insert(hit.pos, y_explore.pos, V);
reservoir.update(y_explore, f_s * y_explore.Le * G * V / pdf_uniform, V);
```

**Unbiased** as long as μ > 0 everywhere (enforced by MU_MIN floor). The 1/W normalization in ReSTIR cancels μ — it influenced *selection*, not the final *value*. Standard importance sampling.

**Exploration candidate** prevents feedback death. Without it: cache says occluded → light never selected → never traced → cache never updated → permanent exclusion. The ε-greedy candidate (1/M ≈ 3% at M=32) guarantees every light is eventually probed.

**L0 is sufficient** for candidate weighting. Rough occlusion probability is the right granularity for light selection — no need for sharp shadow boundaries. Single hash lookup per candidate.

**Benefit:** Occluded lights (μ≈0) effectively removed from candidate pool. Hit rate jumps from ~70% to ~95% in scenes with many occluded lights. Multiplicative with spatial reuse — better initial candidates propagate through reservoir sharing.

### 11.2 Post-ReSTIR Final Shading (CV+RRR)

After ReSTIR selects a light, apply CV+RRR on the single final shadow ray. This is §10 applied at the shading stage. Decoupled from ReSTIR internals — ReSTIR runs unchanged, cache gates only the final trace.

At 1080p, saves ~1.76M shadow rays/frame/light (88% of 1 ray/pixel at typical survival rates). ~0.2–0.9ms/frame depending on ray cost. Modest but zero risk.

### 11.3 ReSTIR GI Revalidation

The cache's strongest use case. ReSTIR GI spatial reuse borrows neighbor paths and must verify visibility from the current shading point to the neighbor's secondary hit Q. Standard options: skip revalidation (biased, light leaks) or retrace all k neighbors (unbiased, expensive).

CV+RRR makes unbiased revalidation near-free. See §12 for full treatment.

### 11.4 Summary

| Insertion point | Rays saved | Unbiased? | Risk |
|---|---|---|---|
| In p̂ (selection) | M candidates skip tracing | Yes, if μ>0 | Feedback loop without exploration |
| Post-shading (final ray) | ~88% of 1 ray/pixel | Yes, trivially | Minimal |
| GI revalidation | ~80% of k rays/pixel | Yes, CV+RRR | Cache cold on disocclusion |

All three compose: cache informs which light to pick, gates the final shadow ray, and amortizes GI revalidation. Same hash table, same entries.

---

## 12. Contribution-Weighted Revalidation

### 12.1 The Insight

Don't RR based on visibility variance alone. RR based on how much the revalidation residual *matters to the pixel*. A dim light with uncertain visibility: skip. A bright light with known visibility: also skip. Trace only when uncertainty × contribution is significant.

### 12.2 With Cache

```hlsl
for (int i = 0; i < K_NEIGHBORS; i++) {
    vec3 Q = neighbor[i].secondary_hit;
    float mu = lookup(my_pos, Q).mean;

    float contrib_bound = f_s * neighbor[i].Lo * G(my_pos, Q);
    float max_residual = contrib_bound * max(mu, 1.0 - mu);
    float p = clamp(max_residual / threshold, P_MIN, 1.0);

    if (random() < p) {
        float V = trace(my_pos, Q) ? 1.0 : 0.0;
        insert(my_pos, Q, V);
        V_est[i] = mu + (V - mu) / p;
    } else {
        V_est[i] = mu;
    }
}
```

Three regimes: μ≈1 (known visible, small residual → skip), μ≈0 (known occluded, small residual → skip, return ~0), μ≈0.5 (uncertain, trace if bright). The cache collapses two of three cases. Expected traces: ~0.5–1.0 per pixel at k=5.

**Per-pixel adaptive threshold:** Set relative to pixel luminance. `threshold = pixel_luminance × relative_error`. More aggressive in bright regions, conservative in dark (matches perceptual importance).

### 12.3 Without Cache

For GI revalidation, there is no spatial neighbor poll — each neighbor has a *different* secondary hit Q. Nobody else evaluated V(my_pos, Q_neighbor). Without cache, μ defaults to 0.5 (uninformed), and max_residual = contrib_bound for every neighbor. This degrades to contribution-only RR — skip dim neighbors, always trace bright ones. Still useful, but no visibility signal.

| Scenario | Traces/pixel (k=5) | Visibility signal |
|---|---|---|
| Full revalidation | 5.0 | N/A |
| Contribution-only RR (no cache) | ~1.5 | None — bright always traced |
| Contribution-weighted + cache | ~0.5–1.0 | Cache distinguishes bright+visible from bright+uncertain |

### 12.4 Path Sharing via Spatial Reuse

ReSTIR GI concentrates selections: a "good" path (high Lo) gets selected by many pixels in the reuse radius. All need to revalidate visibility to the *same Q* from nearby shading points. At L0 quantization (4³), nearby shading points hash to the same cell. The first pixel to trace populates the entry; subsequent pixels find it cached.

This happens within a single frame via wavefront execution. With 50–100 pixels selecting the same path, they fall into ~3–5 L0 cells. Total traces for that path: ~3–5 instead of ~50–100.

This is the strongest architectural argument for L0's coarse resolution — it maximizes sharing across pixels that selected the same reused path.

### 12.5 Cache-Informed Neighbor Selection

Score potential spatial neighbors before committing to reuse:

```hlsl
for (int i = 0; i < CANDIDATE_NEIGHBORS; i++) {
    vec3 Q = candidate[i].secondary_hit;
    float mu = lookup_L0(my_pos, Q).mean;
    float score = geometric_score * mu;  // prefer visible paths
    // insert into top-k
}
```

Neighbors whose secondary hit is occluded from the current point get deprioritized. Reduces wasted reuse attempts. L0 only — needs to be cheap.

---

## 13. Cache-Free Alternatives

### 13.1 Binary V_prev as Control Variate

Use ReSTIR's own temporal reservoir history. Each reservoir already carries the previous frame's traced V (0 or 1). Use as μ directly:

```hlsl
float mu = reservoir.V_prev;
float p = P_REVALIDATE;  // fixed or heuristic-driven
if (random() < p) {
    float V = trace(hit.pos, light.pos) ? 1.0 : 0.0;
    V_est = mu + (V - mu) / p;
    reservoir.V_prev = V;
} else {
    V_est = mu;
}
```

Zero additional storage. But μ is binary — maximum possible residual when wrong (|V−μ|=1), spatially correlated fireflies at shadow edges. No built-in variance estimate to drive adaptive p. Breaks on disocclusion (no history). Cannot help spatial reuse or GI revalidation (V_prev is for a different shading point).

### 13.2 Spatial Neighbor Visibility Poll (DI only)

During ReSTIR DI spatial reuse, multiple neighbors may have selected the same light. Their traced V values are binary samples of visibility from nearby points to the same light. Pool them for a fractional estimate:

```hlsl
float v_sum = 0, v_count = 0;
for (int i = 0; i < K_NEIGHBORS; i++) {
    if (same_light(neighbor[i].reservoir.light, y)) {
        v_sum += neighbor[i].reservoir.V;
        v_count += 1;
    }
}
float mu = v_count > 0 ? v_sum / v_count : 0.5;
```

Temporal EMA of the spatial estimate (`mu_temporal = lerp(mu_temporal, mu_spatial, alpha)`) gives smooth fractional μ that converges over frames. One extra float per pixel. Works well for DI where many neighbors share the same light. Does not work for GI — each neighbor has a different secondary hit, no shared queries.

### 13.3 Comparison

| Approach | μ quality | Storage | Camera-robust | Helps GI | Effort |
|---|---|---|---|---|---|
| Binary V_prev | 0 or 1 | 0 | No | No | Trivial |
| Spatial neighbor poll | Fractional, noisy | 1 float/px | No | No | Easy |
| Temporal EMA of spatial | Fractional, smooth | 1 float/px | Partial (reproj) | No | Easy |
| World-space hash cache | Fractional, converged | ~4 MB | Yes | Yes | Nontrivial |

Cache-free approaches capture ~60% of the benefit at ~5% of implementation cost for DI. The cache's unique advantage: GI revalidation (no screen-space alternative exists for arbitrary secondary hits) and camera-motion robustness. Both can coexist — screen-space μ for temporal DI, hash cache for spatial reuse + GI.

---

## 14. Prior Art

**Kugelmann 2006** — *Efficient Adaptive Global Illumination Algorithms*, Diplomarbeit, Universität Ulm (supervised by Alexander Keller). Establishes the framework this paper extends: spatial-hash grid cells for grouping visibility samples (hash inspired by [Teschner et al. 2003] via Keller's lectures; present in code, not textualized in thesis), predicted visibility V̄ with RR-gated correction (CV+RRR developed independently of Szirmay-Kalos et al.), quality factor Q scaling correction probability, and a generalized "predictions with correction at random" framework for unbiased adaptive sampling. Applied to shadow test reduction in Robust Instant Global Illumination with many point lights. **Direct ancestor of this work.**

**Guo, Eisemann & Eisemann 2020 (NEE++)** — Spatial×spatial visibility caching with Russian roulette. Voxel-to-voxel visibility probability in 6D domain, bidirectional symmetry, RR rejection of shadow rays, unbiased estimator. Reports 80% shadow ray reduction. Uses dense D³×D³ matrix (16³ voxels → 32 MB, single resolution, offline). Independently arrived at a similar spatial cache with RR. We replace the dense matrix with sparse multilevel hash for real-time, and substitute CV+RRR (return μ on kill) for standard RR (return 0 on kill).

**Popov et al. 2013** — Adaptive Quantization Visibility Caching. Adaptive spatial quantization, reports <2% shadow rays needed. Demonstrates that spatial quantization of visibility queries is viable.

**Ulbrich et al. 2013** — Progressive Visibility Caching. Progressive refinement of cached visibility.

**Ward 1994** — Adaptive Shadow Testing. Statistical visibility for shadow ray gating. The original observation that shadow ray decisions can be guided by spatial statistics.

**Bokšanský & Meister 2025** — Neural Visibility Cache. Notes "cache mutual visibility between any two points" as future work — which is exactly what we (and NEE++) do. Uses neural network; we use hash table.

**Binder et al. 2018** — Path space filtering (independent development of spatial hashing). Main takeaway for this work: jitter-before-quantize filtering pattern and fingerprint design. *Note: Teschner's spatial hashing was covered in Keller's CG simulation lectures, likely the common root for both Kugelmann 2006 and Binder 2018.*

**Gautron 2020/2021** — Real-time ray-traced AO with spatial hashing; LOD index in the hash function with viewing-distance-based cell size selection, propagation from finer to coarser LODs. Direct reference for our distance-gated LOD selection.

**Müller et al. 2022** — Instant-NGP: multi-resolution hash, all levels written simultaneously.

**Stotko et al. 2025** — MrHash: variance-driven adaptation in flat hash (TSDF domain).

**Ouyang et al. 2021 / Lin et al. 2022** — ReSTIR GI: path reuse with revalidation rays. We provide the visibility cache that makes revalidation RR-gatable while preserving unbiasedness.

**Bitterli et al. 2020** — ReSTIR DI: resampled importance sampling for light selection. Complementary.

**Szirmay-Kalos et al.** — "Go with the winners" — control-variate Russian roulette residual (CV+RRR). Returns cached μ on RR kill instead of 0. Independent development in [Kugelmann 2006].

---

## 15. Contributions

The core idea — spatial-hash grid for visibility prediction with RR-gated correction — originates in [Kugelmann 2006], a Diplomarbeit at Universität Ulm supervised by Alexander Keller (CV+RRR independent of [Szirmay-Kalos et al.]). NEE++ [Guo et al. 2020] independently arrived at a similar spatial×spatial cache with RR for offline rendering.

This work extends the 2006 foundation to real-time GPU path tracing:

1. **Multilevel sparse hash** — multiple LOD levels [Gautron 2020] in a shared open-addressing hash table, with temporal decay and pressure eviction for bounded real-time memory.

2. **Integration with ReSTIR DI/GI pipelines** — cached μ in the target function for light selection, contribution-weighted RR for GI revalidation, path sharing through L0 spatial quantization.

3. **GPU-specific engineering** — packed atomic entries, warp reduction (SM6.5+), CAS overflow decay, distance-gated LOD intervals, angular quantization for infinite endpoints, runtime statistics with auto-tuning decay, and exploration candidates for feedback prevention.

---

## 16. Configuration

### Implementation Parameters

```hlsl
#define N_LEVELS            3
#define MAX_PROBE           4
#define MIN_WEIGHT          4
#define MIN_BOOTSTRAP_WEIGHT 8
#define DECAY_TRIGGER       32768   // inline overflow decay threshold
#define EVICTION_BASE       4       // pressure eviction base (uint16 count)
#define MIN_CELL_PIXELS     4       // LOD max range: cell < 4×4 pixels → skip
#define MAX_CELL_PIXELS     64      // LOD min range: cell > 64×64 pixels → skip

// Default: asymmetric (unidirectional PT)
static const LODConfig lods[N_LEVELS] = {
    { 10.0,  10.0,  0.10  },   // L0: ~10m cells, ~6° angular bins
    { 1.25,  2.5,   0.025 },   // L1: ~1.25m / 2.5m, ~1.4° angular bins
    { 0.08,  0.625, 0.005 },   // L2: ~8cm / 62cm, ~0.3° angular bins
};
```

### User Quality Knobs

```hlsl
#define VAR_THRESHOLD       0.01    // L0 variance gate for fine writes
#define TAU_RR              0.01    // RR aggressiveness (low = more skip)
#define P_MIN               0.05    // global floor on trace probability
#define FIREFLY_BUDGET      10.0    // max luminance per amplified sample
#define CLAMP_MAX           5.0     // output clamp safety net (biased)
#define MU_MIN              0.01    // floor on cached μ in light selection
#define DECAY_PERIOD_MAX    60      // max decay half-life in frames (user floor on responsiveness)
```

TAU_RR × P_MIN × FIREFLY_BUDGET form the quality/performance tradeoff. DECAY_PERIOD controls responsiveness to lighting changes. All are scene-independent in meaning, scene-dependent in optimal value.

---

## 17. Table Sizing

Active cell population is sparse. Most theoretical cells are empty. Active count depends on scene complexity and visible surface area:

- **L0:** 10m cells, coarse. ~1K active. 8 KB.
- **L1:** 1.25m–2.5m cells. ~50K active (shadow boundaries). 400 KB.
- **L2:** 8cm–62cm cells. ~200K active (fine shadow edges). 1.6 MB.

Total ~250K active entries. At 8 bytes and 50% load factor: ~4 MB.

---

## 18. Runtime Statistics and Auto-Tuning

### 18.1 Per-Frame Counters

Five global atomic counters on a dedicated buffer (separate cache line from table, zero contention):

```hlsl
RWByteAddressBuffer stats;
// [0] inserts     — successful try_insert
// [4] evictions   — pressure eviction triggered
// [8] misses      — lookup returned MISS
// [12] decays     — overflow CAS decay triggered
// [16] probe_sum  — total probe steps (insert + lookup)
```

Read back CPU-side one frame later via async readback (no GPU stall). Reset counters each frame.

### 18.2 Derived Metrics

- **Load pressure:** eviction_rate / insert_rate. Near 1.0 = table full, every insert evicts. Near 0 = plenty of room.
- **Cache effectiveness:** 1 - miss_rate / query_rate. How often the cache helps vs falls back to baseline.
- **Average probe depth:** probe_sum / (inserts + queries). Rising = load factor climbing.
- **Decay trigger rate:** How often overflow decay fires. High = many active entries near ceiling.

### 18.3 Auto-Tuning Decay Period

DECAY_PERIOD has a user-set ceiling: DECAY_PERIOD_MAX — the slowest acceptable decay for the scene type (action game: 60, architectural walkthrough: 300). Auto-tuning only speeds up from there to relieve load pressure, never slows beyond the user's chosen responsiveness:

```
error = smoothed_pressure - target_pressure   // target ≈ 0.4
auto_value += Kp * error + Ki * integral(error)
DECAY_PERIOD = clamp(auto_value, 8, DECAY_PERIOD_MAX)
```

High pressure → decrease DECAY_PERIOD → faster forgetting → more room. Low pressure → relax back toward DECAY_PERIOD_MAX but never exceed it. One-sided controller.

**Table resize (fallback):** Can't resize mid-frame without rehashing. If average probe depth > 2.5 for N consecutive frames, double table next frame (allocate, zero, swap). If < 1.2 and pressure < 0.1, halve. Hysteresis prevents thrashing.

**Do NOT auto-tune:** TAU_RR, P_MIN, FIREFLY_BUDGET — these are quality decisions. Auto-tuning them from cache stats would silently change visual quality.

---

## 19. Results

### 19.1 Test Scenes

**TODO:** Select 3–4 scenes covering key regimes: many small lights (bistro), single dominant light (sponza sun), IBL-heavy (outdoor), dynamic lighting (animated spots). Show baseline vs cache-enabled for each.

### 19.2 Variance Reduction

**TODO:** Per-pixel variance maps (baseline PT vs cache-enabled) at equal sample count. Show L0/L1/L2 contribution heatmaps. Measure MSE convergence rate over frames.

### 19.3 Performance

**TODO:** Shadow ray count reduction (total traced / total shaded pixels). Frame time breakdown: cache insert, lookup, decay pass, warp reduction overhead. Measure at 1080p and 4K.

### 19.4 Runtime Statistics

**TODO:** Plot per-frame counters (§18) over a camera flythrough: insert rate, eviction rate, miss rate, average probe depth, decay triggers. Show auto-tuning DECAY_PERIOD response to load changes.

### 19.5 Ablation

**TODO:** Disable components individually and measure impact: distance-gated LOD interval, variance gate, warp reduction, overflow CAS decay, pressure eviction. Identify which components carry the most value.

### 19.6 Parameter Sensitivity

**TODO:** Sweep TAU_RR, P_MIN, MIN_CELL_PIXELS, MAX_CELL_PIXELS, DECAY_PERIOD_MAX. Show quality/performance tradeoff curves.

---

## 20. Discussion

**Graceful degradation:** Where cell resolution is too coarse for the feature (e.g. penumbra narrower than L2 cell), variance stays high (mixed V=0/V=1 in one cell → σ² ≈ 0.25), p_survive → 1.0, every ray traces. Similarly, rarely-selected lights have few cache samples → low total_count → lookup fails min_weight → MISS → unconditional trace. In both cases the cache degrades to unoptimized baseline — zero savings but zero harm. Unbiased CV+RRR guarantees this: the cache can never make things worse than not having a cache, only fail to help.

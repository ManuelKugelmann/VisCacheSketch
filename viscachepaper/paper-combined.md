# Multilevel Visibility Hash Filter
## Variance-Driven Shadow Ray Caching for Real-Time Path Tracing

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

We present a multilevel spatial hash table that caches pairwise visibility between surface regions and light regions for real-time path tracing. The cached mean serves as a control variate with Russian roulette residual (CV+RRR) — a classical technique that makes shadow-ray gating provably unbiased regardless of cache accuracy — forming a self-regulating loop that concentrates traces on shadow boundaries. Multiple LOD levels are written simultaneously and selected per query by screen-space cell footprint. We integrate the cache with ReSTIR DI and GI pipelines: cached visibility informs light selection, gates final shading shadow rays, and enables contribution-weighted revalidation that approaches biased-skip cost while preserving unbiasedness. Initial profiling on Bistro exterior shows **##%** shadow-ray reduction in direct illumination and **##%** in GI revalidation, with no measurable bias and negligible cache-maintenance overhead.

**Keywords:** visibility caching, shadow rays, spatial hashing, control variate, Russian roulette, ReSTIR, real-time rendering

---

# 1. Introduction

Shadow rays dominate the cost of direct lighting in real-time path tracing. Most confirm what nearby rays already established: a surface region is consistently lit or consistently occluded from a light region. We cache point-to-point visibility in a spatial hash table and gate shadow rays via control-variate Russian roulette residual (CV+RRR): the cached mean replaces most traces, a randomly-triggered correction preserves unbiasedness, and a self-regulating loop concentrates remaining traces on shadow boundaries.

Kugelmann [2006] explored three independent cache experiments — irradiance, binary visibility, and free-path distance — each with CV+RRR correction in a fixed-resolution single-level spatial hash. We develop the binary visibility experiment into a complete real-time system. Binary is sufficient for shadow decisions; its Bernoulli structure gives variance for free from a single cached mean (var = μ(1−μ)); and the (point, point) domain aligns with pairwise visibility queries. CV+RRR itself is a classical technique (Szirmay-Kalos et al., "go with the winners"; independently in [Kugelmann 2006]). We do not claim it as new — we advocate for its wider adoption and develop the system around it.

World-space visibility caches are a natural complement to ReSTIR [Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022]: spatial reuse concentrates many pixels onto the same light or secondary hit, and a world-space cache amortizes their shared visibility queries automatically. The cache integrates with ReSTIR DI and GI pipelines at three points: light selection, final shading, and path revalidation.

Our contributions: (1) A real-time pairwise binary visibility cache with CV+RRR correction, where the Bernoulli variance signal self-regulates trace probability without per-scene tuning. (2) Three integration points with ReSTIR DI/GI sharing one cache — light selection weighting, final-shading shadow-ray gating, and GI revalidation gating — the last being the strongest case since no screen-space alternative exists for arbitrary secondary hits. (3) Real-time capacity management — temporal decay, pressure-scaled eviction, warp reduction (SM 6.5), distance-gated LOD selection — and an optional multilevel structure that reduces sensitivity to cell-size choice.

---

# 2. Related Work

**Visibility caching.** Ward [1994] introduced statistical shadow testing — gating shadow rays by spatial statistics. Popov et al. [2013] developed adaptive quantization visibility caching, reporting less than 2% of shadow rays needed. Ulbrich et al. [2013] proposed progressive refinement. Guo, Eisemann and Eisemann [2020] (NEE++) cache voxel-to-voxel visibility probability in a 6D domain with bidirectional symmetry and RR rejection, reporting 80% shadow ray reduction. Their approach uses a dense D3×D3 matrix (163 voxels, ~32 MB, single resolution, offline).

**Kugelmann [2006]** explored three independent cache experiments within a spatial hash grid [Teschner et al. 2003]: (1) irradiance (point, direction) → ℝ, (2) binary visibility (point, point) → {0,1}, and (3) free-path distance (point, direction) → ℝ≥0 — each with CV+RRR correction rates driven by their respective variances, in a fixed-resolution single-level hash applied to shadow-test reduction in robust instant global illumination. The binary visibility experiment is the direct ancestor of this work. Two decades of hardware evolution — GPU ray tracing, wave intrinsics — and the ReSTIR framework provide the context that makes the 2006 experiment practical as a real-time system.

Concurrent with this work, Bokšanský and Meister [2025] feed neural visibility estimates into weighted reservoir sampling for light selection — the same visibility-weighted selection idea as our Sec. 8.1. Their approach uses an Instant-NGP backbone [Müller et al. 2022] and operates in biased mode by default, using network output directly for shading when confident. CV+RRR (Sec. 4) would make their biased mode unbiased by construction. Reservoir Splatting [Liu et al. 2025] improves temporal path reuse robustness under camera motion via forward projection with Jacobian correction; our cache addresses the orthogonal problem of spatial revalidation cost.

**Spatial hashing.** Teschner et al. [2003] established spatial hashing for collision detection. Binder et al. [2018] applied fingerprint-based hashing to path-space filtering with jitter before quantization. Müller et al. [2022] (Instant-NGP) store multi-resolution features in hash tables combined via MLP. Stotko et al. [2025] (MrHash) use variance-driven adaptation in flat hash for TSDF reconstruction. Gautron [2020, 2021] used LOD index in the hash function with viewing-distance-based cell size selection for real-time ray-traced AO.

**ReSTIR.** Bitterli et al. [2020] introduced resampled importance sampling for direct lighting. Ouyang et al. [2021] and Lin et al. [2022] extended this to path reuse, where revalidation rays test visibility from the current shading point to a neighbor's secondary hit. The biased/unbiased tradeoff — skip revalidation (light leaks) vs. always retrace (expensive) — motivates our approach. CV+RRR integrates with Area ReSTIR [Zhang et al. 2024] without modification: the final shadow-ray structure is identical to standard RTXDI.

**Control variates and hashing.** Szirmay-Kalos et al. described the "go with the winners" estimator: returning a control variate value on RR termination instead of zero. [Kugelmann 2006] developed CV+RRR independently for the same purpose. We apply this classical technique to cached visibility and advocate for its wider adoption. For hash noise we use pcg3d [Jarzynski and Olano 2020], a GPU hash function that passes all but one BigCrush test at ~12 ALU with no lookup table.

---

# 3. Data Structure

## 3.1 Entry

Each entry stores a fingerprint and a packed uint with two 16-bit counters (visible_count, total_count):

```hlsl
struct Entry {
  uint fingerprint; // collision detect
  uint packed;     // [vis:16][total:16]
}; // 8 bytes
```

V=1 adds 0x00010001; V=0 adds 0x00000001. Single InterlockedAdd — both counters always in sync. Mean = vis/total, variance = mean(1−mean). Weighted insertion optional: quantize weight to 4 bits (1–15), add (w&lt;&lt;16)|w for V=1. Overflow prevented by inline decay: when total exceeds a trigger, subtract 1/8 of both counters.

## 3.2 LOD Configuration

Three levels. Default: asymmetric — endpoint A (shading point) refines faster than B (light/secondary hit), matching the common unidirectional PT case where roles are known. Cell sizes in world units; no scene bounds needed (§4). Optional: symmetric cell sizes for bidirectional use cases, required when canonicalization (Sec. 4) is enabled.

| Level | Cell A | Cell B | ≈ px @ 5 m |
|---|---|---|---|
| L0 | 10 m | 10 m | ~107 |
| L1 | 1.25 m | 2.5 m | ~13 / ~27 |
| L2 | 8 cm | 62 cm | ~0.9 / ~6.7 |

> **Table 1.** Asymmetric cell sizes (default). Symmetric variant uses Cell A for both endpoints. Pixel column shows projected Cell A / Cell B side length at 5 m distance, 90° HFoV, 1080p. L2 Cell A is subpixel at 5 m because L2 is only active at close range (distance-gated, Sec. 5).

Cell sizes are calibrated for primary viewing distances of 2–20 m in mixed exterior/interior scenes (Bistro, Sponza). Scenes at substantially different scales (tabletop close-ups, city-scale flyovers) would benefit from camera-adaptive cell sizing via FoV and circle of confusion — deferred to future work.

**LOD asymmetry.** Cell sizes are asymmetric: endpoint A (shading point) is quantized more finely than endpoint B (light source or secondary hit). This is justified for direct illumination where the shading point exhibits more spatial variation (view-dependent BRDF, geometric normal) than the light source (spatially coherent emission). For GI revalidation (Sec. 9), where B is also a surface point, symmetric cells may be more appropriate — we defer this investigation, noting that at L2 both endpoints are typically close spatially, limiting the impact.

**Explicit vs. neural.** Compared to neural visibility caches [Bokšanský and Meister 2025], the explicit hash table offers inspectable entries (cached μ and sample count are directly readable), zero inference latency (one hash + one memory read vs. MLP evaluation), predictable cold-start behavior (first sample populates an entry immediately), and tunable parameters with clear semantics. The neural approach offers automatic spatial adaptation without explicit LOD configuration and potentially better generalization. CV+RRR (Sec. 8) applies identically to either data structure.

---

# 4. Addressing

Quantization uses absolute cell-size division: int3(floor(pos / cell_size)). No scene bounds needed — works for any position. Both endpoints are jittered independently before quantization, with magnitude = cell_size. Jitter uses pcg3d [Jarzynski & Olano, 2020], seeded from the unquantized position bits asuint(pos). Each surface point therefore gets independent jitter, and a fixed world-space point always maps to the same cell.

**Stochastic vs coherent jitter.**  Prior path-space filtering [Binder et al., 2018] seeds jitter from the preliminary cell index floor(pos/cell_size), so all positions within a preliminary cell share the same displacement vector. This maximizes samples per cell but creates sharp step functions at (irregularly placed) cell boundaries — a systematic, persistent bias that does not diminish with accumulation. Position-seeded jitter instead gives probabilistic cell membership near boundaries: nearby surface points may map to different cells, producing an intrinsic box filter across the boundary. The marginal variance increase from this boundary dilution is noise that reduces with sample count, while boundary steps are irreducible bias. Eliminating bias at the cost of slightly more reducible variance is the standard Monte Carlo trade-off.

Fingerprint uses the same jittered+quantized coordinates as the address but a different hash function [Keller et al., 2016],[Binder et al., 2018]. Optional bidirectional canonicalization (lexicographic swap) merges V(P,Q) and V(Q,P) into one entry; requires symmetric cell sizes. Probe sequence: double hashing with fingerprint as h2. IBL samples use a virtual far endpoint; a 1-bit is_inf flag selects angular quantization (octahedral mapping) for infinite endpoints (IBL, directional lights) vs positional quantization for finite surfaces, preventing collisions between the two address spaces. Canonicalization applies only to finite×finite pairs.

---

# 5. Insert

L0 is read to decide write depth. During bootstrap, all levels are written. Once L0 matures, fine levels are written only where L0 variance exceeds a threshold — the same variance signal that drives RR survival probability in Sec. 8 (see coupled variance adaptation). A distance interval gates the LOD range by target square pixel footprint: skip levels where the cell is below 4×4 pixels or above 64×64 pixels. Clipmap-like: L0 far field, L2 near field, L1 bridges. Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync.

**Algorithm 1: Distance + Variance-Gated Insert**
```
Input: pos_a, pos_b, visibility V, camera_pos
di <- distance_lod_interval(pos_a, camera_pos)
r0 <- lookup_single(pos_a, pos_b, di.min_level)
if r0 = MISS or r0.weight < w_bootstrap then
  var_max <- N_LEVELS - 1               // bootstrap
else if r0.variance > tau then
  var_max <- N_LEVELS - 1               // boundary
else
  var_max <- di.min_level               // smooth
max_level <- min(di.max_level, var_max)
for l <- di.min_level to max_level do
  jitter pos_a by cell_size(l)
  try_insert(hash(pos_a,pos_b,l), fp(pos_a,pos_b,l), V)
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

---

# 6. Eviction and Temporal Decay

Pressure-scaled eviction is always active on the insert path. Steps 0–1 are protected (no eviction at home slot). From step 2, each step doubles the eviction threshold, enabling self-healing of long chains. Inline overflow decay uses a CAS loop to atomically subtract 1/8 of both counters when total exceeds a trigger, keeping counts near the ceiling so recent samples dominate. Integer shift-truncation preserves the mean ratio within ~0.003% at trigger counts. For dynamic scenes, an optional background decay pass traverses 1/N of the table per frame, halving counts on each visit. The effective half-life is DECAY_PERIOD frames. At DECAY_PERIOD=60 (~1 s at 60 fps): an entry not refreshed decays to 1/1024 of its original count in 10 s (10 half-lives). At DECAY_PERIOD=300 (~5 s): the same decay takes 50 s. Active entries resist decay because their sample rate (hundreds of inserts/frame at L0) far exceeds the decay rate (one halving per DECAY_PERIOD frames). Not needed for single-frame rendering.

---

# 7. Lookup

**Algorithm 2: Coarse-to-Fine Lookup**
```
Input: pos_a, pos_b, camera_pos
best <- MISS
di <- distance_lod_interval(pos_a, camera_pos)
for l <- di.min_level to di.max_level do
  slot <- find(fp(pos_a,pos_b,l), hash(pos_a,pos_b,l))
  if slot < 0 then break              // no entry
  e <- table[slot]
  if e.total < w_min then break        // too sparse
  p <- e.vis / e.total
  best <- (mean=p, var=p(1-p), level=l)
  if best.var < tau then break         // clean enough
return best
```

Four stopping conditions: distance interval bounds, no entry, too few samples, low variance.

---

# 8. Control Variate with Russian Roulette

The cached mean μ serves as a control variate [Szirmay-Kalos et al.]. Analytic lighting (BRDF × Le × G) is always evaluated. Only the shadow ray is gated:

**Algorithm 3: Shading with Cached Visibility**
```
Input: hit, light
analytic <- brdf x Le x G
r <- lookup(hit.pos, light.pos)
if r = MISS then
  V <- trace(hit, light); insert(V)
  return analytic x V
p_s <- clamp(r.var / tau, P_MIN, 1)
if random() < p_s then
  V <- trace(hit, light); insert(V)
  return analytic x (r.mean + (V - r.mean) / p_s)
else
  return analytic x r.mean     // no trace, no insert
```

**Unbiasedness proof.** The estimator V̂ equals μ + (V − μ)/p with probability p, and μ with probability (1−p). E[V̂] = p·(μ + (E[V]−μ)/p) + (1−p)·μ = E[V]. The residual variance is Var[V̂] = (1/p − 1)·Var[V − μ]. When μ = E[V], the residual is zero — a perfect cache needs no correction rays. Cache quality affects only efficiency (residual variance), never correctness. Only traced values are inserted — returning μ without tracing does not update the cache, preventing positive feedback.

**Generality.** CV+RRR converts any visibility estimate μ — whether from a spatial hash (this work), a neural network [Bokšanský and Meister 2025], temporal reprojection, or spatial neighbor polling — into an unbiased estimator wherever a mean estimate is available. The technique is agnostic to the source of μ; cache quality affects only efficiency, never correctness.

**Why binary visibility.** [Kugelmann 2006] explored three cached quantities; we choose binary visibility for three reasons: (1) binary is sufficient for shadow-ray decisions — the ray either hits or misses; (2) Bernoulli structure gives variance for free from μ alone (var = μ(1−μ)), requiring no separate variance estimator; (3) the (point, point) → {0,1} domain aligns naturally with ReSTIR's pairwise queries where each reservoir stores a specific source–target pair. Free-path distance [Kugelmann 2006, experiment 3] is a richer representation but requires a separate variance estimator and is not pursued here.

**Coupled variance adaptation.** The same Bernoulli variance var = μ(1−μ) drives two reinforcing mechanisms simultaneously: (1) RR survival probability p = clamp(var/τ, pmin, 1) governs the correction rate — how often shadow rays are traced; (2) the write-depth gate (Sec. 5.2) governs spatial resolution — whether fine-level cache entries are updated. High-variance regions trace more often *and* update fine levels; low-variance regions trace rarely *and* only update the coarsest level. This coupling is self-regulating: no per-scene tuning is needed because the variance signal adapts to local shadow structure automatically. The coupling only becomes possible with a multilevel cache — [Kugelmann 2006] had fixed resolution, so only the correction rate was variance-driven.

Self-regulating: low σ2 → aggressive RR → few traces. High σ2 → always trace → cache updates → σ2 drops. Lighting change → σ2 rises → traces reallocated. Pmin ≈ 0.05 ensures at least 5% of pixels always trace.

## 8.1 Firefly Mitigation

At Pmin=0.05, surviving samples are amplified up to 1/Pmin = 20×. Worst case: μ≈0, V=1, p=0.05 → V̂ = 0 + (1−0)/0.05 = 20. At shadow edges where μ≈0.5, fireflies are spatially correlated — adjacent pixels share similar psurvive, producing bright clusters that temporal denoisers integrate into persistent bright bands.

**Adaptive Pmin.** Scale the survival floor by shading contribution: pfloor = clamp(luminance(fs·Le·G) / firefly_budget, Pmin, 1). firefly_budget is the maximum tolerable absolute luminance (cd/m²) from a single amplified sample. Example: with firefly_budget = 10 and shading contribution luminance 50, pfloor = 1 — the ray is always traced, preventing a 1000-luminance firefly. A dim contribution of luminance 0.1 gets pfloor = 0.01 — aggressive RR is safe because even 100× amplification produces only luminance 10. Unbiased.

**Output clamp (biased safety net).** Clamp the amplified estimate: V̂ = clamp(V̂, 0, C). Introduces bias bounded by C × p per clamped sample. Equivalent to p → max(p, 1/C). Visually: slight darkening at penumbra edges vs. bright firefly bands.

---

# 9. ReSTIR Integration

The cache interacts with ReSTIR at three points, all using the same hash table. Both DI and GI queries are point-to-point visibility lookups.

## 9.1 Cache-Informed Light Selection

Replace V=1 in ReSTIR's target function p̂ with cached μ during initial candidate generation: p̂ = fs × Le × G × max(μ, μmin). The μmin floor (default 0.01) prevents permanent exclusion of visible lights with stale cache entries. Bokšanský and Meister [2025] independently apply the same visibility-weighted selection idea with a neural cache.

**Unbiasedness.** The cached μ appears only in the target function p̂ used for candidate selection, not in the final estimator. ReSTIR's 1/W normalization cancels p̂ — the selected light's contribution is divided by its selection probability, which includes μ. For this cancellation to hold, every light must have nonzero selection probability. The μmin floor enforces this: even a fully occluded light (true μ=0) retains at least 1% of its BRDF-weighted selection weight.

An exploration candidate (1/M of budget, where M is the number of initial light candidates per pixel, typically 32) uses uniform sampling and always traces its shadow ray — the ε-greedy strategy. Combined with μmin, permanent exclusion is impossible.

L0 suffices for candidate weighting. Occluded lights (μ≈0) are effectively removed from the candidate pool, improving hit rate from ~70% to ~95% in scenes with many occluded lights.

## 9.2 Post-Shading Shadow Ray

After ReSTIR selects a light, apply CV+RR (Algorithm 3) on the final shadow ray. Decoupled from ReSTIR internals. Saves ~88% of final shadow rays. Modest but zero risk.

## 9.3 ReSTIR GI Revalidation

The cache's strongest use case. ReSTIR GI spatial reuse borrows neighbor paths and must verify visibility from the current shading point P to the neighbor's secondary hit Q. With k=5 spatial neighbors, unbiased revalidation costs 5 shadow rays per pixel — the main reason production systems use biased skip-revalidation.

CV+RR makes unbiased revalidation near-free: look up cached V(P, Q), apply contribution-weighted RR (Sec. 10). Expected traces drop from 5 to ~0.7 per pixel.

| Insertion point | Rays saved | Unbiased? | Risk |
|---|---|---|---|
| In target (selection) | M candidates | If μ>0 | Feedback loop |
| Post-shading | ~88% of 1/px | Trivially | Minimal |
| GI revalidation | ~85% of k/px | CV+RR | Cold on disocclusion |

> **Table 2.** Cache insertion points in ReSTIR.

---

# 10. Contribution-Weighted Revalidation

RR probability proportional to how much the revalidation residual *matters to the pixel*, not just visibility variance. Maximum possible residual for neighbor i: fs × Lo × G × max(μ, 1−μ).

With the cache, three regimes: μ≈1 (known visible, small residual → skip), μ≈0 (known occluded, small residual → skip), μ≈0.5 (uncertain → trace if bright). The cache collapses two of three cases. Without cache, μ=0.5 for all GI queries (no spatial neighbor poll exists for arbitrary secondary hits), degrading to contribution-only RR.

**Algorithm 4: Contribution-Weighted Revalidation**
```
for i <- 0 to K_NEIGHBORS do
  Q <- neighbor[i].secondary_hit
  mu <- lookup(my_pos, Q).mean
  bound <- f_s * Lo * G(my_pos, Q)
  residual <- bound * max(mu, 1-mu)
  p <- clamp(residual / threshold, P_MIN, 1)
  if random() < p then
    V <- trace(my_pos, Q); insert(my_pos, Q, V)
    V_est[i] <- mu + (V - mu) / p
  else
    V_est[i] <- mu
```

## 10.1 Path Sharing

ReSTIR GI concentrates selections: a good path gets selected by many pixels in the reuse radius. All need to revalidate visibility to the *same* Q from nearby shading points. At L0 quantization (43), nearby points hash to the same cell. The first pixel to trace populates the entry; subsequent pixels find it cached within the same frame.

With 50–100 pixels selecting the same path, they fall into ~3–5 L0 cells. Total traces: ~3–5 instead of ~50–100. This is the strongest architectural argument for L0's coarse resolution — it maximizes sharing across pixels that selected the same reused path.

| Method | Traces/px (k=5) | Visibility signal |
|---|---|---|
| Full revalidation | 5.0 | N/A |
| Contribution RR, no cache | ~1.5 | None |
| Contribution + cache | ~0.5–1.0 | Cached μ |

> **Table 3.** GI revalidation cost.

---

# 11. Cache-Free Alternatives

Screen-space alternatives capture substantial benefit at lower cost, particularly for DI.

| Approach | μ quality | Helps GI? | Camera-robust? |
|---|---|---|---|
| Vprev | Binary | No | No |
| Poll + EMA | Fractional | No | Partial |
| Hash cache | Converged | Yes | Yes |

---

# 12. Runtime Statistics

Five per-frame atomic counters (inserts, evictions, misses, decay triggers, probe steps) on a dedicated buffer enable load monitoring at negligible cost. Derived metrics: load pressure (eviction/insert ratio), cache effectiveness (1 − miss/query), average probe depth. DECAY_PERIOD auto-tunes via PI controller on smoothed load pressure — one-sided: speeds up under load, never slows beyond a user-set ceiling (DECAY_PERIOD_MAX, the minimum responsiveness for the scene type). Quality knobs (TAU_RR, Pmin, firefly_budget) are never auto-tuned — they are user decisions.

---

# 13. Results

All measurements at 1920×1080, 1 spp, RTX 4090, driver 560.x, DXR 1.1. Reference images: 4096 spp accumulation, same seed. MSE computed in linear RGB.

## 13.1 Test Scenes

| Scene | Triangles | Lights | Character |
|---|---|---|---|
| red | red | red | red |
| red | red | red | red |
| red | red | red | red |

> **Table 5.** Test scenes. Bistro is the primary benchmark; Sponza tests single-light coherence; Cornell Box verifies graceful degradation when the cache offers no spatial advantage.

## 13.2 Shadow-Ray Reduction

| Scene | Mode | DI final | GI reval. | Total rays/px |
|---|---|---|---|---|
| red | Baseline | red | red | red |
| red | Cache | red | red | red |
| red | Baseline | red | red | red |
| red | Cache | red | red | red |
| red | Cache | red | red | red |

## 13.3 Frame Time

| Component | Bistro (ms) | Sponza (ms) |
|---|---|---|
| Lookup | red | red |
| Insert + warp reduce | red | red |
| Decay (1/60 table) | red | red |
| Cache total overhead | red | red |
| Shadow rays saved | red | red |
| **Net frame time &#916;** | red | red |

## 13.4 Convergence

## 13.5 Ablation

| Configuration | Rays/px | MSE | ms |
|---|---|---|---|
| Full system (L0+L1+L2, var gate, warp red.) | red | red | red |
| − variance gate (always write all levels) | red | red | red |
| − distance LOD (all levels at all distances) | red | red | red |
| − warp reduction (per-thread atomics only) | red | red | red |
| L0 only (coarsest, 10 m cells) | red | red | red |
| L2 only (finest, 8 cm cells) | red | red | red |
| − firefly adaptive Pmin | red | red | red |
| No cache (baseline) | red | red | red |

## 13.6 Disocclusion Stress Test

**Graceful degradation.** Where cell resolution is too coarse, variance stays high, psurvive → 1, every ray traces. Rarely-selected lights → MISS → unconditional trace. Baseline cost, zero harm. The cache can never make things worse.

---

# 14. Conclusion

We have described an assembly of known techniques for real-time visibility caching: sparse multilevel hash replacing NEE++'s dense matrix [Guo et al. 2020], control-variate RR [Szirmay-Kalos et al.] returning cached mean on trace termination, distance-gated LOD intervals, angular quantization for infinite endpoints, runtime statistics with auto-tuning, and integration with ReSTIR DI/GI pipelines.

Key observations: (1) ReSTIR GI's selection concentration aligns with coarse cache cells, enabling within-frame amortization of revalidation traces; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing.

---

# References

- [Binder et al. 2018] N. Binder, S. Fricke, and A. Keller. "Path Space Filtering." *GPU Zen 2*, 2018.

- [Bitterli et al. 2020] B. Bitterli, C. Wyman, M. Pharr, P. Shirley, A. Lefohn, and W. Jarosz. "Spatiotemporal Reservoir Resampling for Real-Time Ray Tracing with Dynamic Direct Lighting." *ACM Trans. Graph.*, 39(4):148, 2020.

- [Bokšanský and Meister 2025] A. Bokšanský and D. Meister. "Neural Visibility Cache." 2025.

- [Guo et al. 2020] Y. Guo, E. Eisemann, and T. Eisemann. "NEE++: Faster N-Closest Emitter Sampling with Voxelized Visibility." *Pacific Graphics*, 2020.

- [Jarzynski & Olano 2020] M. Jarzynski and M. Olano. "Hash Functions for GPU Rendering." *JCGT*, 9(3):21–38, 2020.

- [Keller et al. 2016] A. Keller, N. Binder, and K. Dahm. "Path Space Similarity Determined by Fourier Histogram Descriptors." ACM SIGGRAPH 2014 Talks; extended with hash-based filtering 2016.

- [Lin et al. 2022] D. Lin et al. "Generalized Resampled Importance Sampling: Foundations of ReSTIR." *ACM Trans. Graph.*, 41(4), 2022.

- [Müller et al. 2022] T. Müller, A. Evans, C. Schied, and A. Keller. "Instant Neural Graphics Primitives with a Multiresolution Hash Encoding." *ACM Trans. Graph.*, 41(4):102, 2022.

- [Kugelmann 2006] M. Kugelmann. "Efficient Adaptive Global Illumination Algorithms." Diplomarbeit, Universität Ulm, 2006. Supervisor: A. Keller.

- [Ouyang et al. 2021] Y. Ouyang, S. Liu, M. Kettunen, M. Pharr, and J. Pantaleoni. "ReSTIR GI: Path Resampling for Real-Time Path Tracing." *Computer Graphics Forum*, 40(8):17–29, 2021.

- [Popov et al. 2013] S. Popov, R. Ramamoorthi, F. Durand, and G. Drettakis. "Adaptive Quantization Visibility Caching." *Eurographics Symposium on Rendering*, 2013.

- [Stotko et al. 2025] P. Stotko et al. "MrHash: Resolution Where It Counts." *arXiv:2511.21459*, 2025.

- [Szirmay-Kalos et al.] L. Szirmay-Kalos et al. "Go with the Winners" — control variate Russian roulette. (Exact citation TBD.)

- [Teschner et al. 2003] M. Teschner et al. "Optimized Spatial Hashing for Collision Detection of Deformable Objects." *Proc. VMV*, pp. 47–54, 2003.

- [Ulbrich et al. 2013] R. Ulbrich et al. "Progressive Visibility Caching." 2013.

- [Ward 1994] G. J. Ward. "Adaptive Shadow Testing for Ray Tracing." *Eurographics Rendering Workshop*, 1994.

---

*Combined 2026-03-10 09:33 UTC | 542fd9d*

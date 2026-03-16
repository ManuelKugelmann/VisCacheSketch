# 14. Conclusion

We have described a visibility cache that stores
pairwise binary predictions in a flat, multilevel spatial hash table,
corrects them stochastically via prediction-with-correction
(control variate + variance-driven Russian roulette
[Szécsi et al. 2003; Szirmay-Kalos et al. 2005; Kugelmann 2006]),
and operates entirely lock-free on the GPU.
The method is algorithm-agnostic:
it operates on pairwise (point, point) → {0,1} queries
regardless of what generates them.

The key additions, each built on specific prior work:

- **Robust hashing** (modifying [Binder et al. 2018], hash from [Jarzynski & Olano 2020]). Position-seeded jitter replaces cell-index-seeded jitter, converting boundary artifacts from irreducible bias into reducible variance. The jitter is the filter — no explicit smoothing required.

- **Collision handling** (fingerprints from [Binder et al. 2018], lock-free updates informed by [Gautron 2021]). Fingerprint-based detection, double-hash probing (replacing Binder's linear probing), pressure-scaled eviction, inline overflow decay via atomic CAS, and WaveMatch coalescing (SM 6.5).

- **LOD in the hash key** (from [Gautron 2020, 2021]). Level index in the hash input; multiple resolutions in one flat table. Prior multilevel approaches — separate tables [Müller et al. 2022], octree subdivision [Popov et al. 2013], hierarchical cascades — were all more complex and performed worse for our access pattern.

- **Coupled variance adaptation** (extending [Kugelmann 2006]; independently paralleled by [Stotko et al. 2025]). Bernoulli variance (var = μ(1−μ)) requires no separate accumulator. The same signal drives both the correction rate and write-depth gating for spatial resolution. This coupling is self-regulating and only becomes possible with a multilevel cache.

The cache is algorithm-agnostic. We demonstrated integration with ReSTIR DI [Bitterli et al. 2020] and ReSTIR PT [Lin et al. 2022] (which generalizes ReSTIR GI [Ouyang et al. 2021]) as one natural client, but the same cache applies to instant radiosity, classical next-event estimation, or any method evaluating pairwise visibility.

Key observations: (1) ReSTIR spatial reuse concentrates selections onto shared reconnection vertices, aligning with coarse cache cells and enabling within-frame amortization of revalidation traces — but this is a happy property of the integration, not of the cache itself; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing, so the cache can never make things worse.

**Future work.**
Currently the cache only suppresses traces (RR with survival ≤ 1).
Adjoint-driven RR and splitting [Vorba and Křivánek 2016]
and the "go with the winners" family
[Aldous and Vazirani 1994; Grassberger 2002]
suggest the complementary direction:
*splitting* — tracing multiple shadow rays per shading point
for high-variance, high-importance cache entries —
to converge the cache faster in critical regions.
The same importance-weighted framework applies:
where pfloor already reaches 1 and variance remains high,
a splitting factor > 1 could allocate additional traces.
A natural application is light selection:
the cache's per-entry variance signal could weight
reservoir sampling candidates,
preferring lights whose visibility is uncertain
over lights the cache already predicts confidently —
a "go with the winners" strategy applied to light selection
rather than path continuation.
Efficiency-aware adaptation [Rath et al. 2022; Meyer et al. 2024]
could further improve budget allocation
by incorporating per-ray traversal cost,
backing off RR when rays are cheap
and being more aggressive when BVH traversal is expensive.
**Histogram stratification × VisCache.**
Histogram stratification [Salaün et al. 2025]
sorts light candidates by estimated contribution
into histogram bins and applies QMC within each stratum,
reducing variance from O(1/N) to O(1/N²) for smooth integrands.
The visibility cache's per-light μ estimates are composable
with this at the same pipeline stage.
VisCache serves as a cheap visibility oracle
that enables large-K candidate evaluation:
generate K candidate lights,
sort by visibility-weighted contribution f̂ = fs × Le × G × μ (histogram sort),
apply QMC pick on the sorted distribution,
then trace one accurate shadow ray for the winner.
The benefit is multiplicative —
cheaper K evaluations (cache lookup vs. shadow ray)
*and* better distribution (histogram sort over the visibility-informed proposal).
Crucially, the histogram sort operates on the proposal f̂,
while exact evaluation (the traced shadow ray) is applied only to the winner —
so approximate visibility in f̂ does not introduce bias,
only changes sampling efficiency.
This combination of VisCache with histogram stratification
is a novel integration point.

**Multilevel cache for ReSTIR path guiding.**
ReSTIR PG [Zeng et al. 2025] combines ReSTIR with path guiding,
using world-space guiding structures
to inform reservoir candidate generation.
The multilevel hash structure naturally extends beyond binary visibility
to cache richer per-cell statistics —
contribution means, variance, directional histograms —
at multiple spatial resolutions,
providing the world-space guiding signals
that ReSTIR PG requires.
Coarse cells supply robust, well-sampled statistics
for initial candidate generation,
while fine cells refine decisions near geometric detail.
The same variance-gated cascade (Sec. 5) applies:
write guiding statistics to finer levels
only where coarse-level variance justifies the cost.
This generalizes the current binary visibility cache
to a multilevel path guiding cache for ReSTIR PG,
with the same self-regulating budget allocation.

**Connection to Neural Two-Level Monte Carlo.**
Sanzharov et al. [2025] use a neural incident radiance cache (NIRC)
in a Two-Level Monte Carlo (MLMC) scheme
to compensate for cache bias,
with a Balanced Termination Heuristic (BTH) that decides
when to trust the cache vs. trace further —
enabling cache use at the primary bounce,
unlike NRC's spread-angle heuristic.
Their BTH is structurally a stochastic version
of our variance-gated write depth (Sec. 5):
both decide at which level to stop and trust the cache.
Our variance-coupled correction rate (Sec. 8)
maps directly onto the MLMC residual estimator structure —
the control variate returns the cached prediction,
the residual corrects it stochastically.
Combining MLMC with a hash-based visibility cache
would yield unbiased hash-gated visibility
with variance-optimal termination depth,
where both the cache level and the correction rate
are driven by the same variance signal.
Their use of world-space multi-level hash encodings
further parallels our LOD-in-key design (Sec. 4).

**ReSTIR BDPT.**
Lin et al. [2025] extend GRIS to bidirectional path tracing,
enabling caustics via technique-aware extended path space
and caustic reservoirs.
The reconnection vertex data structures from ReSTIR PT
port directly into BDPT's hybrid shift —
and the visibility cache sits on the same shadow ray step.
Caustics specifically require accurate visibility
at specular-diffuse-diffuse paths,
exactly where spatial hash visibility caching has the highest leverage:
these paths concentrate on narrow geometric regions
that align well with fine-level cache cells,
and their high contribution variance
makes the shadow ray cost dominant.
The cache's variance-gated write depth
would naturally allocate fine resolution
to caustic shadow boundaries
while leaving diffuse-dominated regions at coarse levels.

**Independent per-endpoint LOD.**
The current design uses a shared level index —
both endpoints are quantized at the same cell size,
enabling canonicalization (Sec. 4.5).
A natural extension is independent LOD per endpoint:
replacing the 1D key `(qa, qb, lvl)` with a 2D key
`(qa, qb, lvlA, lvlB)`,
where each endpoint is quantized at its own level's cell size.
A sharp shadow boundary from a large area light
needs fine resolution on the shading point
but only coarse resolution on the light —
the entry would live at (lvlA=2, lvlB=0) instead of (2, 2).
A 3-way split variance cascade
(refine A, refine B, refine both)
would determine which (lvlA, lvlB) pairs to populate,
with coarse entries already established as mixed
skipped on insert and left to decay for revalidation.
The current 1D cascade is the diagonal of the N × N LOD grid,
so the extension is backward-compatible.
Canonicalization would require restriction
to the diagonal (lvlA = lvlB) or
symmetric level assignment.

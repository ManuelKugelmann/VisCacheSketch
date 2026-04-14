# 14. Conclusion

We have described a visibility cache that stores
pairwise binary predictions in a flat, multilevel spatial hash table,
corrects them stochastically via prediction-with-correction
(control variate + variance-driven Russian roulette
[Szécsi et al. 2003; Szirmay-Kalos et al. 2005; Kugelmann 2006]),
and operates entirely lock-free on the GPU.
The method is algorithm-agnostic:
it operates on pairwise visibility queries
regardless of what generates them.

The key additions, each built on specific prior work:

- **Position+normal × direction+distance addressing.** The hash key decomposes the query into shading-point identity (position + surface normal) and query geometry (direction + distance), exploiting free geometric information that position × position keys cannot. Normal disambiguates thin geometry; direction provides an angular LOD axis; distance monotonicity enables free multi-write from a single any-hit ray.

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

**MegaLights pipeline integration.**
MegaLights [Conner et al. 2025] (Epic/UE5)
is a stochastic tile-based direct lighting system
enabling many dynamic shadowed area lights
through a scalable, hardware-conscious pipeline.
Its architectural pattern — tile-based candidate pools
with stochastic selection — is composable
with histogram stratification [Salaün et al. 2025]:
MegaLights generates the candidate pool,
histogram stratification improves which candidates get selected,
and the visibility cache provides the μ oracle
for visibility-weighted sorting.
The three components operate at different pipeline stages
and compose without modification to each other.

**Path space filtering with multilevel hash and correction.**
Path space filtering [Binder and Keller 2019]
uses a spatial hash over path space
to cache and filter full path contributions —
a predecessor to SHaRC and closely related
to the spatial hash lineage of this work.
The visibility cache is path space filtering
restricted to the visibility factor.
Three additions from this work apply directly
to general path space filtering:
(1) a multilevel hash map with LOD in the key (Sec. 4),
giving resolution-adaptive filtering in one flat table;
(2) variance-gated write depth (Sec. 5),
so the cache self-regulates which levels receive updates
based on local filter quality;
(3) prediction-with-correction (Sec. 8),
using cached path contributions as control variate
with RR on the residual to maintain unbiasedness —
the filtered estimate is returned on RR termination
instead of zero, and only traced paths update the cache.
This would turn path space filtering
from a biased filter into an unbiased estimator
with variance-optimal spatial resolution.

**Real-time Markov chain path guiding.**
Alber et al. [2025] propose lightweight unbiased path guiding
for real-time applications using MCMC,
avoiding costly fitting procedures
and hierarchical spatial data structures
that are inefficient on GPU architectures.
The visibility cache is orthogonal:
it operates on pairwise (point, point) → {0,1} queries
regardless of how those points were generated —
whether by MCMC path guiding, ReSTIR, or any other sampler.

**2D LOD cascade (spatial × angular).**
The position+normal × direction+distance addressing (Sec. 4.1)
has two independent LOD axes: spatial cell size and angular bin size.
The full LOD grid is N × N (spatial\_lvl, angular\_lvl) pairs.
We propose a diagonal-first exploration scheme:

1. Walk the diagonal (0,0) → (1,1) → (2,2),
   advancing both axes together.
   Cost: N lookups — identical to the current 1D cascade.
2. At the terminal diagonal level (k,k),
   if variance is still high,
   probe the two off-diagonal neighbors (k+1,k) and (k,k+1)
   to determine which axis needs finer resolution.
   Cost: +2 lookups.
3. A max\_diff constraint (|spatial\_lvl − angular\_lvl| ≤ 1)
   prevents the two axes from diverging too far.
   A fine spatial cell with a coarse angular bin
   (or vice versa) wastes the finer resolution
   because the coarser axis dominates the variance.

The three-state cascade (Sec. 5) applies to each (s, a) pair:
a child entry (s+1, a+1) on the diagonal starts receiving writes
once its parent (s, a) is useable (not necessarily mature).
New child entries inherit the parent's μ as initial data
at reduced weight (equivalent to a few decay steps),
so the child starts with a reasonable control variate
rather than bootstrapping from zero.
The parent continues refining in parallel;
writes stop only when the parent reaches maturity.

Off-diagonal children follow the same rule:
(k+1, k) starts when (k, k) is useable and spatial variance is high;
(k, k+1) starts when (k, k) is useable and angular variance is high.
The common case (both axes equally needed) stays on the diagonal
at current cost; off-diagonal exploration only fires
at the terminal level when the diagonal answer isn't sufficient.

**Independent per-endpoint LOD.**
A further extension replaces the shared level index with a 2D key
`(qa, qb, lvlA, lvlB)`,
where each endpoint is quantized at its own level's cell size.
A sharp shadow boundary from a large area light
needs fine resolution on the shading point
but only coarse resolution on the light —
the entry would live at (lvlA=2, lvlB=0) instead of (2, 2).
The current 1D cascade is the diagonal of this N × N grid,
so the extension is backward-compatible.

**Distance-bin multi-write implementation.**
The distance monotonicity described in Sec. 4.1
(V=0 at d implies V=0 at all d' > d)
enables free propagation across distance bins on every trace.
The current implementation writes only the queried distance bin;
extending the insert path to propagate along the distance column
— V=0 to all farther bins from d\_hit, V=1 to all nearer bins from d\_query —
is a pure implementation task with no algorithmic risk.
The variance gate applies to propagation targets:
skip bins that already agree with the propagated value.

**Per-cell distance prior for collapsed-distance addressing.**
When the distance axis is collapsed in the hash key
(`dir_dist1`-style addressing, single distance bucket per `(posA, dir)` bin),
rays of very different lengths pool into the same cell
and the cached μ averages short-ray and long-ray visibility together.
Under the surface-target assumption
(V=1 implies the ray reached its target surface at tMax,
with no volumetric scattering past that point),
every V=1 sample with ray length L is a verified occluder-free segment (0, L)
for that bin's direction.
An auxiliary per-cell `clearDist = max(tMax | V=1)` —
stored as a parallel `RWBuffer<uint>` indexed by slot,
updated via `InterlockedMax(asuint(tMax))` on V=1 inserts,
reset to 0 on eviction —
records the longest verified clear-path length in the bin.
At lookup, a query ray shorter than `clearDist`
can be predicted visible (μ→1, var→0) with geometric justification:
under bin-homogeneity in the direction quantization,
a shorter ray is contained within a previously cleared segment.
The CV+RRR estimator remains unbiased regardless of μ accuracy
(see Sec. 8), so an incorrect override
(quantization heterogeneity, thin grazing blockers)
only affects variance, not expectation.
The complementary V=0 statistic —
`nearestBlocker = min(tMax | V=0)` — is an upper bound on the true blocker distance
(the blocker lies somewhere in (0, tMax], not at tMax itself),
so it cannot cleanly drive an override:
the blocker could always be closer than any observed blocked ray.
The V=1 direction gives the stronger signal.
The open question is whether the per-slot storage overhead
(one additional 32-bit field per entry, roughly 16 MB at a 4M-entry table)
buys enough variance reduction in collapsed-distance regimes
to beat proper distance binning (`dir_dist`);
in the general case, allocating that same storage
to finer distance bins in the key itself is likely a better trade.

**Sentinel traces for dynamic scene detection.**
The Pmin floor (Sec. 8) already forces ~5% of pixels
to trace unconditionally, paying the ray cost regardless of cache state.
Currently these traces feed into the normal update pipeline,
slowly shifting μ.
A zero-cost extension: Pmin-forced traces that disagree
with the cached estimate by more than a sentinel threshold
(e.g. |V − μ| > 0.5, tuneable)
bypass the maturity gate (Sec. 5),
forcing a write even to mature entries.
Agreeing sentinels respect the maturity gate as normal —
only disagreement warrants overriding it.
This turns the existing 5% always-trace budget
into an implicit change detector —
if the scene changes and a mature entry becomes stale,
disagreeing Pmin traces correct it at a rate of Pmin × frame_rate
(~3 updates/second per cell at 60 fps),
without needing explicit invalidation logic
or a separate probe pass.
Combined with inline overflow decay (Sec. 6),
which keeps total counts bounded so new observations shift μ quickly,
this provides O(1)-second response to local scene changes
while leaving stable regions at full maturity.
The current background decay (Sec. 6) becomes a global safety net
rather than the primary change-response mechanism.

**Interpolatable visibility field.**
Each occupied cell is a noisy sample of a continuous visibility field V(a,b),
located at the cell's effective center,
with known value (μ) and known uncertainty (μ(1−μ)/n).
Reframing the hash table as a set of scattered spatial samples
opens the path to explicit interpolation at lookup time:
query K neighboring cells and blend by distance and confidence,
e.g. w_i = n_i / (1 + d_i² / cell_size²).
At coarse levels (L0, 10 m cells),
discrete jumps at cell boundaries are large
and neighbors are likely populated —
interpolation over 8 cube-corner neighbors
costs ~8 hash lookups (~100 ALU + 8 cache lines),
trivial compared to a shadow ray.
At fine levels (L2, 16 cm cells),
the current position-seeded jitter (Sec. 4.2)
already provides sufficient stochastic smoothing at near-pixel scale.
A practical rule: interpolate at coarse levels, jitter-filter at fine levels.
The interpolated L0 μ has lower variance than any single cell's μ,
so the variance-gated cascade stops earlier,
potentially saving fine-level lookups.
This reframes the cache from a discrete lookup structure
to a sparse spatial reconstruction of the visibility field
from noisy Bernoulli observations —
prediction-with-correction then maintains reconstruction quality
by tracing where reconstruction uncertainty is high.

**Double jitter: grid jitter + point jitter.**
The current position-seeded jitter (Sec. 4.2) smooths cell boundary transitions
but leaves the grid itself regular —
cell centers remain on a uniform axis-aligned lattice.
A two-stage jitter separates two independent jobs:
(1) *grid jitter* displaces each cell's effective center
by a deterministic hash of its quantized coordinates,
breaking axis-aligned regularity
so that scene features (walls, floors)
do not systematically align with cell boundaries;
(2) *point jitter* (the existing position-seeded jitter)
provides the boundary box filter independently.
Neither stage alone achieves both properties:
grid jitter without point jitter recreates Binder et al.'s [2018] sharp boundary steps
at irregularly placed boundaries;
point jitter without grid jitter leaves axis-aligned grid structure.
Double jitter is particularly beneficial
for the interpolatable-field extension above:
on a regular lattice, neighboring cell centers are maximally correlated
and interpolation degenerates toward trilinear on a grid;
with grid jitter, cell centers form a quasi-random sample set,
giving more independent information per neighbor
and reducing interpolation variance.

**Multi-lookup smoothing and inter-level interpolation.**
Currently each query performs a single coarse-to-fine cascade
and returns the best matching entry.
An alternative is to evaluate multiple lookups —
either at jittered positions within the cell neighborhood
or by interpolating between adjacent levels —
and average the resulting μ values.
This is analogous to the Nc > 1 cheap-sample strategy
in Neural Two-Level MC [Dereviannykh et al. 2024],
where multiple neural cache evaluations (2–25× cheaper than a trace)
are averaged to reduce residual variance
before a single expensive correction sample.
Hash lookups are even cheaper than neural evaluations,
so the cost of multi-lookup averaging is near zero.
Inter-level interpolation (blending μ from adjacent LOD levels
weighted by their sample counts)
would smooth the discrete LOD transitions
that the current cascade produces,
similar to trilinear interpolation
in neural hash encodings [Müller et al. 2022]
and roughness-gated blending in SHaRC [Benyoub et al. 2024].
The position jitter (Sec. 4) already provides stochastic smoothing
across cell boundaries within a single level;
multi-lookup and inter-level interpolation
would extend this smoothing across levels
and across multiple cells per query.

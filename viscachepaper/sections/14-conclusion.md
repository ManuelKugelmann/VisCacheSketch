# 14. Conclusion

Twenty years ago, a thesis [Kugelmann 2006]
cached pairwise binary visibility in spatial grids —
backed by spatial hashing [Teschner et al. 2003] in the accompanying code,
though not described in the thesis text —
and corrected predictions via variance-driven adaptive sampling,
a technique called prediction-with-correction
(control variate + Russian roulette on the residual;
non-zero termination estimate [Szécsi et al. 2003];
variance-driven RR from "go with the winners" [Szirmay-Kalos et al. 2005]).
The thesis developed many cache experiments —
visibility prediction, contribution prediction, and others —
as part of a broader framework for adaptive global illumination.
Instant radiosity [Keller 1997] was the test case,
but the method was always algorithm-agnostic:
it operates on pairwise (point, point) → {0,1} queries
regardless of what generates them.
The idea was sound but limited by
fixed-resolution single-level hashing and offline CPU execution.
We have described the engineering —
drawing on two decades of developments in GPU hashing,
lock-free atomics, and multilevel spatial data structures —
required to make it practical in a real-time path tracer.

The key additions, each built on specific prior work:

- **Robust hashing** (modifying [Binder et al. 2018], hash from [Jarzynski & Olano 2020]). Position-seeded jitter replaces cell-index-seeded jitter, converting boundary artifacts from irreducible bias into reducible variance. The jitter is the filter — no explicit smoothing required.

- **Collision handling** (fingerprints from [Binder et al. 2018], lock-free updates informed by [Gautron 2021]). Fingerprint-based detection, double-hash probing (replacing Binder's linear probing), pressure-scaled eviction, inline overflow decay via atomic CAS, and WaveMatch coalescing (SM 6.5).

- **LOD in the hash key** (from [Gautron 2020, 2021]). Level index in the hash input; multiple resolutions in one flat table. Prior multilevel approaches — separate tables [Müller et al. 2022], octree subdivision [Popov et al. 2013], hierarchical cascades — were all more complex and performed worse for our access pattern.

- **Coupled variance adaptation** (extending [Kugelmann 2006]'s adaptive sampling; independently paralleled by [Stotko et al. 2025]). [Kugelmann 2006] already used variance to drive the correction rate. We narrow to binary visibility where Bernoulli variance (var = μ(1−μ)) requires no separate variance estimator — an optimization not exploited in the original thesis — and add a second use of the same signal: write-depth gating drives spatial resolution. This coupling is self-regulating and only becomes possible with a multilevel cache.

The cache is algorithm-agnostic. We demonstrated integration with ReSTIR DI and GI [Bitterli et al. 2020; Ouyang et al. 2021] as one natural client, but the same cache applies to instant radiosity (as in the original thesis), classical next-event estimation, or any method evaluating pairwise visibility.

Key observations: (1) ReSTIR GI's selection concentration aligns with coarse cache cells, enabling within-frame amortization of revalidation traces — but this is a happy property of the integration, not of the cache itself; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing, so the cache can never make things worse.

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

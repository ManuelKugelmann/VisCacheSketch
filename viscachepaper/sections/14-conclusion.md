# 14. Conclusion

This paper completes work begun twenty years ago. The core algorithm — cache pairwise visibility in a spatial hash [Teschner et al. 2003], correct predictions via variance-driven adaptive sampling (prediction-with-correction [Kugelmann 2006]; reducing RR variance via non-zero termination [Szécsi et al. 2003]; "go with the winners" [Szirmay-Kalos et al. 2005]) — was proposed in [Kugelmann 2006] as part of a thesis on adaptive global illumination that developed many cache experiments, including visibility prediction and contribution prediction. Instant radiosity [Keller 1997] was the 2006 test case, but the method was always algorithm-agnostic: it operates on pairwise (point, point) → {0,1} queries regardless of what generates them. The idea was sound but limited by fixed-resolution single-level hashing and offline CPU execution. We have described the engineering — drawing on two decades of developments in GPU hashing, lock-free atomics, and multilevel spatial data structures — required to make it practical in a real-time path tracer.

The key additions, each built on specific prior work:

- **Robust hashing** (modifying [Binder et al. 2018], hash from [Jarzynski & Olano 2020]). Position-seeded jitter replaces cell-index-seeded jitter, converting boundary artifacts from irreducible bias into reducible variance. The jitter is the filter — no explicit smoothing required.

- **Collision handling** (fingerprints and probing from [Binder et al. 2018], lock-free patterns from [Gautron 2021]). Fingerprint-based detection, double-hash probing, pressure-scaled eviction, inline overflow decay via atomic CAS, and WaveMatch coalescing (SM 6.5).

- **LOD in the hash key** (from [Gautron 2020, 2021]). Level index in the hash input; multiple resolutions in one flat table. Prior multilevel approaches — separate tables [Müller et al. 2022], octree subdivision [Popov et al. 2013], hierarchical cascades — were all more complex and performed worse for our access pattern.

- **Coupled variance adaptation** (extending [Kugelmann 2006]'s adaptive sampling; independently paralleled by [Stotko et al. 2025]). [Kugelmann 2006] already used variance to drive the correction rate. We narrow to binary visibility where Bernoulli variance (var = μ(1−μ)) requires no separate variance estimator — an optimization not exploited in the original thesis — and add a second use of the same signal: write-depth gating drives spatial resolution. This coupling is self-regulating and only becomes possible with a multilevel cache.

The cache is algorithm-agnostic. We demonstrated integration with ReSTIR DI and GI [Bitterli et al. 2020; Ouyang et al. 2021] as one natural client, but the same cache applies to instant radiosity (as in the original thesis), classical next-event estimation, or any method evaluating pairwise visibility.

Key observations: (1) ReSTIR GI's selection concentration aligns with coarse cache cells, enabling within-frame amortization of revalidation traces — but this is a happy property of the integration, not of the cache itself; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing, so the cache can never make things worse.

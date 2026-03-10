# 14. Conclusion

This paper completes work begun twenty years ago. The core algorithm — cache pairwise visibility in a spatial hash, correct predictions via CV+RRR — was proposed in [Kugelmann 2006] and applied to shadow-ray reduction in instant radiosity. The idea was sound but limited by fixed-resolution single-level hashing and offline CPU execution. We have described the engineering required to make it practical in a real-time GPU path tracer.

The key additions developed in the intervening years:

- **Robust hashing.** Position-seeded jitter that acts as an intrinsic box filter across cell boundaries, eliminating the systematic boundary artifacts of cell-index-seeded approaches [Binder et al. 2018]. The jitter is the filter — no explicit smoothing required.

- **Collision handling.** Fingerprint-based detection with double-hash probing, pressure-scaled eviction that self-heals probe chains, inline overflow decay via atomic CAS, and WaveMatch coalescing (SM 6.5) for contention reduction.

- **LOD in the hash key.** Following Gautron [2020, 2021], the level index is part of the hash input. Multiple resolutions coexist in one flat table with no indirection. Prior multilevel approaches — separate tables, octrees, hierarchical cascades — were all more complex and performed worse for our access pattern.

- **Coupled variance adaptation.** The Bernoulli variance signal drives both correction rate (RR survival probability) and spatial resolution (write-depth gate) simultaneously. This coupling is self-regulating and only becomes possible with a multilevel cache — [Kugelmann 2006] had fixed resolution, so only the correction rate adapted.

The cache is algorithm-agnostic. We demonstrated integration with ReSTIR DI and GI pipelines, but ReSTIR is an integration target, not a contribution — the same cache applies to instant radiosity (as in the original thesis), classical next-event estimation, or any method evaluating pairwise visibility.

Key observations: (1) ReSTIR GI's selection concentration aligns with coarse cache cells, enabling within-frame amortization of revalidation traces — but this is a happy property of the integration, not of the cache itself; (2) contribution-weighted RR gates revalidation by perceptual importance rather than raw visibility variance; (3) the design degrades gracefully — every failure mode falls back to unoptimized baseline tracing, so the cache can never make things worse.

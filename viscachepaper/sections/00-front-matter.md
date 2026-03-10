# Multilevel Visibility Hash Filter
## Variance-Driven Shadow Ray Caching for Real-Time Path Tracing

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

We present a multilevel spatial hash table that caches pairwise visibility between surface regions and light regions for real-time path tracing. The cached mean serves as a control variate with Russian roulette residual (CV+RRR) — a classical technique that makes shadow-ray gating provably unbiased regardless of cache accuracy — forming a self-regulating loop that concentrates traces on shadow boundaries. Multiple LOD levels are written simultaneously and selected per query by screen-space cell footprint. We integrate the cache with ReSTIR DI and GI pipelines: cached visibility informs light selection, gates final shading shadow rays, and enables contribution-weighted revalidation that approaches biased-skip cost while preserving unbiasedness. Initial profiling on Bistro exterior shows **##%** shadow-ray reduction in direct illumination and **##%** in GI revalidation, with no measurable bias and negligible cache-maintenance overhead.

**Keywords:** visibility caching, shadow rays, spatial hashing, control variate, Russian roulette, ReSTIR, real-time rendering

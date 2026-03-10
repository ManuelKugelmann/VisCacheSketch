# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

Twenty years ago, a thesis [Kugelmann 2006] proposed caching pairwise binary visibility in a spatial hash table and correcting predictions via control-variate Russian roulette residual (CV+RRR) — an unbiased estimator regardless of cache quality. The idea was promising but limited by fixed-resolution single-level hashing and offline CPU rendering. This paper completes that work. We describe the engineering required to make it practical in a real-time GPU path tracer: robust hash addressing with position-seeded jitter that acts as an intrinsic box filter across cell boundaries, fingerprint-based collision detection with double-hash probing, LOD level encoded directly into the hash key so that multiple resolutions coexist in one flat table, and variance-driven write-depth gating that couples spatial resolution to correction rate — a feedback loop only possible with a multilevel cache. We show that ReSTIR DI and GI pipelines [Bitterli et al. 2020; Ouyang et al. 2021] are a natural but orthogonal integration target: the cache reduces shadow-ray cost for any method that evaluates pairwise visibility, whether ReSTIR, instant radiosity [Kugelmann 2006], or classical next-event estimation. Initial profiling on Bistro exterior shows **##%** shadow-ray reduction in direct illumination and **##%** in GI revalidation, with no measurable bias and negligible cache-maintenance overhead.

**Keywords:** visibility caching, shadow rays, spatial hashing, control variate, Russian roulette, real-time rendering, collision handling

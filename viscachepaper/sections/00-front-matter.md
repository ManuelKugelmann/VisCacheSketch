# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

We present a world-space visibility cache
that predicts binary shadow-ray outcomes
and corrects errors stochastically,
yielding an unbiased estimator regardless of cache quality.
The cache is a single flat hash table
storing per-cell hit/miss ratios in 8 bytes,
updated lock-free with single-InterlockedAdd atomics.
Position-seeded jitter acts as an intrinsic box filter
across cell boundaries,
fingerprint-based double hashing handles collisions,
and LOD level encoded in the hash key
lets multiple resolutions coexist without indirection.
Variance is obtained for free from the Bernoulli mean (var = μ(1−μ))
and drives both the correction rate
and write-depth gating across levels.
The cache is algorithm-agnostic;
we demonstrate it with ReSTIR DI and GI
but it applies to any pairwise visibility query.
On Bistro exterior, shadow rays drop by
**##%** (direct) and **##%** (GI revalidation),
with no measurable bias.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

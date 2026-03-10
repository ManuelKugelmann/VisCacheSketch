# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

Most shadow rays in real-time path tracing are redundant,
as nearby surface points querying the same light region
overwhelmingly agree on the outcome.
We store these binary predictions in a flat, multilevel spatial hash table
with 8-byte entries and lock-free atomic updates,
and correct cached predictions stochastically
so that the estimator remains unbiased regardless of cache quality.
Position-seeded jitter provides an intrinsic box filter across cell boundaries,
while variance derived from the Bernoulli mean alone
drives both the correction rate and the write depth across levels.
Integrated with ReSTIR DI and GI on Bistro exterior,
the cache reduces shadow rays by
**##%** (direct) and **##%** (GI revalidation)
with no measurable bias.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

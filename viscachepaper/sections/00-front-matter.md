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
with 8-byte entries, lock-free atomic updates,
multilevel resolution without indirection,
and variance derived for free from the Bernoulli mean.
It is algorithm-agnostic;
we demonstrate it with ReSTIR DI and GI.
On Bistro exterior, shadow rays drop by
**##%** (direct) and **##%** (GI revalidation),
with no measurable bias.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

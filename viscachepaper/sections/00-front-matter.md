# Visibility Prediction-with-Correction for Real-Time Path Tracing
## Unbiased Adaptive Shadow Ray Reduction with a Filtered Multi-Level Hash Cache

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

Most shadow rays in real-time path tracing are redundant,
as nearby surface points querying the same light region
overwhelmingly agree on the outcome.
We store binary visibility predictions in a flat, multilevel spatial hash table
with 8-byte entries and lock-free atomic updates,
keyed by shading-point position and surface normal
on one side and query direction and distance on the other.
This decomposition exploits free geometric information:
normals disambiguate thin geometry,
direction enables angular LOD,
and distance monotonicity allows a single any-hit ray
to propagate results across multiple distance bins at zero cost.
Cached predictions are corrected stochastically
so that the estimator remains unbiased regardless of cache quality.
Position-seeded jitter provides an intrinsic box filter across cell boundaries,
while variance derived from the Bernoulli mean alone
drives both the correction rate and the spatial write depth —
a coupled dual adaptation that makes the cache self-regulating.
The cache is algorithm-agnostic but pairs naturally with ReSTIR,
whose spatial reuse funnels many pixels onto the same lights
and therefore the same visibility queries.
On Bistro exterior with ReSTIR DI and GI,
shadow rays drop by
**##%** (direct) and **##%** (GI revalidation)
with no measurable bias.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

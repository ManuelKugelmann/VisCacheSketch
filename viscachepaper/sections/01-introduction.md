# 1. Introduction

Shadow rays dominate the cost of direct lighting in real-time path tracing.
Most confirm what nearby rays already established:
a surface region is consistently lit or consistently occluded from a light region.
The core idea of this paper —
cache point-to-point visibility in spatial grids and gate shadow rays via
*prediction-with-correction* [Kugelmann 2006]
(CV+RR; non-zero termination estimate [Szécsi et al. 2003],
variance-driven RR [Szirmay-Kalos et al. 2005]) —
is twenty years old.
Kugelmann [2006] developed it as part of a thesis on adaptive global illumination
with a general *prediction-with-correction* framework applied through
many explorative cache experiments —
visibility prediction, contribution prediction, and others —
with generalized variance-driven adaptive sampling already built in.
The spatial grids were visible in the thesis results,
but the underlying spatial hashing [Teschner et al. 2003] —
inspired by Teschner's work to sidestep the curse of dimensionality
in naive grids — was an unmentioned implementation detail;
the contribution was the per-point cached estimation source
and the variance-driven adaptive sampling loop.
The test case was instant radiosity,
but the method was always algorithm-agnostic —
it operates on pairwise (point, point) → {0,1} visibility queries
regardless of what generates them.
Prediction-with-correction makes the estimator provably unbiased
regardless of cache quality,
but the thesis used fixed-resolution single-level grids on the CPU,
with generalized variance driving only the correction rate,
not spatial resolution.

This paper completes that work.
The intervening two decades brought GPU ray tracing hardware,
wave intrinsics for lock-free parallel hashing, and the ReSTIR framework —
but the algorithmic core remains:
cache a visibility prediction, correct it stochastically,
and let the variance signal self-regulate the trace rate.
By narrowing to binary visibility we gain Bernoulli structure —
variance free from the mean alone —
an optimization unavailable in the thesis's general-variance framework.
What is new is the engineering to make this robust and practical:

- **Robust hash addressing**
  (building on [Binder et al. 2018], hash quality from [Jarzynski & Olano 2020]).
  Binder et al. introduced jitter-before-quantize spatial hashing
  with fingerprint collision detection and linear probing
  for path-space filtering.
  We adopt their hash table mechanics but change the jitter seed
  from cell index to unquantized position bits
  (pcg3d [Jarzynski & Olano 2020]).
  The change eliminates systematic boundary artifacts
  (sharp steps at cell edges)
  and replaces them with probabilistic cell membership —
  an intrinsic box filter.
  The jitter *is* the filter:
  nearby points near a cell boundary probabilistically map to adjacent cells,
  producing smooth transitions that reduce with sample count
  rather than persisting as irreducible bias.
  See Sec. 4.

- **Collision handling**
  (fingerprints and probing from [Binder et al. 2018],
  lock-free GPU updates informed by [Gautron 2021]).
  Fingerprint-based collision detection (from Binder)
  with double-hash probing (our replacement for their linear probing),
  pressure-scaled eviction that self-heals long probe chains,
  and inline overflow decay via atomic CAS
  that keeps counters bounded while preserving the mean ratio.
  The 8-byte entry format (fingerprint + packed counters)
  enables single-InterlockedAdd updates
  and WaveMatch coalescing (SM 6.5)
  for ~16× reduction in atomic contention at coarse levels.
  See Secs. 3, 5, 6.

- **LOD in the hash key** (from [Gautron 2020, 2021]).
  Gautron demonstrated LOD level encoded directly into the hash function
  for real-time AO, with distance-based cell selection.
  We adopt this directly:
  multiple resolution levels coexist in one flat table —
  no separate tables, no tree structure, no indirection.
  Distance-gated level selection acts as a clipmap:
  coarse cells for far field, fine cells for near field.
  Prior multilevel hash approaches —
  separate tables per level [Müller et al. 2022],
  octree-like subdivision [Popov et al. 2013], hierarchical indirection —
  were all more complex and performed worse for this use case.
  See Secs. 3, 5.

- **Coupled variance adaptation**
  (extending [Kugelmann 2006]'s adaptive sampling;
  independently paralleled by [Stotko et al. 2025]).
  [Kugelmann 2006] already used variance to drive the correction rate
  (RR survival probability) — this was its adaptive sampling.
  We narrow to binary visibility where Bernoulli variance (var = μ(1−μ))
  requires no separate variance estimator —
  an optimization not exploited in the original thesis.
  We add a second use of the same signal:
  the write-depth gate drives spatial resolution —
  whether fine-level cache entries are updated.
  High-variance regions trace more often *and* update fine levels;
  low-variance regions trace rarely *and* only update the coarsest level.
  Stotko et al. [2025] (MrHash) independently developed
  variance-driven resolution allocation for TSDF hashing —
  the same principle in a different domain.
  This coupling only becomes possible with a multilevel cache.
  See Sec. 8.

The cache is agnostic to what generates the visibility queries.
We demonstrate integration with ReSTIR DI and GI
[Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022],
but ReSTIR is not related work — it is one of many possible clients.
The same cache applies equally to instant radiosity
(as in the original thesis [Kugelmann 2006]),
classical next-event estimation,
or any algorithm that evaluates pairwise point-to-point visibility.
ReSTIR happens to be a particularly good fit
because spatial reuse concentrates many pixels
onto the same light or secondary hit,
and a world-space cache amortizes their shared visibility queries automatically.

Our contributions are therefore not algorithmic novelty but *completion*:
(1) robust hashing with position-seeded jitter
that eliminates cell-boundary bias,
fingerprint-based collision detection, and pressure-scaled eviction;
(2) LOD integrated into the hash key
with variance-driven write-depth gating —
coupled adaptation that was impossible at fixed resolution;
(3) a demonstration that the cache integrates cleanly
with modern path-tracing pipelines (ReSTIR DI/GI) as well as classical ones,
reducing shadow rays without introducing bias.

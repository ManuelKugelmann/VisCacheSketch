# 1. Introduction

Most shadow rays in real-time path tracing are redundant.
Nearby surface points asking about the same light region
overwhelmingly agree on the answer — lit or blocked —
yet each fires its own ray.
A world-space cache that remembers these answers
and only re-traces where the outcome is uncertain
can eliminate the majority of shadow work
without disturbing the estimator.

The idea is not new.
Kugelmann [2006] built exactly this system — spatial hash grids
storing per-cell visibility predictions, corrected stochastically
to preserve unbiasedness — as part of a broader thesis
on adaptive global-illumination sampling.
That work explored many cache flavours
(visibility, contribution, combined)
within a general prediction-with-correction framework,
using variance to throttle the correction rate.
It ran on the CPU, used a single grid resolution,
and demonstrated the concept on instant radiosity.
The spatial hashing itself [Teschner et al. 2003] was treated
as plumbing, not contribution —
the point was the cached estimator and its adaptive loop.

What has changed is the platform, not the principle.
GPU ray-tracing hardware, wave intrinsics for lock-free atomics,
and the ReSTIR framework [Bitterli et al. 2020; Ouyang et al. 2021]
now make the approach both practical and urgent:
ReSTIR's spatial reuse funnels many pixels
onto the same light or secondary hit,
and a world-space cache amortizes their shared queries naturally.

This paper revisits the 2006 prototype
with two decades of hashing and GPU advances:

- **Position-seeded jitter** replaces Binder et al.'s [2018]
  cell-index jitter with pcg3d [Jarzynski & Olano 2020]
  seeded from unquantized position bits.
  Nearby points near a cell boundary probabilistically map
  to adjacent cells — an intrinsic box filter
  that smooths transitions instead of producing
  the sharp steps of deterministic quantization.
  See Sec. 4.

- **Fingerprint collision handling** adopts Binder et al.'s [2018]
  fingerprint-based detection but replaces linear probing
  with double hashing, adds pressure-scaled eviction
  to self-heal long probe chains,
  and uses inline overflow decay via atomic CAS
  to keep counters bounded while preserving the mean ratio.
  An 8-byte entry format enables single-InterlockedAdd updates
  and WaveMatch coalescing (SM 6.5) for ~16× reduction
  in atomic contention at coarse levels.
  See Secs. 3, 5, 6.

- **LOD in the hash key**, following Gautron [2020, 2021],
  encodes resolution level directly into the hash function
  so multiple levels coexist in one flat table —
  no separate tables, no tree, no indirection.
  Distance-gated level selection acts as a clipmap.
  See Secs. 3, 5.

- **Coupled variance adaptation** extends the original thesis's
  variance-driven correction rate with a second feedback channel:
  the same Bernoulli signal (var = μ(1−μ), no separate accumulator needed)
  now also gates write depth —
  each level's variance controls whether the next finer level is written.
  High-variance regions trace more *and* cascade to fine resolution;
  stable regions stop propagation early.
  Stotko et al. [2025] independently developed the same principle
  for TSDF hashing.
  See Sec. 8.

The cache is agnostic to its client algorithm.
We demonstrate it with ReSTIR DI and GI,
but it applies equally to classical next-event estimation,
instant radiosity (as in the original thesis),
or any system that evaluates pairwise point-to-point visibility.

Our contribution is therefore *completion*, not invention:
robust hashing that eliminates cell-boundary bias,
collision handling that scales on the GPU,
multilevel resolution with variance-driven gating,
and a clean integration path for modern path-tracing pipelines —
reducing shadow rays without introducing bias.

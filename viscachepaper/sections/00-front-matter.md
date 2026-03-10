# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

Twenty years ago, a thesis [Kugelmann 2006] cached pairwise binary visibility
in spatial grids and corrected predictions via variance-driven adaptive sampling —
a technique called *prediction-with-correction*
(control variate + Russian roulette on the residual;
non-zero termination estimate formalized for rendering by
[Szécsi et al. 2003],
variance-driven RR by [Szirmay-Kalos et al. 2005]) —
yielding an unbiased estimator regardless of cache quality.
The spatial grids were visible in the thesis results,
but the underlying spatial hashing — inspired by Teschner et al. [2003]
to sidestep the curse of dimensionality in naive grids —
was an unmentioned implementation detail;
the thesis contribution was applying CV+RR with per-point cached predictions
and generalized variance-driven adaptive sampling to visibility.
The method was demonstrated on instant radiosity but was always algorithm-agnostic.
It used fixed-resolution single-level grids on the CPU,
with generalized variance driving only the correction rate.

This paper completes that work by replacing the naive grid
with formal spatial hashing [Teschner et al. 2003]
and integrating improvements developed in the intervening decades:
robust hash addressing with position-seeded jitter
[Binder et al. 2018, modified] that acts as an intrinsic box filter
across cell boundaries,
fingerprint-based collision detection [Binder et al. 2018]
with double-hash probing [Knuth 1973],
LOD level encoded directly into the hash key [Gautron 2020]
so that multiple resolutions coexist in one flat table,
variance-driven write-depth gating inspired by concurrent work
on adaptive hash resolution [Stotko et al. 2025],
and GPU-parallel lock-free updates [Gautron 2021]
with pcg3d hashing [Jarzynski & Olano 2020].
By narrowing from the thesis's general framework to binary visibility,
we exploit Bernoulli structure:
variance is free from the mean alone (var = μ(1−μ)),
eliminating the separate variance accumulator.
We demonstrate integration with ReSTIR DI and GI
[Bitterli et al. 2020; Ouyang et al. 2021] as one natural client,
but the cache applies equally to classical next-event estimation
or any pairwise visibility query.
Initial profiling on Bistro exterior shows
**##%** shadow-ray reduction in direct illumination
and **##%** in GI revalidation,
with no measurable bias and negligible cache-maintenance overhead.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

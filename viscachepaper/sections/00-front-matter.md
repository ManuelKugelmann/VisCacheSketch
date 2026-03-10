# Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing
## Robust Hashing, Collision Handling, and ReSTIR Integration for a Two-Decade-Old Idea

**M. Kugelmann**

*Draft — March 2026*

---

### Abstract

Twenty years ago, a thesis [Kugelmann 2006] proposed caching pairwise binary visibility in a spatial hash table [Teschner et al. 2003] and correcting predictions via variance-driven adaptive sampling — a technique [Kugelmann 2006] called *prediction-with-correction* (independently: "go with the winners" [Szirmay-Kalos et al. 2005]) — yielding an unbiased estimator regardless of cache quality. The method was demonstrated on instant radiosity but was always algorithm-agnostic: it reduces shadow-ray cost for any renderer that evaluates pairwise visibility. The idea was promising but limited by fixed-resolution single-level hashing and offline CPU rendering. This paper completes that work by integrating improvements developed in the intervening decades: robust hash addressing with position-seeded jitter [Binder et al. 2018, modified] that acts as an intrinsic box filter across cell boundaries, fingerprint-based collision detection [Binder et al. 2018] with double-hash probing, LOD level encoded directly into the hash key [Gautron 2020] so that multiple resolutions coexist in one flat table, variance-driven write-depth gating inspired by concurrent work on adaptive hash resolution [Stotko et al. 2025], and GPU-parallel lock-free updates [Gautron 2021] with pcg3d hashing [Jarzynski & Olano 2020]. We demonstrate integration with ReSTIR DI and GI [Bitterli et al. 2020; Ouyang et al. 2021] as one natural client, but the cache applies equally to classical next-event estimation or any pairwise visibility query. Initial profiling on Bistro exterior shows **##%** shadow-ray reduction in direct illumination and **##%** in GI revalidation, with no measurable bias and negligible cache-maintenance overhead.

**Keywords:** visibility caching, shadow rays, spatial hashing, prediction-with-correction, adaptive sampling, real-time rendering, collision handling

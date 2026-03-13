# Unbiased Visibility Prediction-with-Correction for Real-Time Path Tracing

**Shadow Ray Reduction using a Filtered Adaptive Multi-Level Hash Cache**

**[Paper draft](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html)** | **[2006 Diplomarbeit (PDF)](docs/references/Kugelmann2006_ThesisMK.pdf)**

**Author:** Manuel Kugelmann
**Status:** Implementation in progress. Paper draft in progress.

---

### History

The 2006 Diplomarbeit by Manuel Kugelmann ("Efficient Adaptive Global Illumination Algorithms", Universität Ulm, supervisor Alexander Keller) suffered multiple problems — overambitious scope, underautomated experiments, too much side work for financial reasons, theft of personal belongings, youthful lack of managment and communication skills — and was never properly finished. It's artifacts (thesis test and code) probably linger somwhere in the University Ulm archives and A. Keller's archives. A definitve hardcopy and compact disk with source code exists in Manuel Kugelmann's storage.

The thesis developed a general framework called *prediction with correction* (Sec. 3.4) — using a spatial hash map cached prediction as control variate and Russian roulette to decide whether to correct, with variance driving RR survival probability as adaptive sampling (Sec. 3.4.1). The framework was applied through many explorative cache experiments — visibility prediction (Sec. 3.2.2), contribution prediction (Sec. 3.2.3), and others. The approach of using variance — not absolute light — to drive sampling rate and the use of a spatial hash map for the cache was inspired by hints on the important role of variance and the "curse of dimensionality" in Keller's lectures at Universität Ulm.

Using a control variate instead of zero on RR termination is standard Monte Carlo variance reduction — combining two textbook techniques (Knuth 1973; Hammersley and Handscomb 1964). The idea is at least implicit in the "go with the winners" family (Aldous and Vazirani 1994; Grassberger 2002). In the graphics context, [Szécsi, Szirmay-Kalos and Kelemen 2003][r-szecsi] formalized the non-zero termination estimate for rendering (CV, but with fixed RR probability). [Szirmay-Kalos et al. 2005][r-szirmay] added variance-driven RR via a Splitting|Russian Roulette framework using a scene-global average radiance estimate. The Kugelmann thesis arrived at the same CV+VRRR math independently but refined the estimation source (per-point spatial cache rather than a scene-global constant) and the variance signal use (variance measuring the cache-quality → trace-rate loop). The overlap with Szécsi et al. was found late in the writing process and contributed to the overambitious search for other possible new contributions.

The spatial grids of the hash map were visible in the thesis — screenshots show grid cells. What was an unmentioned implementation detail was the use of *spatial hashing* to map grid cells to memory. The practical inspiration came from [ODE][r-ode] (Open Dynamics Engine, Russell Smith, 2001–2004), which uses spatial hashing for broad-phase collision detection. Kugelmann encountered ODE's spatial hashing through deep use of ODE during a Universität Ulm student course project ([Animal Race](http://animalrace.bitcraft.org/)). The 2006 thesis adopted spatial hashing for caching illumination quantities without suffering the "curse of dimensionality" but did not describe or frame it as a contribution.

The Bernoulli optimization (var = μ(1−μ), requiring no separate variance accumulator for binary visibility) was not realized in 2006 — the thesis used generalized variance estimation across all cached quantities. Narrowing to binary visibility allows exploiting the Bernoulli structure.

The test case in 2006 was Instant Radiosity [Keller 1997], but the caching for CV+VRRR is algorithm-agnostic: it operates on pairwise queries regardless of the rendering algorithm generating them.

Research progress in the meantime arrived at many similar insights and solutions independently - the 2006 work is practically undiscoverable by the public.
Let's try an LLM assisted speed run of getting the old 2006 work up to date ... 

## Overview

Most shadow rays in real-time path tracing are redundant — nearby surface points querying the same light region overwhelmingly agree on the outcome. We store binary visibility predictions in a flat, multilevel spatial hash table with 8-byte entries and lock-free atomic updates, and correct cached predictions stochastically so that the estimator remains unbiased regardless of cache quality.

### Core mechanism

The **prediction-with-correction** (**C**ontrol **V**ariate + **V**ariance-driven **R**ussian **R**oulette **R**esidual) estimator converts any visibility prediction into an unbiased shadow ray estimator:

```
variance = µ(1 − µ)
p = clamp(variance / varianceThreshold, pMin, 1.0)
if random < p:
    V = traceShadowRay()
    return µ + (V - µ) / p    # unbiased correction
else:
    return µ                  # no trace, use cached mean
```

The **Bernoulli structure** of binary visibility makes this easy: The same scalar µ gives both the cached estimate and the variance.

The variance signal drives two reinforcing mechanisms:
1. **Correction rate** — variance steers the number of samples via RR
2. **Spatial resolution** — sample count and variance determine which resolution levels of the cache get writes

High-variance regions trace more often *and* at finer spatial resolution.
Low-variance regions trace rarely and only update the coarse level.
This self-regulating behaviour makes the system practical without per-scene tuning.

The cache is algorithm-agnostic — it operates on pairwise (point, point) → {0,1} queries regardless of the rendering algorithm generating them.

### Key additions beyond [Kugelmann 2006][r-kugelmann]

- **Position Jitter as Filtering** intrinsic box filter across cell boundaries, based on [Binder et al. 2018][r-binder] 
- **Good and Fast Hash** - based on PCG3D [Jarzynski & Olano 2020][r-jarzynski]
- **Hash Collision Handling** - fingerprint like [Binder et al. 2018][r-binder], double-hash probing, pressure-scaled eviction
- **LOD in the hash key** - multiple resolutions in one flat table [Gautron 2020][r-gautron20], [Gautron 2021][r-gautron21]
- **Coupled variance adaptation** - variance drives resolution level like in [Stotko et al. 2025][r-stotko]
- **GPU implementation** — built on NVIDIA Falcor 8.0 [Kallweit et al. 2022][r-falcor]
- **ReSTIR integration** — example integration with ReSTIR DI [Bitterli et al. 2020][r-bitterli] and ReSTIR PT [Lin et al. 2022][r-lin]

#### ReSTIR integration

The visibility cache plugs into two points of the ReSTIR pipeline. During **light selection**, the cached mean µ replaces the usual visibility assumption in the RIS target function, yielding µ-weighted candidate selection that steers samples toward actually visible lights. During **visibility revalidation**, the correction estimator replaces unconditional occlusion rays with variance-driven Russian Roulette, reducing shadow rays while maintaining equal quality. This offers a middle way between skipping revalidation completely (biased) and full revalidation (expensive). Instead of our visibility cache any other prediction of visibility, e.g. from ReSTIR reservoir data, can be used.

---

## Related work

| Paper | Relation |
|-------|---------|
| [Kugelmann 2006 (Diplomarbeit)][r-kugelmann] | Direct ancestor — CV+RR with per-point spatial cache, variance-driven adaptive sampling |
| [Szécsi et al. 2003][r-szecsi] | Non-zero termination estimate for rendering (CV, fixed RR probability) |
| [Szirmay-Kalos et al. 2005][r-szirmay] | Variance-driven splitting/RR for path tracing |
| [Teschner et al. 2003][r-teschner] | Spatial hashing for collision detection — foundational technique |
| [Smith 2001–2004 (ODE)][r-ode] | `dHashSpace` broad-phase collision via spatial hashing; inspiration far spatial hashing in 2006 thesis |
| [Binder et al. 2018][r-binder] | Spatial hashing, jitter-quantize, fingerprint collision detection |
| [Gautron 2020][r-gautron20], [Gautron 2021][r-gautron21] | LOD in hash key, lock-free GPU hash updates |
| [Jarzynski & Olano 2020 (JCGT)][r-jarzynski] | PCG3D hash function |
| [Stotko et al. 2025 (MrHash)][r-stotko] | Parallels - variance-driven resolution in flat hash (TSDF domain) |
| [Lin et al. 2022 (GRIS/ReSTIR_PT)][r-lin] | Baseline for GI revalidation |
| [Bitterli et al. 2020 (ReSTIR DI)][r-bitterli] | Spatiotemporal reservoir resampling for direct lighting; integration target |
| [Bokšanský & Meister 2025 (JCGT)][r-boksansky] | Parallels — neural visibility cache for light selection |
| [Kallweit et al. 2022 (Falcor)][r-falcor] | GPU rendering framework used as implementation base |

[r-kugelmann]: docs/references/Kugelmann2006_ThesisMK.pdf
[r-szecsi]: https://www.researchgate.net/publication/221546555_Variance_Reduction_for_Russian-roulette
[r-szirmay]: https://www.researchgate.net/publication/228769903_Go_with_the_Winners_Strategy_in_Path_Tracing
[r-teschner]: https://matthias-research.github.io/pages/publications/tetraederCollision.pdf
[r-ode]: https://ode.org/
[r-binder]: https://doi.org/10.1145/3214745.3214806
[r-gautron20]: https://doi.org/10.1145/3388767.3407365
[r-gautron21]: https://link.springer.com/chapter/10.1007/978-1-4842-7185-8_41
[r-jarzynski]: https://jcgt.org/published/0009/03/02/
[r-stotko]: https://arxiv.org/abs/2511.21459
[r-lin]: https://doi.org/10.1145/3528223.3530158
[r-bitterli]: https://doi.org/10.1145/3386569.3392382
[r-falcor]: https://github.com/NVIDIAGameWorks/Falcor
[r-boksansky]: https://jcgt.org/published/0014/02/01/

---

## Quickstart

```bat
cmd /c "curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.bat?%RANDOM% -o %TEMP%\vc-install.bat && %TEMP%\vc-install.bat"
```

Idempotent — safe to re-run. Clones (or pulls), downloads test scenes, downloads the latest release, runs CPU tests, and launches Mogwai with Bistro.

See **[Getting Started](docs/GETTING_STARTED.md)** for build-from-source, Linux/WSL, and release usage.


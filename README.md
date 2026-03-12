# Visibility Prediction-with-Correction for Real-Time Path Tracing

**Unbiased Adaptive Shadow Ray Reduction with a Filtered Multi-Level Hash Cache**

**[Paper draft](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html)** | **[2006 Diplomarbeit (PDF)](docs/references/Kugelmann2006_ThesisMK.pdf)**

**Author:** Manuel Kugelmann
**Status:** Implementation in progress. Paper draft in progress.

---

## Overview

Most shadow rays in real-time path tracing are redundant — nearby surface points querying the same light region overwhelmingly agree on the outcome. We store binary visibility predictions in a flat, multilevel spatial hash table with 8-byte entries and lock-free atomic updates, and correct cached predictions stochastically so that the estimator remains unbiased regardless of cache quality.

### Core mechanism

The **prediction-with-correction (Control Variate + Variance-driven Russian Roulette Residual = CV+VRRR)** estimator converts any visibility prediction into an unbiased shadow ray estimator:

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
2. **Spatial resolution** — sample count and variance determine which LOD levels of the cache get writes

High-variance regions trace more often *and* at finer spatial resolution.
Low-variance regions trace rarely and only update the coarse level.
This self-regulating behaviour makes the system practical without per-scene tuning.

The cache is algorithm-agnostic — it operates on pairwise (point, point) → {0,1} queries regardless of the rendering algorithm generating them.

### Key additions beyond [Kugelmann 2006]

- **Position-seeded jitter** intrinsic box filter across cell boundaries, based on [Binder et al. 2018] [Jarzynski & Olano 2020]
- **Collision handling** fingerprint detection based on [Binder et al. 2018], double-hash probing, pressure-scaled eviction, WaveMatch coalescing (SM 6.5)
- **LOD in the hash key** multiple resolutions in one flat table [Gautron 2020], [Gautron 2021]
- **Coupled variance adaptation** — Bernoulli variance drives both correction rate and write-depth gating (independently paralleled by [Stotko et al. 2025])
- **ReSTIR integration** at three points: DI candidate selection, post-shading correction, revalidation

[Kugelmann 2006]: docs/references/Kugelmann2006_ThesisMK.pdf
[Binder et al. 2018]: https://doi.org/10.1145/3214745.3214806
[Jarzynski & Olano 2020]: https://jcgt.org/published/0009/03/02/
[Gautron 2020]: https://doi.org/10.1145/3388767.3407365
[Gautron 2021]: https://link.springer.com/chapter/10.1007/978-1-4842-7185-8_41
[Stotko et al. 2025]: https://arxiv.org/abs/2511.21459

### ReSTIR integration

| Point | Section | What it replaces | Benefit |
|-------|---------|-----------------|---------|
| DI candidate selection | §9.1 | V=1 assumption in RIS target | µ-weighted selection, better candidates |
| visibility  | §9.2 | Unconditional shadow ray | ~88% shadow ray reduction |
| GI revalidation | §9.3 | k=5 full retrace per pixel | ~0.5–1.0 traces/px vs. 5.0 |

---

## Quickstart

```bat
curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o %TEMP%\vc-bootstrap.bat && %TEMP%\vc-bootstrap.bat
```

Idempotent — safe to re-run. Clones (or pulls), downloads the latest release, fetches test scenes, runs CPU tests, and launches Mogwai with Bistro. See **[Getting Started](docs/GETTING_STARTED.md)** for build-from-source, Linux/WSL, and release usage.

---

## Related work

| Paper | Relation |
|-------|---------|
| [Kugelmann 2006 (Diplomarbeit)][r-kugelmann] | Direct ancestor — CV+RR with per-point spatial cache, variance-driven adaptive sampling |
| [Szécsi et al. 2003][r-szecsi] | Non-zero termination estimate for rendering (CV, fixed RR probability) |
| [Szirmay-Kalos et al. 2005][r-szirmay] | Variance-driven splitting/RR for path tracing |
| [Teschner et al. 2003][r-teschner] | Spatial hashing for collision detection — foundational technique |
| [Smith 2001–2004 (ODE)][r-ode] | `dHashSpace` broad-phase collision via spatial hashing; practical inspiration for 2006 thesis |
| [Binder et al. 2018][r-binder] | Spatial hashing, jitter-quantize, fingerprint collision detection |
| [Gautron 2020][r-gautron20], [Gautron 2021][r-gautron21] | LOD in hash key, lock-free GPU hash updates |
| [Jarzynski & Olano 2020 (JCGT)][r-jarzynski] | PCG3D hash function |
| [Stotko et al. 2025 (MrHash)][r-stotko] | Independent: variance-driven resolution in flat hash (TSDF domain) |
| [Lin et al. 2022 (GRIS/ReSTIR_PT)][r-lin] | Baseline for GI revalidation |
| [Bokšanský & Meister 2025 (JCGT)][r-boksansky] | Concurrent — neural visibility cache for light selection |

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
[r-boksansky]: https://jcgt.org/published/0014/02/01/

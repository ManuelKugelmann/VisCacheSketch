# Visibility Prediction-with-Correction for Real-Time Path Tracing

**Unbiased Adaptive Shadow Ray Reduction with a Filtered Multi-Level Hash Cache**

**[Paper draft](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html)** | **[Getting Started](docs/GETTING_STARTED.md)** | **[2006 Diplomarbeit (PDF)](docs/references/Kugelmann2006_ThesisMK.pdf)**

**Author:** Manuel Kugelmann
**Target venue:** EGSR / HPG 2026
**Status:** Implementation in progress, paper draft in revision

---

## Quickstart

```bat
curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o %TEMP%\vc-bootstrap.bat && %TEMP%\vc-bootstrap.bat
```

Idempotent — safe to re-run. Clones (or pulls), downloads the latest release, fetches test scenes, runs CPU tests, and launches Mogwai with Bistro. See **[Getting Started](docs/GETTING_STARTED.md)** for build-from-source, Linux/WSL, and release usage.

---

## Overview

Most shadow rays in real-time path tracing are redundant — nearby surface points querying the same light region overwhelmingly agree on the outcome. We store binary visibility predictions in a flat, multilevel spatial hash table with 8-byte entries and lock-free atomic updates, and correct cached predictions stochastically so that the estimator remains unbiased regardless of cache quality.

### Core mechanism

The **prediction-with-correction (CV+VRRR)** estimator converts a spatial visibility cache into an unbiased shadow ray estimator:

```
if rand < p:
    V = traceShadowRay()
    return µ + (V - µ) / p    # unbiased correction
else:
    return µ                   # no trace, use cached mean
```

where `p = clamp(var / varThreshold, pMin, 1.0)` and `var = µ(1 − µ)`.

The **Bernoulli structure** of binary visibility makes this clean: variance is fully determined by the cached mean — no separate variance estimator needed. The same scalar µ gives both the cached estimate and the variance, enabling joint adaptation of correction rate and spatial resolution with a single threshold.

### Coupled variance adaptation

The same variance signal drives two reinforcing mechanisms:
1. **Correction rate** — RR survival probability p
2. **Spatial resolution** — write-depth gate determines which LOD levels receive updates

High-variance regions trace more often *and* at finer spatial resolution. Low-variance regions trace rarely and only update the coarse level. This self-regulating behaviour makes the system practical without per-scene tuning.

### Key additions beyond Kugelmann [2006]

- **Position-seeded jitter** (modifying [Binder et al. 2018], hash from [Jarzynski & Olano 2020]) — intrinsic box filter across cell boundaries
- **Collision handling** — fingerprint detection, double-hash probing, pressure-scaled eviction, WaveMatch coalescing (SM 6.5)
- **LOD in the hash key** [Gautron 2020, 2021] — multiple resolutions in one flat table
- **Coupled variance adaptation** — Bernoulli variance drives both correction rate and write-depth gating (independently paralleled by [Stotko et al. 2025])
- **ReSTIR integration** at three points: DI candidate selection, post-shading correction, GI revalidation

### ReSTIR integration

| Point | Section | What it replaces | Benefit |
|-------|---------|-----------------|---------|
| DI candidate selection | §9.1 | V=1 assumption in RIS target | µ-weighted selection, better candidates |
| Post-shading correction | §9.2 | Unconditional shadow ray | ~88% shadow ray reduction |
| GI revalidation | §9.3 | k=5 full retrace per pixel | ~0.5–1.0 traces/px vs. 5.0 |

The cache is algorithm-agnostic — it operates on pairwise (point, point) → {0,1} queries regardless of the rendering algorithm generating them.

---

## Related work

| Paper | Relation |
|-------|---------|
| Kugelmann 2006 (Diplomarbeit) | Direct ancestor — CV+RR with per-point spatial cache, variance-driven adaptive sampling |
| Szécsi et al. 2003 | Non-zero termination estimate for rendering (CV, fixed RR probability) |
| Szirmay-Kalos et al. 2005 | Variance-driven splitting/RR for path tracing |
| Teschner et al. 2003 | Spatial hashing for collision detection — foundational technique |
| Smith 2001–2004 (ODE) | `dHashSpace` broad-phase collision via spatial hashing; practical inspiration for 2006 thesis |
| Binder et al. 2018 | Spatial hashing, jitter-quantize, fingerprint collision detection |
| Gautron 2020, 2021 | LOD in hash key, lock-free GPU hash updates |
| Jarzynski & Olano 2020 (JCGT) | PCG3D hash function |
| Stotko et al. 2025 (MrHash) | Independent: variance-driven resolution in flat hash (TSDF domain) |
| Lin et al. 2022 (GRIS/ReSTIR_PT) | Baseline for GI revalidation |
| Bokšanský & Meister 2025 (JCGT) | Concurrent — neural visibility cache for light selection |

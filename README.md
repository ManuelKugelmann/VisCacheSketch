<p align="center">
  <img src="viscache.png" alt="VisCache logo" width="400">
</p>

# Unbiased Visibility Prediction-with-Correction for Real-Time Path Tracing

**Shadow Ray Reduction using a Filtered Adaptive Multi-Level Hash Cache**

**[Paper draft](https://ManuelKugelmann.github.io/VisCache/paper.html)** | **[2006 Diplomarbeit (PDF)](docs/references/Kugelmann2006_ThesisMK.pdf)** | **[Dev Log](docs/devlog/DEVLOG.md)** | **[Ladder Plan](docs/LADDER_PLAN.md)** | **[Ladder Log](docs/LADDERLOG.md)**

**Author:** Manuel Kugelmann
**Status:** Implementation in progress. Paper draft in progress.

---

### Headline results

**Shadow rays saved across the matrix at vanilla-quality match** (cache `rays_traced_pct`; lower = more rays saved; 100% = vanilla). Static-scene frame-accumulation, x4 SPP, canonical config (`stderrThreshold=0.10`).

<p align="center">
  <img src="docs/rays_saved_matrix.png" alt="Rays saved across scenes × bounce depths — 3-94% saved at vanilla-quality match" width="900">
</p>

**Quality at x4 SPP vs RTXDI** (mean OkLab perceptual error vs x4096 GT, lower = better). Cache integrates into ReSTIR DI as `restir_2d` (per-pixel reservoir + screen-tile pool, RTXDI's exact data structure) and `restir_3d` (3D-cell pool with footprint-derived entry level — world-space analog). **Net 6 wins / 1 trail / cumulative −4.81pp ahead of production RTXDI.** `|restir_2d − restir_3d| ≤ 0.03pp` on every scene (structural-equivalence claim from §3.0 made operational).

<p align="center">
  <img src="docs/rtxdi_parity.png" alt="RTXDI parity at x4 SPP — 6/7 scene wins" width="900">
</p>

**Algorithm in action — Sponza canonical, x16 SPP, stderr=0.10.** 4×3 diagnostic grid: row 1 = render | rays-traced heatmap | error vs GT | noise; row 2 = LOD level | maturity | cached μ | variance; row 3 = cold-miss | qA hash | qB hash | probe steps. The cache trusts most of the wall and floor (purple = low rays_traced; cells are mature with low variance) and refines only at the penumbra boundaries (yellow rays, high variance). **Mean error 2.0% vs vanilla x4096 GT, art5 15%, 26.5% rays traced — 73.5% saved.**

<p align="center">
  <img src="docs/plates/sponza_canonical_x16_diagnostic.png" alt="Sponza canonical diagnostic 4×3 grid" width="900">
</p>

Full numbers in [paper §13](viscachepaper/sections/13-results.md); methodology and per-step ladder narrative in [LADDERLOG.md](docs/LADDERLOG.md).

---

### History

The core ideas behind this project — control variates, Russian roulette, spatial hashing, variance-driven sampling — are not new. They are textbook Monte Carlo techniques ([Knuth 1973][r-knuth]; [Hammersley and Handscomb 1964][r-hammersley]) and well-known data structures. The contribution of the [2006 thesis][r-kugelmann] was combining them in a specific way for visibility estimation in rendering. Much of the same ground has since been covered independently by others, often with better engineering, better framing, or both. We all stand on the shoulders of giants.

**The 2006 thesis.** Manuel Kugelmann's 2006 Diplomarbeit ("Efficient Adaptive Global Illumination Algorithms", Universität Ulm, supervisor Alexander Keller) developed a framework called *prediction with correction* (Sec. 3.4): a spatial hash map stores cached predictions used as control variates, with Russian roulette deciding whether to trace a correction ray and variance driving the RR survival probability (Sec. 3.4.1). The framework was applied to visibility prediction (Sec. 3.2.2), contribution prediction (Sec. 3.2.3), and other cached quantities. The approach of using variance — not absolute light — to drive sampling rate, and the use of spatial hashing for the cache, was inspired by A. Keller's lectures on the role of variance and the "curse of dimensionality". The test case was Instant Radiosity [[Keller 1997][r-keller]], but the caching is algorithm-agnostic — it operates on pairwise queries regardless of the rendering algorithm.

The thesis was never properly finished and remained unpublished. Its artifacts (text and code) likely linger in the Universität Ulm archives and A. Keller's archives. A definitive hardcopy and compact disk with source code exists in Manuel Kugelmann's storage.

**Why it was cut short.** The 2006 thesis was looking for a workable solution to the concrete problem of the day — rendering many lights, many shadow rays, and many paths in tractable time — aiming too high. Funding pressure throughout the Diplomarbeit pulled time toward paid sidework, and afterwards a paid Computer-Vision thesis became the priority. The visibility-caching line was left at "promising sketch with empirical results" — the polish, broader scene validation, and journal write-up never happened. The 2026 work picks the same investigation back up two decades later.

**Prior and parallel work on CV+RR.** Using a control variate instead of zero on RR termination is at least implicit in the "go with the winners" family ([Aldous and Vazirani 1994][r-aldous]; [Grassberger 2002][r-grassberger]). In the graphics context, [Szécsi, Szirmay-Kalos and Kelemen 2003][r-szecsi] formalized the non-zero termination estimate for rendering (CV with fixed RR probability). [Szirmay-Kalos et al. 2005][r-szirmay] added variance-driven RR using a scene-global radiance estimate. The 2006 thesis arrived at the same CV+VRRR math independently, differing mainly in the estimation source (per-point spatial cache rather than a scene-global constant) and the variance feedback loop (cache quality drives trace rate and spatial resolution). The overlap with both Szécsi et al. and Szirmay-Kalos et al. was discovered late in the writing process.

**Spatial hashing.** The spatial grids were visible in the thesis screenshots, but the use of *spatial hashing* to map grid cells to memory went unmentioned — it was treated as an implementation detail, not a contribution. The practical inspiration came from [ODE][r-ode] (Open Dynamics Engine, Russell Smith, 2001–2004), which uses spatial hashing for broad-phase collision detection. Kugelmann encountered ODE through a Universität Ulm course project ([Animal Race](http://animalrace.bitcraft.org/)).

<img src="docs/references/MK2006.jpg" width="380" alt="Kugelmann 2006 — spatial hash grid visibility cache. Left: rendered image. Right: shadow test count revealing the spatial grid cells.">

**What was not in 2006.** The Bernoulli optimization (var = μ(1−μ), requiring no separate variance accumulator for binary visibility) was not realized — the thesis used generalized variance estimation across all cached quantities. Narrowing to binary visibility allows exploiting the Bernoulli structure. GPU implementation, modern hash functions, LOD-in-key, and ReSTIR integration are all new (see [Key additions](#key-additions-beyond-kugelmann-2006) below).

Since the thesis was unpublished with no online abstract or indexed metadata, independent rediscovery of these ideas by the community is the expected and natural outcome.

**Name collision: another "VisCache".** A 2016 Utrecht student project by [Jerry Jinfeng Guo](https://github.com/Jerry-Jinfeng-Guo/VisCache) used the same name for a unidirectional path tracer with visibility caching, also reporting ~78 % shadow-ray reduction. The name was independently coined; we encountered the repository after our project was already named. The 2016 work is unpublished, but is plausibly the conceptual seed of [Guo, M. Eisemann & E. Eisemann 2020 — NEE++][r-guo], which we cite. Independent prior art for the name and the headline savings number — not for the multilevel hash cascade, the ReSTIR composition, or any specific 2026 contribution. We keep the name; both projects sit in the [Ward 1991] / [Popov 2013] / [Ulbrich 2013] / [Kugelmann 2006] line of visibility caching, ten years apart and on different sides of the GPU / ReSTIR transition.

**Let's try an LLM-assisted speed run of getting the old 2006 work up to date ...**

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

The variance signal drives two reinforcing mechanisms simultaneously (**coupled dual adaptation**):
1. **Correction rate** — variance steers the number of samples via RR
2. **Spatial resolution** — variance gates which resolution levels of the cache get writes

High-variance regions trace more often *and* at finer spatial resolution.
Low-variance regions trace rarely and only update the coarse level.
This one-signal-two-decisions coupling is what makes the cache self-regulating without per-scene tuning.

The cache is algorithm-agnostic — it operates on pairwise visibility queries regardless of the rendering algorithm generating them.

### Key addressing: position+normal × direction+distance

The hash key decomposes the visibility query into **shading point** (position + surface normal) and **query** (direction + distance). This exploits free geometric information that symmetric position × position addressing cannot:

- **Normal** disambiguates thin geometry and corners — nearby points with different normals get separate entries
- **Direction** enables angular LOD — coarse angular bins where visibility is smooth, fine bins at shadow edges
- **Distance monotonicity** — if occluded at distance d, everything farther is also blocked; one any-hit ray (using the free `CommittedRayT()`) propagates V=0 to all farther distance bins at zero cost

A secondary position × position mode is available for GI revalidation queries. Both modes coexist in the same flat hash table.

### Key additions beyond [Kugelmann 2006][r-kugelmann]

- **Position+normal × direction+distance addressing** — exploits surface normal, angular LOD, and distance monotonicity
- **Position Jitter as Filtering** — intrinsic box filter across cell boundaries, based on [Binder et al. 2018][r-binder]
- **Good and Fast Hash** — based on PCG3D [Jarzynski & Olano 2020][r-jarzynski]
- **Hash Collision Handling** — fingerprint like [Binder et al. 2018][r-binder], double-hash probing, pressure-scaled eviction
- **LOD in the hash key** — multiple resolutions in one flat table [Gautron 2020][r-gautron20], [Gautron 2021][r-gautron21]
- **Coupled variance adaptation** — variance drives correction rate and spatial resolution like in [Stotko et al. 2025][r-stotko]
- **GPU implementation** — built on NVIDIA Falcor 8.0 [Kallweit et al. 2022][r-falcor]
- **Cache-weighted light selection** — cached μ weights ReSTIR candidate selection like [Bokšanský & Meister 2025][r-boksansky]
- **ReSTIR integration** — example integration with ReSTIR DI [Bitterli et al. 2020][r-bitterli] and ReSTIR PT [Lin et al. 2022][r-lin]

#### ReSTIR integration

The visibility cache plugs into two points of the ReSTIR pipeline. During **light selection**, the cached mean µ replaces the usual visibility assumption in the RIS target function, yielding µ-weighted candidate selection that steers samples toward actually visible lights. During **visibility revalidation**, the correction estimator replaces unconditional occlusion rays with variance-driven Russian Roulette, reducing shadow rays while maintaining equal quality. This offers a middle way between skipping revalidation completely (biased) and full revalidation (expensive). Note: Instead of our visibility cache any other prediction of visibility, e.g. from ReSTIR reservoir data, can be used.

### Current results

Canonical config: flat multilevel hash with the entry level selected analytically per query from primary-hit pixel footprint. **`forceDescendFootprintPx` is a continuous knob that subsumes the RTXDI / ReSTIR-DI screen-space data structures as specific operating points** (paper §3.0): sub-pixel target footprint ≈ per-pixel reservoir (each pixel maps to a private world cell); $T^2$-pixel target footprint ≈ tile pool (all pixels in a $T \times T$ tile share one cell). The canonical `forceDescendFootprintPx=16` lands at the tile-pool-equivalent operating point. **World cells are camera-invariant by construction** — no motion-vector reprojection is needed to reuse samples across camera motion, no `mCap` lifetime clamps, no disocclusion gates: the cell ID is the same world point regardless of how the camera moved between frames, and the fingerprint match doubles as the disocclusion test. (RTXDI/ReSTIR DI's screen-space reservoirs need all three.) The cascade depth (`numLevels`) is an envelope, not a fixed working set: only actively-visited levels populate the hash; idle levels never get written; transiently-visited levels decay and have their slots reclaimed under collision pressure. Bayer 2×2 stratification, `bootThreshold=8`, `stderrThreshold=0.10`, `pMin=0.02`. Static-scene frame-accumulation, 1-spp-per-frame, x4 SPP unless noted. Full numbers in [paper §13](viscachepaper/sections/13-results.md).

**Shadow rays % traced (algorithmic).** Cache `rays_traced_pct` — lower is better; 100% = vanilla equivalent.

| Scene | b=0 | b=1 | b=4 | b=8 | b=16 |
|---|---:|---:|---:|---:|---:|
| Cornell_1PL  | 9.7%  | 7.7%  | **6.1%** | — | — |
| Cornell_1AL  | 53.0% | 47.9% | 37.8% | — | — |
| Cornell_3AL  | 65.7% | 57.4% | 44.8% | — | — |
| Cornell_32PL | 75.8% | 71.5% | 60.1% | — | — |
| Sponza | 31.9% | 28.2% | **25.7%** | 24.4% | **23.8%** |
| BistroInterior | 49.8% | 48.2% | 47.0% | — | — |
| BistroExterior | 60.3% | 59.6% | 58.9% | — | — |

**3–94% rays saved across the matrix at vanilla-quality match.** Rays-saved increases monotonically with bounce depth on every scene; Sponza b=8/16 establishes the asymptote at ~76% rays saved (24% traced).

**Quality at matched SPP (b=4 multibounce, x4):** OkLab perceptual error matches vanilla within 0.05pp on every scene; art5 differs by ≤1pp. Multibounce relmse improves dramatically on indoor multi-light (BistroInterior 2.4× better than vanilla, Cornell_1PL 9% better) — the cache averages out per-bounce firefly variance via cell-level means.

**RTXDI parity (single-bounce DI, x4 OkLab vs x4096 GT):**

| Scene | vanilla | RTXDI | restir_2d (ours) | Δ vs RTXDI |
|---|---:|---:|---:|---:|
| Cornell_1AL | 1.39 | 2.18 | **2.15** | **−0.03 win** |
| Cornell_1PL | 0.21 | 1.39 | **0.21** | **−1.18 win** |
| Cornell_3AL | 2.97 | **2.60** | 3.55 | +0.95 trail |
| Cornell_32PL | 5.36 | 3.73 | **3.31** | **−0.42 win** |
| Sponza | 6.23 | 7.08 | **6.49** | **−0.59 win** |
| BistroInterior | 16.96 | 10.73 | **9.54** | **−1.19 win** |
| BistroExterior | 18.12 | 13.23 | **10.88** | **−2.35 win** |

**Net: 6 wins / 1 trail; cumulative −4.81pp ahead** of the production RTXDI baseline. The 3D-cell pool with footprint-derived entry level recovers RTXDI's screen-tile pool at matched parameters: `|restir_2d − restir_3d| ≤ 0.03pp` on every scene (structural-equivalence claim from §3.0 made operational).

*Wall-clock numbers are deferred from this README — measurement methodology is being tightened (see [LADDERLOG.md](docs/LADDERLOG.md) `TIMING_HONEST` row). Initial steady-state results indicate positive savings on Sponza single-bounce DI even with no GPU optimization; multibounce wall-clock and dynamic-scene measurements are open implementation milestones.*

### Independent parallel work

The individual ideas in the 2006 thesis — control variates, Russian roulette, spatial hashing, variance-driven sampling — are well-established techniques. Many researchers independently arrived at similar combinations. This is a non-exhaustive selection; there is likely more work we are not yet aware of.

**Control Variate + Russian Roulette in rendering.**
[Szécsi et al. 2003][r-szecsi] and [Szirmay-Kalos et al. 2005][r-szirmay] preceded the 2006 thesis (see [History](#history)). More recently, [Dereviannykh et al. 2024][r-n2lmc] (Neural Two-Level MC) use a related approach — their MLMC residual estimator shares the cached-estimate-plus-unbiased-correction structure, framed as two-level Monte Carlo with an MIS-based termination heuristic.

**Visibility Caching.**
The idea of caching visibility to reduce shadow rays predates 2006 — [Ward 1991][r-ward] used heuristic ordering to skip predictable shadow rays. Independent work arrived at the idea through different paths: [Popov et al. 2013][r-popov] an adaptive octree for offline rendering, [Guo et al. 2020][r-guo] (NEE++) per-voxel-pair visibility caching, [SHaRC (Benyoub et al. 2024)][r-sharc] a world-space radiance hash (RTX SDK), [Bokšanský & Meister 2025][r-boksansky] a neural visibility cache, and [Tokuyoshi 2024][r-tokuyoshi] efficient visibility reuse across spatiotemporal neighbors in ReSTIR. [Zhang, Lin et al. 2025][r-zhang25] avoid shadow rays entirely for most lights via ReSTIR-selected shadow maps. [Conner et al. 2025][r-megalights] (MegaLights, Unreal Engine 5) trace a fixed budget of shadow rays per pixel via stochastic light importance sampling.

**Spatial Hashing in rendering.**
Spatial hashing was independently adopted in rendering by [Binder et al. 2018][r-binder] (path-space filtering), [Gautron 2020][r-gautron20]/[2021][r-gautron21] (ambient occlusion), [Müller et al. 2022][r-muller] (Instant NGP — multi-resolution hash encoding, backbone of [Bokšanský & Meister 2025][r-boksansky] and [Dereviannykh et al. 2024][r-n2lmc]), and [SHaRC (Benyoub et al. 2024)][r-sharc] (world-space spatial hash, RTX SDK).

**Variance-driven adaptive sampling.**
[Vorba and Křivánek 2016][r-adrrs] (ADRRS) precompute an adjoint importance function to set per-event RR/splitting weight windows. [Rath et al. 2022][r-rath] (EARS) uses efficiency-aware RR/splitting for path continuation; [Meyer et al. 2024][r-mars] (MARS) generalize to per-technique sample counts. [Jin et al. 2025][r-nrrs] (NRRS) pioneer neural networks with hash-grid encoding for learning RR factors in wavefront path tracing. [Stotko et al. 2025][r-stotko] (MrHash) independently couples variance to spatial resolution in a flat hash (TSDF domain). All operate on path continuation decisions, not shadow ray gating — our work is orthogonal.

[r-n2lmc]: https://arxiv.org/abs/2412.04634
[r-ward]: https://doi.org/10.1007/978-3-642-77145-8_2
[r-sharc]: https://github.com/NVIDIAGameWorks/RTXGI
[r-rath]: https://doi.org/10.1145/3528223.3530168
[r-guo]: https://doi.org/10.1111/cgf.14142
[r-popov]: https://doi.org/10.1111/cgf.12166

---

## Related work

| Paper | Relation |
|-------|---------|
| [Kugelmann 2006 (Diplomarbeit)][r-kugelmann] | Direct ancestor — CV+RR with per-point spatial cache, variance-driven adaptive sampling |
| [Szécsi et al. 2003][r-szecsi] | Non-zero termination estimate for rendering (CV, fixed RR probability) |
| [Szirmay-Kalos et al. 2005][r-szirmay] | Variance-driven splitting/RR for path tracing |
| [Teschner et al. 2003][r-teschner] | Spatial hashing for collision detection — foundational technique |
| [Smith 2001–2004 (ODE)][r-ode] | Broad-phase collision via spatial hashing; inspiration for spatial hashing in 2006 thesis |
| [Binder et al. 2018][r-binder] | Spatial hashing, jitter-quantize, fingerprint collision detection |
| [Gautron 2020][r-gautron20], [Gautron 2021][r-gautron21] | LOD in hash key, lock-free GPU hash updates |
| [Jarzynski & Olano 2020 (JCGT)][r-jarzynski] | PCG3D hash function |
| [Stotko et al. 2025 (MrHash)][r-stotko] | Variance-driven resolution in flat hash (TSDF domain) |
| [Vorba and Křivánek 2016 (ADRRS)][r-adrrs] | Adjoint-driven RR/splitting weight windows for path continuation |
| [Rath et al. 2022 (EARS)][r-rath] | Efficiency-aware RR/splitting for path continuation |
| [Meyer et al. 2024 (MARS)][r-mars] | Per-technique sample allocation via RR/splitting |
| [Jin et al. 2025 (NRRS)][r-nrrs] | Neural RR factors with hash-grid encoding for wavefront path tracing |
| [Guo et al. 2020 (NEE++)][r-guo] | Voxel-to-voxel visibility probability caching |
| [Popov et al. 2013][r-popov] | Adaptive quantization visibility caching (offline) |
| [Benyoub et al. 2024 (SHaRC)][r-sharc] | Spatial Hash Radiance Cache — world-space hash, roughness-gated LoD (RTX SDK) |
| [Lin et al. 2022 (GRIS/ReSTIR_PT)][r-lin] | Baseline for GI revalidation |
| [Tokuyoshi 2024][r-tokuyoshi] | Efficient visibility reuse across spatiotemporal neighbors in ReSTIR |
| [Zhang, Lin et al. 2025 (ReSTIR Shadow Maps)][r-zhang25] | ReSTIR-selected shadow maps — avoids shadow rays for most lights |
| [Conner et al. 2025 (MegaLights)][r-megalights] | Fixed-budget stochastic direct lighting in Unreal Engine 5 |
| [Bitterli et al. 2020 (ReSTIR DI)][r-bitterli] | Spatiotemporal reservoir resampling for direct lighting; integration target |
| [Bokšanský & Meister 2025 (JCGT)][r-boksansky] | Neural visibility cache for light selection |
| [Dereviannykh et al. 2024 (Neural Two-Level MC)][r-n2lmc] | MLMC residual shares cached-estimate + correction structure (but framed as MLMC, not CV; BTH is MIS-based, not variance-driven RR), multi-level hash encodings |
| [Müller et al. 2022 (Instant NGP)][r-muller] | Multi-resolution hash encoding — spatial hashing for neural graphics; backbone of Bokšanský 2025 and Dereviannykh 2024 |
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
[r-muller]: https://doi.org/10.1145/3528223.3530127
[r-boksansky]: https://jcgt.org/published/0014/02/01/
[r-tokuyoshi]: https://doi.org/10.1145/3641233.3664320
[r-zhang25]: https://doi.org/10.1111/cgf.70059
[r-megalights]: https://advances.realtimerendering.com/s2025/content/MegaLights_Stochastic_Direct_Lighting_2025.pdf
[r-adrrs]: https://doi.org/10.1145/2897824.2925912
[r-mars]: https://doi.org/10.1145/3687923
[r-nrrs]: https://arxiv.org/abs/2510.07868
[r-knuth]: https://doi.org/10.1007/978-3-642-56592-2
[r-hammersley]: https://doi.org/10.1007/978-94-009-5819-7
[r-aldous]: https://doi.org/10.1007/BF01208571
[r-grassberger]: https://doi.org/10.1016/S0010-4655(02)00467-3
[r-keller]: https://doi.org/10.1145/258734.258769

---

## Quickstart

```bat
cmd /c "curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.bat?%RANDOM% -o %TEMP%\vc-install.bat && %TEMP%\vc-install.bat"
```

Idempotent — safe to re-run. Clones (or pulls), downloads test scenes, downloads the latest release, runs CPU tests, and launches Mogwai with Bistro.

See **[Getting Started](docs/GETTING_STARTED.md)** for build-from-source, Linux/WSL, and release usage.


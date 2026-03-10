# Referenced Papers

Run `./docs/fetch_papers.sh` to download freely available preprints into `docs/references/`.
All reference PDFs (including own papers) are committed in `docs/references/`.

---

## Own work

### Kugelmann 2006
**M. Kugelmann, "Efficient Adaptive Global Illumination Algorithms," Diplomarbeit, Universität Ulm, 2006.**
Three independent cache experiments — irradiance, binary visibility, free-path distance — each with CV+RRR correction rates driven by variance, stored in a fixed-resolution single-level spatial hash. Direct ancestor of VisCache: we develop experiment (2) (binary visibility) into a complete real-time system.
- PDF: `docs/references/Kugelmann2006_ThesisMK.pdf` (in repo)

---

## ReSTIR family

### Bitterli 2020 — ReSTIR DI
**B. Bitterli et al., "Spatiotemporal Reservoir Resampling for Real-Time Ray Tracing with Dynamic Direct Lighting," TOG 39(4), 2020.**
Introduces Resampled Importance Sampling (RIS) with spatiotemporal reservoir reuse for direct lighting. Samples light candidates with target PDF p̂ = f·L·G·V; our §11.1 replaces V=1 with cached μ. Baseline for DI integration.
- PDF: [Author preprint](https://benedikt-bitterli.me/restir/bitterli20restir.pdf) | **Auto**
- Scenes: Bistro, Emerald Square, Zero Day

### Ouyang 2021 — ReSTIR GI
**Y. Ouyang et al., "ReSTIR GI: Path Resampling for Real-Time Path Tracing," CGF 40(8), 2021.**
Extends ReSTIR to indirect illumination via path reservoirs with spatial/temporal reuse. Revalidation requires k≈5 retrace rays per pixel — our §11.3 reduces this to ~0.5–1.0 via CV+RRR gating.
- PDF: [arXiv:2108.05263](https://arxiv.org/pdf/2108.05263.pdf) | **Auto**
- Scenes: Bistro, Country Kitchen, Living Room

### Lin 2022 — GRIS / ReSTIR PT
**D. Lin et al., "Generalized Resampled Importance Sampling: Foundations of ReSTIR," TOG 41(4), 2022.**
Unifying theory for ReSTIR. DQLin/ReSTIR_PT is the reference implementation we port to Falcor 8.0. Essential baseline for §11.3 Table 3 ground truth.
- PDF: [arXiv:2211.09648](https://arxiv.org/pdf/2211.09648.pdf) | **Auto**
- Scenes: Bistro, Zero Day

### Liu 2025 — Reservoir Splatting
**J. Liu et al., "Reservoir Splatting for Temporal Path Resampling and Motion Blur," SIGGRAPH 2025.**
Forward-projects primary hits for temporal reuse instead of backprojection. Orthogonal to VisCache — addresses path reuse robustness under camera motion, not visibility cost. Enables motion blur for ReSTIR.
- PDF: [NVIDIA Research](https://research.nvidia.com/labs/rtr/publication/liu2025splatting/liu2025splatting_paper.pdf) | **Auto**
- Scenes: Bistro, Zero Day

### Zhang 2024 — Area ReSTIR
**Y. Zhang et al., "Area ReSTIR: Re-Sampling for Real-Time Defocus and Antialiasing," SIGGRAPH 2024.**
Extends ReSTIR DI to lens×light area sampling for DOF/AA. Final shadow ray structure identical to standard RTXDI — CV+RRR integrates without modification.
- PDF: [arXiv:2401.02293](https://arxiv.org/pdf/2401.02293.pdf) | **Auto**
- Scenes: Bistro, Emerald Square

---

## Visibility caching (related / concurrent)

### Bokšanský & Meister 2025 — Neural Visibility Cache
**A. Bokšanský, D. Meister, "Neural Visibility Cache for Real-Time Light Sampling," JCGT 14(2), 2025.**
Concurrent work. Online-trained neural hash grid (instant-ngp backbone) caches light→surface visibility for WRS light selection. Default mode is biased — uses network output directly. CV+RRR would make it unbiased. Same §11.1 idea, different data structure.
- PDF: [arXiv:2506.05930](https://arxiv.org/pdf/2506.05930.pdf) / [JCGT](https://jcgt.org/published/0014/02/01/) | **Auto**
- Scenes: Bistro, Emerald Square

### Popov 2013 — Adaptive Quantization Visibility Caching
**S. Popov, I. Georgiev, P. Slusallek, C. Dachsbacher, "Adaptive Quantization Visibility Caching," EG 2013.**
Quantizes the visibility function domain with locally adapted resolution, reducing shadow rays to <2% in some cases. Related to our variance-gated write depth — both adapt resolution to visibility complexity.
- PDF: [KIT](https://cg.ivd.kit.edu/publications/p2013/AQVC_Popov_2013/AQVC_Popov_2013.pdf) | **Auto**
- Scenes: San Miguel, Conference Room

### Guo 2020 — NEE++
**J. Guo, M. Eisemann, E. Eisemann, "Next Event Estimation++: Visibility Mapping for Efficient Light Transport Simulation," CGF/PG 2020.**
Voxel-to-voxel visibility caching for informed shadow ray Russian roulette and importance sampling. Discards up to 80% of visibility tests. Related approach — voxelized visibility rather than hash-based.
- PDF: [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.14138) / [TU Braunschweig](https://graphics.tu-bs.de/publications/guo2020next) | **Manual**

### Ulbrich 2013 — Progressive Visibility Caching
**J. Ulbrich, J. Novák, H. Rehfeld, C. Dachsbacher, "Progressive Visibility Caching for Fast Indirect Illumination," VMV 2013.**
Accelerates secondary ray computation via visibility correlation estimation between surface points. Automatically adapts cache density to visibility gradient. 4.7× throughput improvement for secondary rays.
- PDF: [EG DL](https://diglib.eg.org/items/849548c6-e849-4345-ae14-0ffa68b3175c) / [KIT](https://cg.ivd.kit.edu/english/PVCFID.php) | **Manual**

### Ward 1994 — Adaptive Shadow Testing
**G.J. Ward, "Adaptive Shadow Testing for Ray Tracing," EG Rendering Workshop 1991 (published 1994).**
Sorts light sources by potential contribution, tests only above-threshold sources for shadows, estimates visibility for the rest statistically. Foundational work on adaptive shadow ray allocation — precursor to CV+RRR.
- PDF: [Radiance Online (HTML)](https://floyd.lbl.gov/radiance/papers/erw91/erw91.html) / [Springer](https://link.springer.com/chapter/10.1007/978-3-642-57963-9_2) | **Manual**

---

## Spatial hashing / hash encoding

### Müller 2022 — Instant NGP
**T. Müller, A. Evans, C. Schied, A. Keller, "Instant Neural Graphics Primitives with a Multiresolution Hash Encoding," TOG 41(4), 2022.**
Multi-resolution hash grid for neural radiance fields. All levels written simultaneously. Backbone used by Bokšanský & Meister 2025. Keller co-authorship connects neural approach to spatial hashing lineage.
- PDF: [arXiv:2201.05989](https://arxiv.org/pdf/2201.05989.pdf) | **Auto**

### Stotko 2025 — MrHash
**P. Stotko et al., "MrHash: Resolution Where It Counts," arXiv 2025.**
Variance-driven hash grid adaptation. Directly related to our §7 variance-gated write depth — both use local variance to allocate resolution where needed.
- PDF: [arXiv:2511.21459](https://arxiv.org/pdf/2511.21459.pdf) | **Auto**

### Binder 2019 — Path Space Filtering
**N. Binder, S. Fricke, A. Keller, "Massively Parallel Path Space Filtering," arXiv 2019 / MCQMC 2020.**
Jitter-before-quantize spatial hashing for path space similarity. Source of our addressing scheme: PCG3D jitter, fingerprint design, double-hash probing. GPU-optimized hash table for massively parallel rendering.
- PDF: [arXiv:1902.05942](https://arxiv.org/pdf/1902.05942.pdf) | **Auto**
- Scenes: Bistro, San Miguel

### Jarzynski & Olano 2020 — Hash Functions for GPU Rendering
**M. Jarzynski, M. Olano, "Hash Functions for GPU Rendering," JCGT 9(3), 2020.**
Evaluates hash functions for quality (TestU01) and GPU speed. PCG3D recommended for quality/speed Pareto frontier. We use PCG3D for both jitter and addressing.
- PDF: [JCGT](https://jcgt.org/published/0009/03/02/paper.pdf) | **Auto**

### Teschner 2003 — Spatial Hashing
**M. Teschner et al., "Optimized Spatial Hashing for Collision Detection of Deformable Objects," VMV 2003.**
Foundational spatial hashing paper. Infinite regular grid compressed via hash function — no scene bounds needed. Covered in Keller's CG lectures at Ulm; likely common root for both Kugelmann 2006 and Binder 2018.
- PDF: [Author page](https://matthias-research.github.io/pages/publications/tetraederCollision.pdf) | **Auto**

---

## Control variates

### Szirmay-Kalos 2005 — Go with the Winners
**L. Szirmay-Kalos, G. Antal, M. Sbert, "Go with the Winners Strategy in Path Tracing," WSCG 2005.**
Proposes returning a control variate value on RR termination instead of zero. Kugelmann 2006 developed CV+RRR independently for the same purpose. We apply this classical technique to cached visibility.
- PDF: [ZCU](https://dspace5.zcu.cz/bitstream/11025/1454/1/Szirmay-Kalos.pdf) | **Auto**

---

## Scenes used across papers

### Cross-paper scene matrix

| Scene | ReSTIR DI | ReSTIR GI | GRIS/PT | NVC 2025 | Liu 2025 | Binder 2019 | Popov 2013 | Source |
|-------|:---------:|:---------:|:-------:|:--------:|:--------:|:-----------:|:----------:|--------|
| **Bistro Interior** | | | x | x | | x | | [NVIDIA ORCA](https://developer.nvidia.com/orca/amazon-lumberyard-bistro) |
| **Bistro Exterior** | | | | x | | | | NVIDIA ORCA |
| **Sponza** | | | | x | | | | [Crytek](https://casual-effects.com/data/) |
| **Zero Day** | x | | x | x | x | | | NVIDIA ORCA |
| **Kitchen** | | x | x | x | | | | [Bitterli resources](https://benedikt-bitterli.me/resources/) |
| **VeachAjar** | | | x | | | | | Bitterli resources |
| **San Miguel** | | | x | | | x | | Bitterli resources |
| **Emerald Square** | x | | | | | | | NVIDIA ORCA |
| **Subway** | | | | x | | | | NVIDIA |
| **Living Room** | | x | | | | | | Bitterli resources |
| **Carousel** | | | x | | | | | |
| **Opera House** | | | x | | | | | |
| **Cornell Box** | | | | | | | | Bundled / analytic |
| **Arcade** | | | | | | | | Falcor bundled |

### Priority scenes for VisCache comparison

These appear in 3+ comparison papers and should be our primary benchmarks:

1. **Bistro Interior** — GRIS, NVC, Binder. Complex lighting, many emitters. **Primary benchmark.**
2. **Zero Day** — ReSTIR DI, GRIS, NVC, Liu 2025. Dynamic emissives. Tests cache invalidation.
3. **Kitchen** (Country Kitchen) — ReSTIR GI, GRIS, NVC. Interior, indirect-dominant. Tests §11.3 GI revalidation.
4. **Sponza** — NVC, path space filtering. Single dominant light. Tests DI efficiency.

### Scene sources

| Source | URL | Notes |
|--------|-----|-------|
| NVIDIA ORCA | [developer.nvidia.com/orca](https://developer.nvidia.com/orca) | Bistro, Emerald Square, Zero Day — includes Falcor `.pyscene` |
| Bitterli Resources | [benedikt-bitterli.me/resources](https://benedikt-bitterli.me/resources/) | 32 scenes (Tungsten/pbrt). Falcor has pbrt-v4 importer |
| Casual Effects | [casual-effects.com/data](https://casual-effects.com/data/) | Sponza, San Miguel mirrors |
| Falcor bundled | `Falcor/media/Arcade/` | Arcade sample scene |

For automated download of Bistro + Sponza: `./scripts/download_scenes.sh`

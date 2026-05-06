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
**D. Lin, M. Kettunen, B. Bitterli, J. Pantaleoni, C. Yuksel, C. Wyman, "Generalized Resampled Importance Sampling: Foundations of ReSTIR," ACM TOG 41(4) / SIGGRAPH 2022, pp. 75:1–75:23.**
Unifying theory for ReSTIR. Introduces GRIS (chained resampling with bijective shift mappings between domains, MIS weights with Jacobians), the hybrid shift (reconnection + random replay) for paths through specular vertices, and ReSTIR PT itself. DQLin/ReSTIR_PT is the reference implementation we port to Falcor 8.0. Essential baseline for §9.3, §9.5, and §13 Table 3 ground truth. Lin 2026 Enhanced is the engineering follow-up.
- Paper PDF: [Utah Graphics Lab](https://graphics.cs.utah.edu/research/projects/gris/sig22_GRIS.pdf) | **Auto**
- Supplemental PDF (S.1 MIS-weight derivations, hybrid-shift Jacobian, light-source MIS, glossy material handling): [Utah Graphics Lab](https://graphics.cs.utah.edu/research/projects/gris/GRIS_supplemental.pdf) | **Auto**
- Source: [DQLin/ReSTIR_PT (Falcor 4.4)](https://github.com/DQLin/ReSTIR_PT)
- Scenes: Bistro, Zero Day, Veach Ajar, Country Kitchen

### Liu 2025 — Reservoir Splatting
**J. Liu et al., "Reservoir Splatting for Temporal Path Resampling and Motion Blur," SIGGRAPH 2025.**
Forward-projects primary hits for temporal reuse instead of backprojection. Orthogonal to VisCache — addresses path reuse robustness under camera motion, not visibility cost. Enables motion blur for ReSTIR.
- PDF: [NVIDIA Research](https://research.nvidia.com/labs/rtr/publication/liu2025splatting/liu2025splatting_paper.pdf) | **Auto**
- Scenes: Bistro, Zero Day

### Zheng et al. 2024 — ReSTIR PG
**Z. Zheng, P. Sen, R. Ramamoorthi, "ReSTIR PG: Path Guiding with Spatiotemporally Resampled Reservoirs," SIGGRAPH Asia 2024.**
Bridges GRIS theory and path guiding by treating the path-guiding distribution as a reservoir-sampled cache. Belongs to both threads — ReSTIR-family and path-guiding — and is a useful cross-thread reference for the §3.0 substrate-convergence claim. Cites the ReSTIR lineage deeply; its substrate is a per-region reservoir of guiding samples, structurally similar to ReGIR but with path-guiding semantics.
- PDF: [UCSD preprint](https://cseweb.ucsd.edu/~ravir/zhengsiga.pdf) | **Auto**

### Zhang 2024 — Area ReSTIR
**S. Zhang, D. Lin, M. Kettunen, C. Yuksel, C. Wyman, "Area ReSTIR: Resampling for Real-Time Defocus and Antialiasing," ACM TOG 43(4) / SIGGRAPH 2024.**
Extends ReSTIR reservoirs to integrate over each pixel's 4D ray space (subpixel filter `(u,v)` × lens area `(s,t)`) via subpixel-tracking temporal reuse with non-integer motion vectors and a new shift mapping for DoF. Robustifies reuse against high-frequency normals/geometry/edge discontinuities; final shadow ray structure unchanged so CV+RRR plugs in unmodified.
- PDF: [NVIDIA Research](https://research.nvidia.com/labs/rtr/publication/zhang2024area/zhang2024area.pdf) | **Auto**

### Lin 2026 — ReSTIR PT Enhanced
**D. Lin, M. Kettunen, C. Wyman, "ReSTIR PT Enhanced: Algorithmic Advances for Faster and More Robust ReSTIR Path Tracing," Proc. ACM CGIT 9(1) / I3D 2026.**
Engineering follow-up to GRIS / ReSTIR PT giving a **2–3× speedup** with reduced color/correlation/disocclusion artifacts. Five contributions, of which three are reusable on any spatiotemporal-resampling pipeline (asterisked in §1):
1. **Paired spatial reuse (§3)** — Pre-computed pairing texture links pixel A↔B; once A reuses from B, B reuses from A *for free* (shared shifts), halving spatial cost. Random-walked Gaussian over a 254×254 tileable texture, shuffled per frame.
2. **Footprint-based reconnection criteria (§4)** — Replaces the ad-hoc roughness/distance thresholds of Lin 2022 with a dual primary-ray-footprint test against `R_pri = sqrt(||x0−x1||²·cosθ / 4π)` (`c = 0.02`). Same `R_pri` we use for analytical cell-size derivation in §3.0; identical primary-ray footprint formalism as Müller 2021 NRC and Bekaert 2003.
3. **Duplication maps (§5)** — Per-frame 17×17 neighborhood count of pixels sharing the same initial-sample seed → duplication score `D∈[0,1]` adaptively reduces the temporal `c_Cap` via `lerp(c_default, c_min, D^α)` with `α=0.1`. Trades ~3% bias for elimination of correlation blobs without touching the shift mapping.
4. **Unified DI+GI single reservoir (§6.1)** — Path tree includes a length-2 NEE ray from `x1`; one RIS pass selects across direct *and* indirect paths into one reservoir. Drops the separate ReSTIR DI pass and *improves* glossy DI quality via path MIS.
5. **Misc GPU optimizations (§6.2–6.4)** — Stream compaction for replay, forced NEE light reconnection, RR only at initial sampling (not replay), reservoir compression to 64 B, vector-valued resampling weights for free chroma denoising, dual motion vectors (Zeng 2021) for disocclusions.
- PDF: [NVIDIA Research](https://research.nvidia.com/labs/rtr/publication/lin2026restirptenhanced/lin2026restirptenhanced.pdf) | **Auto**
- Scenes: Veach Ajar, Carousel, Opera House, Bathroom, Watercolor, Zero Day, Crown, Spaceship, Kitchen, Tower Bridge

## Mutations and shift-mapping lineage (algorithmic basis of GRIS)

GRIS / ReSTIR PT (Lin 2022) is the fusion of two algorithmic threads: Bitterli's reservoir
resampling for ReSTIR DI (above) and the path-space mutation / gradient-domain shift-mapping
machinery below. The Jacobian `|∂T/∂X|` plays an identical role in Metropolis acceptance, in
gradient-domain shift weights, and in GRIS resampling weights — what changed across two
decades was *what we do with it*: accept/reject (1997), finite-difference gradients (2013),
Markov-free reservoir resampling (2022). The "non-Markovian chain" framing GRIS uses for
ReSTIR (Lin 2022, p.3 + p.12) makes the relationship explicit. MK2006's bidirectional /
backtracing imperfect-reconnection sketch was conceptually a Metropolis-style path
transformation, framed informally six years before Lehtinen 2013 formalised the Jacobian.

### Veach & Guibas 1997 — Metropolis Light Transport
**E. Veach, L. J. Guibas, "Metropolis Light Transport," SIGGRAPH 1997.**
Treats path space as a probability distribution; uses Metropolis-Hastings to sample from it via path-space mutations (lens perturbation, caustic perturbation, bidirectional mutation, lens subpath mutation). Each mutation is a transformation `T: Ω → Ω` on paths with Jacobian `|∂T/∂X|` appearing in the acceptance ratio. The "imperfect reconnection at the sensor" insight that MK2006 took from this paper: lens perturbation explicitly exploits the pixel filter's 2D area integration so that connections at the sensor side don't need to land on a specific point.

### Kelemen, Szirmay-Kalos, Antal & Csonka 2002 — PSS-MLT
**C. Kelemen, L. Szirmay-Kalos, G. Antal, F. Csonka, "A Simple and Robust Mutation Strategy for the Metropolis Light Transport Algorithm," Eurographics 2002.**
Moves Metropolis mutations into primary sample space (PSS): the path is the deterministic mapping `x̄ = X(ū)`, mutations are perturbations of the random numbers `ū → ū'`. PSS Jacobian replaces the path-space Jacobian. **The same parameterization Lin 2022 GRIS and Lin 2026 §6 (RR-PSS-decoupling) use verbatim.** Cited explicitly in GRIS §2 background.

### Lehtinen, Karras, Laine, Aittala, Durand & Aila 2013 — Gradient-Domain MLT
**J. Lehtinen et al., "Gradient-Domain Metropolis Light Transport," ACM TOG 32(4) / SIGGRAPH 2013.**
**First introduces shift mappings between neighbouring pixels' path domains** — `T: Ω_neighbor → Ω_current` with explicit Jacobian — to estimate finite-difference path-space gradients. Hybrid shift, manifold shift, half-vector shift all originate here. ReSTIR PT 2022's hybrid shift is *literally* Lehtinen 2013's hybrid shift with the gradient interpretation removed. Cited explicitly in GRIS §2 background and §7.

### Kettunen, Manzi, Aittala, Lehtinen, Durand & Zwicker 2015 — Gradient-Domain BDPT
**M. Kettunen et al., "Gradient-Domain Bidirectional Path Tracing," EGSR 2015.**
Removes the Markov chain from the gradient-domain framework while keeping the shift mappings — non-Markovian shifts driving deterministic-resampling BDPT. The conceptual step from Lehtinen 2013 (chain) to Lin 2022 GRIS (reservoir) goes through this paper. Cited explicitly in GRIS §2.

### Hedstrom, Kettunen, Lin, Wyman & Li 2025 — ReSTIR BDPT
**T. Hedstrom, M. Kettunen, D. Lin, C. Wyman, T.-M. Li, "ReSTIR BDPT: Bidirectional ReSTIR Path Tracing with Caustics," ACM TOG 44 / 2025.**
Brings bidirectional mutations back into GRIS via an extended path space `(x̄, τ)` with sampling-technique-aware MIS, a bidirectional hybrid shift (forward hybrid + reverse hybrid for `t ≤ 1` light-tracing techniques), and per-pixel caustic reservoirs. **§A reformulates caustic temporal reuse via a pixel filter `h_i(x̄)`** — uses a 1-pixel box filter by default but explicitly supports wider filters; the `(u,v) × (s,t)` machinery from Area ReSTIR 2024 is *not* combined with it (the cross-product is open). Most-MLT-like ReSTIR variant; the closest published descendant of MK2006's bidirectional/backtracing reconnection sketch.
- PDF: `docs/references/Hedstrom2025_ReSTIR_BDPT.pdf` (in repo, fetched manually) / [cwyman.org preprint](https://cwyman.org/papers/tog25_ReSTIR_BDPT.pdf)
- Source: [Shmaug/ReSTIR-BDPT (Falcor)](https://github.com/Shmaug/ReSTIR-BDPT)

---

### Boksanský, Jukarainen & Wyman 2021 — ReGIR
**J. Boksanský, P. Jukarainen, C. Wyman, "Rendering Many Lights with Grid-Based Reservoirs," Ray Tracing Gems II, Ch. 23, 2021.**
World-space uniform grid where each cell holds a reservoir of pre-resampled light samples (RIS at the cell centre). Shading queries pick from the cell's reservoir instead of the global light pool — single hash lookup replaces a per-shade RIS pass. Direct precedent for our `WSCellPool` (72 B/slot, N=8): the K-RIS draw + winner write-back in PathTracer.slang is the GPU-grid resampling step from this chapter, generalized to ride the VisCache posA cascade. Section worth re-reading: cell-centre proxy distance bias and the temporal blending rule.
- PDF: [cwyman.org](https://cwyman.org/papers/rtg2-manyLightReGIR.pdf) | **Auto**

### Boissé 2021 — World-Space ReSTIR
**G. Boissé, "World-Space Spatiotemporal Reservoir Reuse for Ray-Traced Global Illumination," SIGGRAPH Asia 2021 Technical Communications.**
First world-space reservoir scheme: hashed spatial cells store reservoirs keyed by quantized position+normal, queried at hit points for spatiotemporal reuse independent of screen connectivity. Direct precedent for our WS-ReSTIR layer riding on VisCache's posA cascade. Compare cell-keying choices (single resolution + jitter vs. our multi-level cascade with `wsLevelOffset`) and M-cap/MIS bias handling.
- PDF: [GPUOpen](https://gpuopen.com/download/publications/SA2021_WorldSpace_ReSTIR.pdf) | **Auto**

### Zhang 2023 — World-Space Path Resampling
**H. Zhang, B. Wang, "World-Space Spatiotemporal Path Resampling for Path Tracing," CGF / Pacific Graphics 2023.**
Caches whole sub-paths (not just final shadow connections) into a normal-aware hash grid; sub-paths starting from non-primary vertices become reusable. Reports 16.6–41.9% MSE reduction over screen-space ReSTIR PT at 4–8% extra cost. Independent re-development of the pos+normal+grid-cell visibility-cache key from **Kugelmann 2006 §3.2.2**, which lists "depth value, surface orientation, occupied grid cell" as cache-grouping criteria 17 years earlier. We already do this on both the cache (`VisCache.slang:597–614`) and `WSCellPool` (`wsResolveCellPoolAddr(posA, faceN)`); cite Zhang 2023 as parallel/downstream evidence, not as the source of the design.
- PDF: [Author preprint](https://wangningbei.github.io/2023/ReSTIR_files/paper_ReSTIRGI.pdf) | **Auto**

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

## RR / splitting / adaptive sampling theory

### Vorba & Křivánek 2016 — ADRRS
**J. Vorba, J. Křivánek, "Adjoint-Driven Russian Roulette and Splitting in Light Transport Simulation," TOG 35(4), 2016.**
Sets RR/splitting factors from path contribution × adjoint estimate, holding contribution roughly constant. Foundational result that RR should follow a contribution proxy, not local reflectance. Theoretical anchor for any cost-aware RR extension to CV+RRR.
- PDF: [CGG (Charles University)](https://cgg.mff.cuni.cz/~jaroslav/papers/2016-adrrs/2016-vorba-adrrs-paper.pdf) | **Auto**

### Rath 2022 — EARS
**A. Rath, P. Grittmann, S. Herholz, P. Weier, P. Slusallek, "EARS: Efficiency-Aware Russian Roulette and Splitting," TOG 41(4) / SIGGRAPH 2022.**
Iteratively learns efficiency-optimal RR/splitting factors from per-cell variance **and** cost. Proves convergence to the efficiency maximum given perfect estimates. Direct upgrade path for our `varThreshold`: variance-only gating misses the high-variance + high-cost regime that step 18 found vt-saturated on Sponza.
- PDF: [Saarbrücken Graphics](https://graphics.cg.uni-saarland.de/papers/rath-2022-ears.pdf) | **Auto**

---

## World-space / hash-based radiance caches

### Müller 2021 — Neural Radiance Cache (NRC)
**T. Müller, F. Rousselle, J. Novák, A. Keller, "Real-Time Neural Radiance Caching for Path Tracing," TOG 40(4) / SIGGRAPH 2021.**
Fully-online-trained neural network as a world-space radiance cache. Self-training trick simulates infinite-bounce GI from few-bounce queries. ~2.6 ms overhead at 1080p. Caches outgoing radiance; we cache visibility — same idea, different quantity. Now shipped as part of NVIDIA RTXGI 2.0.
- PDF: [tom94.net preprint](https://tom94.net/data/publications/mueller21realtime/mueller21realtime.pdf) | **Auto**

### Majercik 2019 — DDGI
**Z. Majercik, J.-P. Guertin, D. Nowrouzezahrai, M. McGuire, "Dynamic Diffuse Global Illumination with Ray-Traced Irradiance Fields," JCGT 8(2), 2019.**
World-space probe grid with directionally resolved irradiance + visibility, updated each frame by ray tracing. Probe-based rather than hash-based, but the "world-space proxy queried at every hit" pattern is shared. Reference point for non-hashed world-space caches.
- PDF: [JCGT](https://jcgt.org/published/0008/02/01/paper-lowres.pdf) | **Auto**

---

## Path guiding / online sampling proxies

### Müller 2017 — Practical Path Guiding
**T. Müller, M. Gross, J. Novák, "Practical Path Guiding for Efficient Light-Transport Simulation," CGF 36(4) / EGSR 2017.**
SD-tree (spatial binary tree × directional quadtree) records incident radiance during rendering; subsequent paths sample from it. Canonical reference for online-learned proxy in graphics. We cite for the philosophy ("learn during render"), not the data structure.
- PDF: [tom94.net preprint](https://tom94.net/data/publications/mueller17practical/mueller17practical.pdf) | **Auto**

### Vévoda, Kondapaneni & Křivánek 2018 — Bayesian Light Sampling
**P. Vévoda, I. Kondapaneni, J. Křivánek, "Bayesian online regression for adaptive direct illumination sampling," TOG 37(4) / SIGGRAPH 2018.**
Per-region light-selection PDF learned online by Bayesian regression; uses control variates for further variance reduction. Closest philosophical match to CV+RRR — same per-cell-statistics + control-variates structure, applied to light selection rather than visibility.
- PDF: [CGG (Charles University)](https://cgg.mff.cuni.cz/~jaroslav/papers/2018-bayesianlighting/2018-vevoda-bayesianlighting-paper.pdf) | **Auto**

---

## Denoising (background)

### Schied 2017 — SVGF
**C. Schied et al., "Spatiotemporal Variance-Guided Filtering: Real-Time Reconstruction for Path-Traced Global Illumination," HPG 2017.**
Reference real-time denoiser. Temporal accumulation + variance-guided wavelet filter. We compare in pre-tonemap EXR specifically to isolate VisCache from SVGF-style filtering, but cite for context: the per-cell variance VisCache uses for trust gating is a structural analogue of SVGF's per-pixel variance estimate.
- PDF: [NVIDIA Research preprint](https://research.nvidia.com/sites/default/files/pubs/2017-07_Spatiotemporal-Variance-Guided-Filtering%3A/svgf_preprint.pdf) | **Auto**

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

### Binder 2018 — Jittered Spatial Hashing (talk)
**N. Binder, S. Fricke, A. Keller, "Fast Path Space Filtering by Jittered Spatial Hashing," SIGGRAPH 2018 Talks.**
Original short paper for the jitter+quantize-then-hash scheme later expanded in Binder 2019. Cell size derived from ray footprint / area pdf at the shading point — close cousin of our adaptive `footprintScale` knob and a cleaner derivation than our hand-tuned `quantSceneScale`.
- PDF: [SIGGRAPH archive](https://history.siggraph.org/wp-content/uploads/2022/09/2018-Talks-Binder_Fast-Path-Space-Filtering-by-Jittered-Spatial-Hashing.pdf) | **Auto**

### Boissé 2022 — GI-1.0 (Two-Level Radiance Cache)
**G. Boissé et al., "GI-1.0: A Fast Scalable Two-Level Radiance Caching Scheme for Real-Time Global Illumination," GPUOpen 2022.**
Production-grade hash-grid radiance cache with explicit two-level structure. Worth reading next to our multi-level cascade: their level-promotion / decay heuristics and cell-update policy are directly applicable to our `numLevels` × `quantShift` ladder.
- PDF: [GPUOpen](https://gpuopen.com/download/publications/GPUOpen2022_GI1_0.pdf) | **Auto**

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

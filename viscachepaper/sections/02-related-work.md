# 2. Related Work

## 2.1 Foundation: Kugelmann [2006]

This paper builds directly on [Kugelmann 2006], a thesis that proposed three independent cache experiments within a spatial hash grid [Teschner et al. 2003]: (1) irradiance (point, direction) → ℝ, (2) binary visibility (point, point) → {0,1}, and (3) free-path distance (point, direction) → ℝ≥0. Each used CV+RRR correction rates driven by the respective variance, applied to shadow-ray reduction in instant radiosity. The binary visibility experiment is the direct ancestor of this work. The thesis was broader (irradiance + visibility + free-path) but shallower in each: fixed-resolution single-level hash, variance driving only the correction rate, CPU-only implementation. We narrow to binary visibility and deepen: robust hashing, collision handling, multilevel LOD with variance-driven spatial resolution, and real-time GPU execution. The remaining experiments — irradiance caching and free-path distance — are not pursued here but remain viable directions for future work.

## 2.2 Visibility Caching

Ward [1994] first observed that shadow-ray decisions can be guided by spatial statistics — sorting lights by potential contribution and estimating visibility for below-threshold sources rather than tracing. This is the conceptual ancestor of all visibility caching: don't trace shadow rays you can predict.

Popov et al. [2013] developed adaptive quantization visibility caching, adapting resolution to local visibility complexity via octree subdivision, reporting less than 2% of shadow rays needed. Their adaptive-resolution idea is related to our variance-gated write depth, but uses explicit octree subdivision rather than hash-level selection. Ulbrich et al. [2013] proposed progressive refinement of cached visibility, sharing our philosophy that cache quality improves over frames. Both are offline, CPU-based.

Guo, Eisemann and Eisemann [2020] (NEE++) cache voxel-to-voxel visibility probability in a 6D domain with bidirectional symmetry and standard RR rejection, reporting 80% shadow ray reduction. Their dense D³×D³ matrix (16³ voxels, ~32 MB, single resolution) does not scale to large scenes. Our approach improves on NEE++ in three specific ways: (a) sparse multilevel hash instead of dense matrix; (b) CV+RRR instead of standard RR — returning μ on termination rather than zero reduces residual variance; (c) real-time GPU implementation.

Concurrent with this work, Bokšanský and Meister [2025] feed neural visibility estimates (Instant-NGP backbone [Müller et al. 2022]) into weighted reservoir sampling for light selection — the same visibility-weighted selection idea as our Sec. 9.1. Their approach operates in biased mode by default, using network output directly for shading when confident. CV+RRR (Sec. 8) would make their biased mode unbiased by construction — the technique applies identically to any data structure that provides a mean visibility estimate μ.

## 2.3 Spatial Hashing

Teschner et al. [2003] established spatial hashing for collision detection: an infinite regular grid compressed to a finite table via hash function, requiring no scene bounds. This was taught in Keller's computer graphics lectures at Universität Ulm and is the pedagogical root of both [Kugelmann 2006] and subsequent GPU hash table work.

Binder et al. [2018] applied spatial hashing to path-space filtering with jitter before quantization, fingerprint-based collision detection, and double-hash probing. We adopt their hash table mechanics but change the jitter seed: Binder seeds from the preliminary cell index (all positions in one cell share the same jitter), producing sharp, persistent boundary steps — a systematic bias. We seed from the unquantized position bits, giving each surface point independent jitter. This converts boundary artifacts from irreducible bias into reducible variance — the standard Monte Carlo trade-off. The jitter is not merely noise; it acts as an intrinsic box filter across cell boundaries (Sec. 4).

Gautron [2020, 2021] demonstrated LOD level encoded directly in the hash function for real-time ray-traced AO, with viewing-distance-based cell size selection. We adopt this design: level index in the hash key, multiple resolutions in one flat table, distance-gated selection. Prior multilevel hash approaches — separate tables per level [Müller et al. 2022], octree-like hierarchical indirection, dense multi-resolution grids — were all more complex for our use case and performed worse. The flat-table approach is simple, has no indirection overhead, and the LOD-in-key design means entries at different levels can coexist and be evicted independently.

Stotko et al. [2025] (MrHash) independently developed variance-driven resolution adaptation in a flat hash for TSDF reconstruction — the same principle as our variance-gated write depth, applied to a different domain.

For hash noise we use pcg3d [Jarzynski and Olano 2020], a GPU hash function that passes all but one BigCrush test at ~12 ALU with no lookup table.

## 2.4 Control Variates

Szirmay-Kalos, Antal and Sbert [2005] proposed a "go with the winners" strategy: on RR termination, return a control-variate prediction instead of zero, eliminating the variance spike from terminated paths. Kugelmann [2006] developed CV+RRR independently for the same purpose. We do not claim CV+RRR as a contribution — it is a classical technique. We apply it to cached binary visibility, where the Bernoulli structure (var = μ(1−μ)) makes the variance signal free and the coupling to write-depth gating (Sec. 8) creates a self-regulating loop that only becomes possible with a multilevel cache.

## 2.5 Integration Targets (Orthogonal)

The visibility cache is agnostic to the algorithm that generates visibility queries. We demonstrate integration with ReSTIR [Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022] and note compatibility with Area ReSTIR [Zhang et al. 2024] and Reservoir Splatting [Liu et al. 2025], but these are *integration targets*, not related work in the visibility caching sense. The same cache applies equally to instant radiosity (as in [Kugelmann 2006]), classical path tracing with next-event estimation, or any algorithm evaluating pairwise visibility. ReSTIR is a particularly good fit because spatial reuse concentrates many pixels onto shared light/secondary-hit pairs, naturally amortizing cache lookups — but this is a property of the integration, not of the cache.

ReSTIR DI [Bitterli et al. 2020] introduced resampled importance sampling for direct lighting. Ouyang et al. [2021] and Lin et al. [2022] extended this to path reuse, where revalidation rays test visibility from the current shading point to a neighbor's secondary hit. The biased/unbiased tradeoff — skip revalidation (light leaks) vs. always retrace (expensive) — is what makes GI revalidation our strongest integration case (Sec. 9.3). CV+RRR resolves this tradeoff: unbiased revalidation at near-biased-skip cost.

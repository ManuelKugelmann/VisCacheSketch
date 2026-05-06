# Reference Summaries — VisCache Relevance & Transitive Citations

Each entry explains **why** the paper matters to VisCache and lists transitive citations we may need.

---

## Core lineage (direct ancestors)

### Kugelmann 2006 — Efficient Adaptive Global Illumination Algorithms
**Diplomarbeit, Universität Ulm. Supervisor: A. Keller.**

Three independent cache experiments in a fixed-resolution single-level spatial hash:
(1) irradiance cache, (2) binary visibility cache, (3) free-path distance cache.
Each uses CV+RRR (control-variate Russian roulette residual) correction driven by per-cell variance.

**VisCache link:** This paper *is* experiment (2) brought to real-time GPU 20 years later.
Every core idea — spatial hash addressing, binary visibility as cached quantity, CV+RRR
as unbiased estimator, variance-driven write gating — originates here. The multilevel
hierarchy and GPU-parallel design are new.

**Transitive citations:**
- Teschner et al. 2003 — spatial hashing in the academic literature (not cited in MK2006; not the inspiration; ODE was)
- Szirmay-Kalos et al. 2005 — CV+RRR "go with the winners" (independent parallel development)

---

### Szirmay-Kalos 2005 — Go with the Winners Strategy in Path Tracing
**WSCG 2005.**

On Russian roulette termination, return the control variate value μ instead of zero.
This converts a high-variance binary estimator (0 or 1/p) into a low-variance residual
estimator around μ. Unbiased as long as μ converges to the true mean.

**VisCache link:** CV+RRR is the core estimator in every VisCache integration point
(§8, §11.1 DI, §11.3 GI revalidation). The cached visibility probability μ serves as
the control variate. Shadow rays fire only when RR selects — at rate |V−μ|, which
vanishes as μ improves. Kugelmann 2006 developed this independently.

**Transitive citations:**
- Arvo & Kirk 1990 — particle tracing; "Russian roulette" term origin
- Veach 1997 — MIS framework; RR as unbiased path termination

**Note:** Citation in references.md still reads "(Exact citation TBD)" — should be:
L. Szirmay-Kalos, G. Antal, M. Sbert, "Go with the Winners Strategy in Path Tracing,"
*Proc. WSCG*, pp. 49–56, 2005.

---

## Addressing & hash design

### Binder 2018/2019 — Path Space Filtering
**GPU Zen 2, 2018; arXiv:1902.05942, 2019.**

Jitter-before-quantize spatial hashing for path-space similarity filtering. Key
contributions adopted by VisCache: (a) PCG3D jitter seeded from cell index,
(b) fingerprint-based collision detection via second hash chain, (c) double-hash
probing, (d) GPU-parallel open-addressing hash table.

**VisCache link:** Source of our addressing scheme (§4). We adopt jitter-before-quantize
but change the jitter seed from cell index to position bits — this replaces Binder's
sharp cell-boundary steps (systematic bias) with probabilistic boundary membership
(reducible variance). Fingerprint and double-hash probe are used directly.

**Transitive citations:**
- Keller et al. 2014/2016 — precursor Fourier histogram similarity (dropped from our refs; subsumed)
- Pharr et al. 2016 — PBRT; path space formalization

---

### Teschner 2003 — Optimized Spatial Hashing for Collision Detection
**VMV 2003.**

Foundational paper establishing spatial hashing: infinite regular grid compressed to
finite table via hash function. No scene bounds needed. Simple, O(1) lookup.

**VisCache link:** The infinite-grid-via-hash concept underlies all of VisCache's
addressing. **Not** the inspiration for MK2006 (Teschner is not in the 2006
bibliography; the practical inspiration was Russell Smith's ODE, which used
spatial hashing for broad-phase collision detection and predates Teschner 2003
by two years). Teschner is the academic-literature ancestor of the path-filtering
thread (Binder 2018/19) and the broader rendering convergence; we cite it for
that role, not as a pedagogical root for MK2006.

**Transitive citations:** None needed (foundational; self-contained).

---

### Jarzynski & Olano 2020 — Hash Functions for GPU Rendering
**JCGT 9(3), 2020.**

Systematic evaluation of hash functions for quality (TestU01 BigCrush) and GPU speed.
PCG3D recommended at the quality/speed Pareto frontier: passes BigCrush, ~12 ALU, no LUT.

**VisCache link:** PCG3D is used for both jitter generation and hash addressing in
VisCache.slang. Quality matters because poor hashing would create systematic cell
clustering, biasing the cache. Speed matters because hashing runs per ray per level.

**Transitive citations:**
- O'Neill 2014 — PCG family (permuted congruential generators); original algorithm

---

### Müller 2022 — Instant Neural Graphics Primitives
**TOG 41(4), 2022.**

Multi-resolution hash grid storing learned features; all levels written simultaneously;
MLP combines multi-scale information. Backbone for neural radiance fields.

**VisCache link:** Referenced for architectural comparison with Bokšanský 2025 (neural
visibility cache uses instant-NGP backbone). VisCache's multilevel hash is conceptually
similar but stores scalar probabilities directly — no MLP, no training, deterministic
lookup. Keller co-authorship connects neural hash grids to the spatial hashing lineage.

**Transitive citations:** None needed (we reference it for context, not technique).

---

### Stotko 2025 — MrHash: Resolution Where It Counts
**arXiv:2511.21459, 2025.**

Variance-driven hash grid adaptation for TSDF reconstruction. Allocates finer resolution
where local variance is high; coarsens where signal is smooth.

**VisCache link:** Directly parallels §7 variance-gated write depth. Both use local
variance to drive resolution allocation. MrHash operates in TSDF domain; VisCache in
visibility domain. Independent concurrent development of the same principle.

**Transitive citations:** None needed.

---

## ReSTIR family (integration targets)

### Bitterli 2020 — ReSTIR DI
**TOG 39(4), 2020.**

Resampled Importance Sampling (RIS) with spatiotemporal reservoir reuse for direct
lighting. Target PDF p̂ = f·L·G·V. Temporal reuse streams new candidates into
per-pixel reservoirs; spatial reuse shares among neighbors.

**VisCache link:** Primary DI integration point (§11.1). Standard ReSTIR DI uses V=1
(no visibility) in the target PDF during candidate generation, then pays a final shadow
ray. VisCache replaces V=1 with cached μ for better candidate weighting, and gates the
final shadow ray via CV+RRR. Both are drop-in modifications at the RTXDI API level.

**Transitive citations:**
- Talbot et al. 2005 — RIS foundations (streaming weighted reservoir)
- Veach & Guibas 1995 — MIS (multiple importance sampling)

---

### Ouyang 2021 — ReSTIR GI
**CGF 40(8), 2021.**

Extends ReSTIR to indirect illumination via path reservoirs with spatial/temporal reuse.
Revalidation requires k≈5 retrace rays per pixel to maintain unbiasedness — the dominant
cost bottleneck.

**VisCache link:** GI revalidation integration point (§11.3). VisCache gates revalidation
shadow rays via CV+RRR, reducing cost from ~5 to ~0.5–1.0 rays per pixel while preserving
unbiasedness. This is the highest-impact integration point for total frame time.

**Transitive citations:**
- Bitterli et al. 2020 — ReSTIR DI (foundation)
- Talbot et al. 2005 — RIS (foundation)

---

### Lin 2022 — GRIS / ReSTIR PT
**TOG 41(4), 2022.**

Unifying theory: Generalized Resampled Importance Sampling. Proves conditions for
unbiased reuse. DQLin/ReSTIR_PT is the reference Falcor implementation.

**VisCache link:** Essential baseline for §11.3 Table 3 ground truth. We port
DQLin/ReSTIR_PT to Falcor 8.0 and compare VisCache-augmented ReSTIR GI against it.
GRIS theory also validates that CV+RRR gating preserves the unbiasedness guarantees.

**Transitive citations:**
- Bitterli et al. 2020, Ouyang et al. 2021 — unified by GRIS
- Talbot et al. 2005 — original RIS

---

### Zhang 2024 — Area ReSTIR
**S. Zhang, D. Lin, M. Kettunen, C. Yuksel, C. Wyman. ACM TOG 43(4) / SIGGRAPH 2024.**

Extends ReSTIR reservoirs to integrate over each pixel's 4D ray space — pixel filter
`(u,v)` × lens aperture `(s,t)` — instead of fixing every reservoir at the pixel
centre with a pinhole. Contributions: subpixel-tracking temporal reuse with non-integer
motion vectors that draw from multiple overlapping prior reservoirs, robust shifts in
high-frequency normal/geometry regions, a DoF shift mapping with new MIS weights,
direct support for non-box pixel filters. Improves bokeh, hair, foliage, and detailed
normal maps; final shadow ray structure unchanged.

**VisCache link:** Orthogonal extension — adds dimensions to the path domain, not to
the visibility cache. CV+RRR plugs in unmodified at the same post-shading shadow ray
point. Not a comparison target. Useful for the §3.0 thread because it shows the
ReSTIR-PT camp keeps extending dimensionality while staying agnostic to the visibility
gating layer.

**Transitive citations:** Bitterli 2020, Lin 2022 (GRIS / ReSTIR PT) — direct ancestors.

---

### Lin 2026 — ReSTIR PT Enhanced
**D. Lin, M. Kettunen, C. Wyman. Proc. ACM CGIT 9(1) / I3D 2026, DOI 10.1145/3804494.**

Engineering follow-up to GRIS / ReSTIR PT delivering 2–3× speedup with simultaneously
reduced color noise, correlation artifacts, and disocclusion noise. The architecture
of Lin 2022 is retained; the wins come from five layered changes (Table 1: 35.7→13.0 ms
on the four reference scenes).

1. **Paired spatial reuse (§3).** Pre-computed reuse texture (254×254, 16-bit `(Δx,Δy)`)
   pairs each pixel with one mirror-paired neighbor. Once A reuses from B, B reuses
   from A *for free* — same shift mapping in both directions. Built by random 2×2
   shuffles, repeats `n_σ ≈ σ²/2 + 0.5` times to hit target σ. Self-inverting; flipped
   / mirrored / transposed each frame to break correlation. Real cost reduction is
   1.63× (not 2×) due to the splitting overhead.
2. **Footprint-based reconnection criteria (§4).** Replaces Lin 2022's `‖x_k−x_{k−1}‖
   ≥ d_min` + min-roughness-pair test with a dual ray-footprint test against the
   primary ray footprint `R_pri = √(‖x0−x1‖²·⟨n_x1, x1→x0⟩ / 4π)`. Reconnect at
   `(p_{k−1}(ω_{k−1})G(x_{k−1}→x_k))⁻¹ ≥ c·R_pri²` AND a symmetric inverse-direction
   test (`c = 0.02`); single-vertex roughness `α_{x_{k−1}} ≥ α_min` retained for env
   lights and parallax. Scene-independent — same `c` works on Kitchen, San Miguel,
   Veach Ajar.
3. **Duplication maps (§5).** Each pixel counts how many of the 17×17 surrounding
   reservoirs share the same initial-sample seed → score `D ∈ [0,1] = count/288`.
   Reduces `c_Cap` adaptively: `c_Cap = lerp(c_default=20, c_min=1, D^α)` with `α=0.1`.
   Trades correlation for ~3% absolute relative bias (only inside correlated regions).
   Catches cold-cache K-RIS lock-in *without* touching the shift mapping.
4. **Unified DI+GI reservoir (§6.1).** The path tree gets a length-2 NEE ray from `x1`;
   one RIS pass selects between direct (`d=2`) and indirect (`d≥3`) paths into a single
   reservoir. Drops the separate ReSTIR DI pass entirely and *improves* glossy DI by
   exposing it to ReSTIR PT's hybrid shift. Storage: 88+16 → 64 B/reservoir, 431 →
   265 MB at 1080p.
5. **Misc GPU/quality (§6.2–6.4).** Stream compaction over pixel-neighbor pairs that
   need replay; forced NEE light reconnection (replay reuses the stored light index
   instead of re-sampling); Russian roulette only at *initial* sampling, never during
   replay (avoids killing valid reused paths); vector-valued (RGB) resampling weights
   for shading while scalar weights drive resampling — chroma noise averages out
   across spatial neighbors at zero cost; dual motion vectors [Zeng 2021] for
   disocclusion regions.

Reservoir was 88 B → 64 B; spatial reuse cost 14.8 → 4.1 ms; total frame cost on the
"Spaceship" reference: 37.1 → 12.6 ms with FLIP error 0.321 → 0.263.

**VisCache link (sorted by directness):**

- **Footprint criteria == our analytical cell-size derivation.** The §3.0 design-
  convergence row "analytical footprint entry-level" is the *same* `R_pri` formula
  Lin 2026 uses for shift-validity. Both compute primary-ray footprint from
  `‖x0−x1‖²·cos(θ)/4π`. Direct cross-cite: their reconnection-vertex check and our
  cascade-level pick are two faces of the same primitive. Worth a paragraph in §3 or
  §11.3 noting the formal equivalence — same closed-form, used once for shift-validity
  on a path domain and once for cell-size on a cache domain.
- **Duplication maps == the cure for our WS-ReSTIR cold-cache lock-in.** Memory
  `project_wsrestir_visibility_blind_bias.md` documents that K-RIS without `V` in
  `p̂` plus per-pixel reservoir lock-in produces 2× worse error than vanilla on
  Bistro/Sponza. Lin 2026 §5 solves the analogous problem in screen-space ReSTIR PT
  by counting same-seed neighbors in a 17×17 window and reducing `c_Cap`. For us:
  count duplicate reservoir slots in a `WSCellPool` cell (cell-local 17×17 over the
  K=8 entries is degenerate — adapt to "fraction of K with the same seed") and
  scale the cell's contribution to outgoing K-RIS draws. This is small, additive,
  and addresses the most painful current failure mode.
- **Paired spatial reuse — directly portable to WS-ReSTIR spatial reuse.** Our
  spatial-reuse cells already step to a coarser cascade level (`wsLevelOffset=+1`).
  Pairing the reuse so A↔B share shift work gives an immediate halving of MIS-weight
  computation. Asterisked in their §1 as portable; "applies to other spatiotemporal
  reuse algorithms, e.g., Bauszat et al. 2017; Ouyang et al. 2021." Includes ours.
- **Unified DI+GI reservoir — simplifies our composition.** Currently we have a
  separate WS-ReSTIR DI layer (§9.1) plus the ReSTIR PT path. Lin 2026 §6.1 shows the
  separate DI pass is unnecessary even without our cache. With the cache: the
  unification means there's one reservoir to gate with cached `μ`, not two.
- **RR at initial only, not replay (§6.2.4).** This matches our CV+RRR philosophy:
  the rate decision belongs at the *sampling* event, not at the reuse event. Their
  rationale is identical to ours: replay-time RR kills valid paths without
  contribution-information benefit. Cite as independent confirmation.
- **Reservoir compression to 64 B.** Our `WSCellPool` slot is 72 B. Their tricks
  (lossy compression of reconnection-vertex normal/incident-radiance) are directly
  applicable — would drop us to ≤ 64 B/slot, freeing 11% of the K=8 cell pool.

**Transitive citations:** Bitterli 2020 (ReSTIR DI), Ouyang 2021 (ReSTIR GI), Lin 2022
(GRIS / ReSTIR PT — *the* baseline), Kettunen 2023 (correlation reduction via path
mutation), Sawhney 2024 (sample mutation), Zhang 2024 (Area ReSTIR — explicitly framed
as "next step" in their §8 future work). Bekaert 2002 (N-rooks blocked reuse —
discussed and rejected as too block-structured), Bekaert 2003 / Müller 2021 NRC (path
footprint precedent for §4). Zeng 2021 (dual motion vectors). Talbot 2005 (RIS).

**Action points for our paper:**
- Add Lin 2026 to §3.0 design-convergence framing as 7th independent team —
  except they hit the *same primary-ray footprint primitive* explicitly (§4), making
  the convergence claim formally tighter, not just empirically.
- Add a §11.3 paragraph linking duplication-map decorrelation to our cold-cache
  WS-ReSTIR lock-in — concrete future-work item.
- Footprint criteria reference is mandatory in §3 (cell sizing) and §11 (path-domain
  resampling).

---

### Liu 2025 — Reservoir Splatting
**SIGGRAPH 2025.**

Forward-projects ("splats") primary hits for temporal reuse instead of backprojection.
Enables motion blur for ReSTIR and improves temporal stability under camera motion.

**VisCache link:** Orthogonal — addresses path reuse robustness, not visibility cost.
Splats path reservoirs, not visibility estimates. VisCache and reservoir splatting
can coexist: splatting handles temporal reuse, VisCache handles shadow ray gating.

**Transitive citations:** None beyond ReSTIR family.

---

## Visibility caching (related / concurrent)

### Bokšanský & Meister 2025 — Neural Visibility Cache
**JCGT 14(2), 2025.**

Online-trained neural hash grid (instant-NGP backbone) caches light→surface visibility
for WRS light selection. Default mode is biased — uses network output directly as
visibility weight without correction.

**VisCache link:** Concurrent independent work, same problem. Key differences:
(a) neural network vs. deterministic hash table — VisCache has no training cost;
(b) biased by default vs. unbiased CV+RRR; (c) per-light clusters vs. per-pair entries.
Our §14 conclusion notes that CV+RRR could debias their approach.

**Transitive citations:**
- Müller et al. 2022 — instant-NGP backbone
- Anderson et al. 2021 — neural light selection (precursor idea)

---

### Guo 2020 — NEE++ (Next Event Estimation++)
**CGF/Pacific Graphics, 2020.**

Voxel-to-voxel visibility caching in 6D domain (source voxel × target voxel).
Caches visibility probability; uses standard RR to skip likely-occluded shadow rays.
Reports 80% shadow ray reduction. Dense D³×D³ matrix (16³ voxels → 32 MB).

**VisCache link:** Closest prior work. VisCache improves on NEE++ in three ways:
(a) sparse multilevel hash instead of dense matrix — scales to large scenes;
(b) CV+RRR instead of standard RR — returns μ on termination, reducing variance;
(c) real-time GPU implementation vs. offline CPU.

**Transitive citations:**
- Vévoda et al. 2018 — Bayesian online learning for light selection (related adaptive technique)

---

### Popov 2013 — Adaptive Quantization Visibility Caching
**EGSR 2013.**

Quantizes visibility function domain with locally adapted resolution. Reports <2%
shadow rays needed in favorable cases. Offline, CPU-based.

**VisCache link:** Demonstrates that spatial quantization of visibility is viable and
can be extremely effective. Related to our variance-gated write depth (§7) — both
adapt resolution to local visibility complexity. Different mechanism: Popov uses
explicit octree subdivision; we use multilevel hash with variance-gated level selection.

**Transitive citations:**
- Hašan et al. 2009 — virtual point lights with visibility clustering

---

### Ulbrich 2013 — Progressive Visibility Caching
**VMV 2013.**

Estimates visibility correlation between surface points; automatically adapts cache
density to visibility gradient. Progressive refinement — cache improves over frames.
4.7× throughput improvement for secondary rays.

**VisCache link:** Shares the progressive refinement philosophy — VisCache's EMA-updated
probability also improves over frames. Different data structure (irradiance-cache-style
records vs. hash table) and target application (offline vs. real-time).

**Transitive citations:**
- Ward et al. 1988 — irradiance caching (cache record placement strategy)

---

### Ward 1994 — Adaptive Shadow Testing for Ray Tracing
**Eurographics Rendering Workshop, 1991 (published 1994).**

Sorts lights by potential contribution; tests only above-threshold lights for shadows;
estimates visibility for the rest statistically. First published observation that shadow
ray decisions can be guided by spatial visibility statistics.

**VisCache link:** Conceptual ancestor. Ward's insight — "don't trace shadow rays you
can predict" — is exactly what CV+RRR implements with cached μ. Ward uses per-light
sorting; we use per-pair probability.

**Transitive citations:** None needed (foundational; self-contained).

---

## World-space ReSTIR / hash-keyed reservoirs

This is the cluster directly relevant to the WS-ReSTIR / `WSCellPool` work in
`Source/RenderPasses/VisCache/WSCellPool.slang` + `WSCellPoolIO.slang`. Cite ReGIR
as the primary anchor: our cell pool is a cascade-aware ReGIR.

### Boksanský, Jukarainen & Wyman 2021 — ReGIR
**"Rendering Many Lights with Grid-Based Reservoirs," Ray Tracing Gems II, Ch. 23, 2021.**

Uniform world-space grid; each cell stores a small reservoir of light samples
pre-resampled by RIS evaluated at the cell centre. Shading queries the cell's
reservoir instead of running RIS over the full light pool — single hash lookup
replaces a per-shade RIS pass. Two design choices the chapter makes explicit:
(a) cell-centre proxy distance bias and how to mitigate it via cell-centre jitter,
(b) temporal blending and M-cap for cell reservoirs.

**VisCache link:** Direct precedent for `WSCellPool` (72 B/slot, N=8). Our K-RIS
draw + winner write-back in PathTracer.slang is the GPU-grid resampling step from
this chapter, generalized over the VisCache posA cascade. The chapter assumes a
uniform grid; we substitute the multi-level cascade resolved by `wsLevelOffset`.
The two parts of the chapter to mirror in our implementation:
1. **M-cap + decay schedule** for cell-pool slots — our current "winner overwrite"
   is the simplest possible insert; the chapter's exponential M-cap gives a smoother
   bias/variance trade and is a one-line change in `WSCellPoolIO.insert`.
2. **Visibility in p̂ at fill time** (NEE-style) — directly addresses
   `wsrestir_visibility_blind_bias`: K-RIS without V was 2× worse on Bistro/Sponza
   because cold cells had no occlusion signal at x1 SPP.

**Transitive citations:**
- Talbot et al. 2005 — RIS streaming reservoir (foundation)
- Bitterli et al. 2020 — ReSTIR DI (M-cap + spatiotemporal reuse machinery)

**Status:** Cite as primary anchor for the WS-ReSTIR/cell-pool section.

---

### Boissé 2021 — World-Space Spatiotemporal Reservoir Reuse
**G. Boissé, SIGGRAPH Asia 2021 Technical Communications.**

Hashed spatial cells store **per-cell reservoirs** (not per-pixel), keyed on
quantized position+normal. Cells are reused across spatially incoherent shading
points, breaking screen-space dependence of ReSTIR. Single-resolution grid + jitter.

**VisCache link:** The screen-decoupled cousin of ReGIR. Compared to ReGIR, Boissé
runs the reservoir update in shader at every hit (closer to standard ReSTIR), where
ReGIR pre-fills cells in a separate pass. Our `WSCellPool` is closer to ReGIR; our
per-pixel temporal reservoir (already present in WS-ReSTIR DI integration) is closer
to Boissé. The two papers are complementary citations for our scheme.

Position+normal as a **joint** hash key is what we already do (cache: `qa` =
`jitterQuantize(posA)` XOR'd with octahedral-encoded `normalA`, `VisCache.slang`
:597–614; pool: `wsResolveCellPoolAddr(posA, faceN)`). Cite Boissé as the
precedent for that design, not as a future change. Position-only was dropped
long before step 18; the Sponza saturation has a different cause (ct=2
structural — see `note[f239e307]`).

**Transitive citations:**
- Bitterli et al. 2020 — ReSTIR DI (per-pixel reservoir machinery)
- Binder 2018/2019 — jittered spatial hashing (cell construction)

**Status:** Cite alongside ReGIR. Was already in `docs/references/` but missing
from REFERENCES.md — fixed in this pass.

---

### Zhang 2023 — World-Space Spatiotemporal Path Resampling
**H. Zhang, B. Wang, CGF / Pacific Graphics 2023.**

Caches whole sub-paths into a **normal-aware** hash grid, allowing reuse of paths
starting from non-primary vertices. Reports 16.6–41.9% MSE reduction over screen-space
ReSTIR PT at 4–8% extra cost. The headline result is the normal-key separation: cells
with similar normal *and* position give "more reasonable separation."

**VisCache link:** Independent re-discovery of the pos+normal cell-key idea
that already appeared in **Kugelmann 2006 §3.2.2** ("the depth value, the
surface orientation, ..., the occupied grid cell" as criteria for grouping
visibility samples into the same cache entry). Zhang 2023 / Boissé 2021 are
*downstream* of that thesis observation by 15–17 years; we already had pos+
normal on both the cache (`qa` folds octahedral `normalA`,
`VisCache.slang:597–614`) and `WSCellPool` (`wsResolveCellPoolAddr(posA, faceN)`).
Cite Zhang 2023 alongside MK2006 as parallel/downstream evidence the design is
right, not as the source of the design. The Sponza ceiling saturation is a
structural ct=2 problem (`project_sponza_trust_gate_saturated.md`), unrelated.

**Transitive citations:**
- Kugelmann 2006 §3.2.2 — original priority for pos+normal+grid-cell key
- Boissé 2021 — independent world-space reservoir re-development
- Lin 2022 — GRIS theory (unbiased reuse over heterogeneous samples)

**Status:** Cite as parallel/downstream prior art alongside MK2006, not as
the source of the cell-key idea.

---

### Boissé 2022 — GI-1.0 Two-Level Radiance Cache
**G. Boissé et al., GPUOpen Technical Report, 2022.**

Production-grade hash-grid radiance cache, deployed in AMD's GI-1.0. Two-level
structure with explicit promotion/decay heuristics: cells "graduate" from coarse
to fine when stable, decay back when underused. Solves the same coarse/fine tension
our `numLevels` × `quantShift` cascade exposes, but with an adaptive policy rather
than fixed levels.

**VisCache link:** Closest production reference for our multi-level cascade. Two
specific things to pull in:
1. **Adaptive level promotion** — our cascade picks the finest level whose cell has
   sufficient samples at lookup time, which is reactive. Their proactive promotion
   rule (insert at coarse, promote when stable) avoids the cold-start tiling that
   step 01 documents.
2. **Decay schedule** — we currently rely on EMA + `ct`; their explicit per-cell
   age + decay policy is the right shape for the per-cell adaptive `ct` direction
   noted in `project_scene_dependent_ct.md`.

**Transitive citations:**
- Boissé 2021 — same author lineage
- Müller et al. 2022 — multi-resolution hashing (architectural cousin)

**Status:** Cite as the production validation of our cascade design and as the
source for level-promotion/decay if we adopt either.

---

### Binder 2018 — Fast Path Space Filtering by Jittered Spatial Hashing (talk)
**N. Binder, S. Fricke, A. Keller, SIGGRAPH 2018 Talks.**

Original short paper for the jitter+quantize-then-hash scheme. Key analytic point:
**cell size is derived from ray footprint / area pdf at the shading point**, giving
roughly constant samples-per-cell across distance. Expanded into Binder 2019 / GPU Zen 2
with the full GPU hash table; adopted in §4 of our addressing.

**VisCache link:** The footprint-derived cell-size derivation is the analytic version
of our hand-tuned `footprintScale` / `quantSceneScale`. We currently apply
`footprintScale` as a global multiplier; their per-hit derivation (cell radius =
constant × √(area pdf · ray length²)) removes the Bistro/Sponza tuning gap and is
implementable as a per-hit scalar in `vcLookup`.

**Transitive citations:**
- Teschner et al. 2003 — spatial hashing (already cited)
- Binder 2019 — full paper version (already cited)

**Status:** Cite alongside Binder 2019 specifically when discussing the
footprint-derived cell-size choice in §4.

---

## Missing from references.md (found in code/paper)

### Gautron 2020 — Real-Time Ray-Traced Ambient Occlusion
**P. Gautron, "Real-Time Ray-Traced Ambient Occlusion of Complex Scenes using Spatial Hashing," SIGGRAPH Talks, 2020.**

World-space AO filtering via spatial hash map. Key contributions: LOD index encoded
directly into the hash function, viewing-distance-based cell size selection, and
coarse-to-fine propagation of cached values across hierarchy levels. Demonstrates
production-quality results on CAD scenes with hundreds of millions of polygons.

**VisCache link:** Direct source for our distance-gated LOD selection strategy
(VisCache.slang line 164). The idea of encoding LOD level into the hash key —
so different resolution levels coexist in the same flat table — is adopted directly.
Gautron caches AO (scalar); we cache visibility probability (scalar). Same data
structure philosophy, different cached quantity.

**Transitive citations:**
- Teschner et al. 2003 — spatial hashing foundation (already cited)

**Status:** Referenced in code and design doc but **not yet in references.md or sections/references.md**.
**Action needed:** Add to both reference lists.

---

### Gautron 2021 — Practical Spatial Hash Map Updates
**P. Gautron, "Practical Spatial Hash Map Updates," Chapter 41 in *Ray Tracing Gems II*, Apress, 2021.**

Follow-up to the 2020 talk. Details the GPU update scheme for spatial hash maps:
lock-free atomics for simple payloads (AO), extended storage for complex payloads
(16-bit floats for image-based lighting). Discusses eviction policies, temporal
stability, and handling of hash collisions under concurrent writes.

**VisCache link:** Our atomic EMA update (§6) faces the same concurrent-write
challenges. Gautron's lock-free atomics pattern for scalar payloads applies directly
to our per-cell probability update. The eviction/temporal-stability discussion
informed our decay factor design.

**Transitive citations:** None beyond Gautron 2020.

**Status:** Not yet in reference lists. Consider citing alongside Gautron 2020 if
the hash map update mechanism is discussed in detail.

---

### Talbot 2005 — Importance Resampling for Global Illumination
**J. Talbot, D. Cline, P. Egbert, "Importance Resampling for Global Illumination," EGSR 2005.**

Foundational paper for Resampled Importance Sampling (RIS). Develops importance
resampling into a variance reduction technique for Monte Carlo integration.
Demonstrates 10–70% variance reduction over standard importance sampling for direct
lighting. Introduces the streaming weighted reservoir that Bitterli 2020 later
adapts into spatiotemporal ReSTIR.

**VisCache link:** Theoretical foundation for all ReSTIR methods. The streaming
weighted reservoir (Algorithm 1 in Talbot) is the core data structure in
ReSTIRGICommon.slang (lines 29, 120) and underlies the M-cap temporal stability
mechanism. VisCache does not modify the reservoir itself — it modifies the target
PDF p̂ and gates the final visibility evaluation. Understanding RIS is necessary
to prove that CV+RRR gating preserves unbiasedness of the resampled estimator.

**Transitive citations:**
- Rubin 1988 — statistical importance resampling (SIR) from Bayesian statistics
- Veach & Guibas 1995 — MIS (combined with RIS in Talbot's framework)

**Status:** Referenced in code comments but **not in paper references**.
**Action needed:** Add if §11 discusses RIS theory or unbiasedness proof; otherwise
transitive through Bitterli 2020 and Lin 2022 is sufficient.

---

## Summary: what cites what

```
Ward 1994 ──────────────────────────────┐
                                        ├─→ "predict shadow rays from statistics"
Szirmay-Kalos 2005 ─→ CV+RRR ──────────┤
                                        │
Kugelmann 2006 ─→ spatial hash + CV+RRR ┘
    ↑ taught via                          ↓ 20 years later
Teschner 2003 ─→ spatial hashing    VisCache (this paper)
    ↓ evolved                        ↑ addressing    ↑ LOD design
Binder 2018 ─→ jitter+quantize+fp ──┘               │
    ↑ hash function from            Gautron 2020 ────┘ distance-gated LOD
Jarzynski 2020 ─→ PCG3D            Gautron 2021 ─→ atomic hash map updates
                                        ↑ integration targets
                                   ReSTIR DI/GI/PT/Area
                                        ↑ RIS from
                                   Talbot 2005

Concurrent work:
  Bokšanský 2025 (neural, biased)   ←→   VisCache (hash, unbiased)
      ↑ backbone from Müller 2022
  Stotko 2025 (variance→resolution) ←→   §7 write-depth gate
  Liu 2025 (temporal splatting)      ⊥    VisCache (orthogonal)

Historical visibility caching:
  Popov 2013 (adaptive quantization, offline)
  Ulbrich 2013 (progressive, offline)
  Guo 2020 (voxel matrix, offline) → VisCache (sparse hash, real-time)

WS-ReSTIR / hash-keyed reservoir cluster (WSCellPool):
  Talbot 2005 ─→ RIS ──┐
  Bitterli 2020 ───────┤
                       ├─→ Boksanský 2021 ReGIR ─────────→ WSCellPool (this work)
  Binder 2018/2019 ────┘     (per-cell light reservoirs;       ↑ K-RIS draw + write-back
       ↑ jitter+quantize       cell-centre proxy + M-cap)      │ riding posA cascade
                                                               │
                          Boissé 2021 WS-ReSTIR ───────────────┤ pos+normal joint key
                          Zhang 2023 WS Path Resampling ───────┤ normal-axis lesson
                          Boissé 2022 GI-1.0 ──────────────────┘ promotion/decay policy
```

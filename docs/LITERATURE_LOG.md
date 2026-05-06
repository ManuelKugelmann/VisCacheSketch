# Literature Log — Adjacent Fields Survey

Running notes on work that touches VisCache from neighbouring corners of graphics
and Monte Carlo. Each cluster has: (a) the papers that matter, (b) the takeaway
that maps onto our problem, (c) concrete hooks to existing code/ladder/notes.

PDFs added in this pass live in `docs/references/`:
`Vorba2016_ADRRS.pdf`, `Rath2022_EARS.pdf`, `Muller2021_NRC.pdf`,
`Muller2017_PracticalPathGuiding.pdf`, `Vevoda2018_BayesianLightSampling.pdf`,
`Majercik2019_DDGI.pdf`, `Schied2017_SVGF.pdf`.

---

## 1. Adaptive multi-resolution hash grids (beyond MrHash)

**MrHash — Stotko et al. 2025** (already in repo). Single flat hash table,
multiple resolution levels keyed by encoded LOD; cell resolution chosen by
**local TSDF variance**. 2.0–7.5× memory savings, up to 13× speedup over VDB.

**fVDB — Williams et al. 2024 (NVIDIA)** and **NeuralVDB 2024**. Sparse
hierarchical voxel grids built on the OpenVDB lineage. fVDB exposes the index
grid (topology) separately from the value array — the same idea as splitting
our `WSCellPool` slot from its key.

**Spatially-Adaptive Hash Encodings — Walker et al. WACV 2025**. Adaptive
multi-resolution hash encoding for neural surface reconstruction; allocates more
hash entries to high-detail regions. Variance-driven resolution allocation in
the neural setting.

**Hooks for VisCache:**
- We already do variance-driven write-depth gating (§7) and have a
  `MrHash` reference. The fVDB *separation of topology and values* is worth
  considering for `WSCellPool`: topology = posA-cascade hash entries; values =
  reservoir slots in a parallel array. Lets us resize the slot table
  independently of the cascade, useful if K is bumped from 8 to 16.
- Walker 2025's "more entries where reconstruction error is high" is the
  spatial counterpart of MrHash's variance-driven resolution. For VisCache,
  these merge: variance is our visibility-disagreement signal, and we already
  use it to pick level — but we don't currently use it to *grow* the table.

Sources: [Stotko 2025 arXiv](https://arxiv.org/abs/2511.21459) ·
[fVDB (NVIDIA)](https://research.nvidia.com/labs/prl/williams2024fVDB/fVDB.pdf) ·
[Spatially-Adaptive Hash Encodings WACV 2025](https://openaccess.thecvf.com/content/WACV2025/papers/Walker_Spatially-Adaptive_Hash_Encodings_for_Neural_Surface_Reconstruction_WACV_2025_paper.pdf) ·
[NanoVDB (Museth 2021)](https://research.nvidia.com/labs/prl/publication/nanovdb/)

---

## 2. Russian roulette & splitting (theory of when to fire shadow rays)

**ADRRS — Vorba & Křivánek 2016** (`Vorba2016_ADRRS.pdf`). Sets RR/splitting
factors from the path's expected contribution × pre-computed adjoint estimate;
contribution is held roughly constant through the path. Foundational result:
RR should be driven by a contribution proxy, not local reflectance.

**EARS — Rath et al. SIGGRAPH 2022** (`Rath2022_EARS.pdf`). Iteratively learns
**efficiency-optimal** RR/splitting factors during rendering using a
lightweight per-cell data structure storing variance + cost. Provably converges
to the efficiency-maximising factors given perfect variance/cost estimates.

**MARS — Grittmann et al. SIGGRAPH Asia 2024**. Multi-sample allocation
through RR+splitting; extends EARS to allocate samples across multiple
techniques (MIS).

**NRRS — 2025 (arXiv 2510.07868)**. Neural variant of EARS; predicts RR
factors from neural features.

**Hooks for VisCache:**
- Our CV+RRR is *exactly* the kind of estimator EARS reasons about. The
  `varThreshold` (vt) knob in §6 / step 06 picks RR rate from variance alone.
  EARS's contribution: variance *and cost* — the optimal factor depends on
  per-cell trace cost, not just variance. The Sponza ceiling regime that
  step-18 found vt-saturated is a place where EARS would predict different
  factors because tracing cost there is high (long rays, BVH descent) — a
  variance-only gate misses it.
- Concrete experiment: extend `vcLookup` to track an EWMA of *trace cost*
  alongside μ and variance, and feed (variance, cost) into the RR rate. Tiny
  shader change (one extra atomic accumulation), big potential payoff in
  bias-dominated regimes.
- ADRRS's "expected contribution" version is harder for us — we'd need an
  adjoint estimate, and we operate on visibility not radiance. Less direct.

Sources: [ADRRS (Křivánek)](https://cgg.mff.cuni.cz/~jaroslav/papers/2016-adrrs/index.htm) ·
[EARS (Saarbrücken)](https://graphics.cg.uni-saarland.de/publications/rath-sig2022.html) ·
[MARS (DL)](https://dl.acm.org/doi/10.1145/3680528.3687636) ·
[NRRS (arXiv)](https://arxiv.org/abs/2510.07868)

---

## 3. World-space radiance / hash radiance caches

**SHaRC — NVIDIA RTXGI 2.0 (2024)**. Production world-space hash radiance cache.
Two passes: (1) sparse fill via short paths into the cache, (2) shading reads
the cache instead of continuing the path. Voxel data buffer = 40 B/voxel,
collisions handled implicitly by a buffer-size-vs-collision-rate trade.

**NRC — Müller, Rousselle, Novák, Keller 2021** (`Muller2021_NRC.pdf`).
Neural network as the cache; trained online during rendering; few-bounce
path lookups give effectively infinite-bounce GI. ~2.6 ms overhead at 1080p.

**GI-1.0 — Boissé et al. 2022** (already in repo). Two-level cell promotion +
decay. Production radiance cache deployed in AMD's GI-1.0.

**DDGI — Majercik et al. 2019** (`Majercik2019_DDGI.pdf`). Probe-based, not
hash-based, but the probe→radiance lookup pattern is the same shape: world-space
proxy for incoming light, used at every hit.

**Hooks for VisCache:**
- SHaRC's two-pass structure (fill, then shade) is **the inverse of how we
  insert**: we update on every shade. SHaRC's fill pass uses short paths
  whose only purpose is to populate the cache, decoupled from main shading.
  This is one solution to `wsrestir_visibility_blind_bias` (cold cache at
  x1 SPP = noisy K-RIS): a cheap fill pre-pass populates cells before
  shading queries them. Could reuse the existing PathTracer with a few-ray
  budget per cell — orthogonal to subframes/Bayer.
- NRC vs. VisCache: NRC caches **outgoing radiance**, we cache **visibility**.
  Same idea (world-space proxy, online updates), different cached quantity.
  NRC's *self-training* trick — query the cache during training to simulate
  multi-bounce — has no obvious VisCache analogue (visibility is already
  bounded). Worth noting in the paper as a contrast: we don't need
  self-training because V is a single-shadow-ray quantity.
- GI-1.0's per-cell age + decay schedule is the most directly transferable.
  Our `ct` is global; their per-cell decay aligns with the per-cell adaptive
  ct direction in `project_scene_dependent_ct.md`.

Sources: [SHaRC (GitHub)](https://github.com/NVIDIA-RTX/SHARC) ·
[SHaRC integration docs](https://github.com/NVIDIA-RTX/SHARC/blob/main/docs/Integration.md) ·
[NRC project page](https://research.nvidia.com/labs/rtr/publication/muller2021nrc/) ·
[DDGI (JCGT)](https://jcgt.org/published/0008/02/01/) ·
[GI-1.0 (GPUOpen)](https://gpuopen.com/download/publications/GPUOpen2022_GI1_0.pdf)

---

## 4. Path guiding (closest cousin to VisCache: a learned proxy for sampling)

**Practical Path Guiding — Müller, Gerber, Gross 2017** (`Muller2017_PracticalPathGuiding.pdf`).
SD-tree (spatial binary tree × directional quadtree) records incident radiance
during rendering; subsequent paths sample from the learned distribution.
Foundational reference for online-learned proxy.

**Markov Chain Mixture Models for Real-Time DI — Dittebrandt et al. CGF 2023**.
Per-pixel Markov-chain sampler over a vMF mixture; SMIS makes it independent
of equilibrium distribution. Screen-space; *local* permutations to avoid
dependent-sample bias.

**Real-Time Markov Chain Path Guiding (MCPG) — Alber, Hanika, Dachsbacher 2025**
(DL/PACMCGIT, HPG Student Comp 1st place). Extends Dittebrandt to GI by storing
vMF-mixture sufficient statistics in **two world-space hash grids in parallel**
(adaptive + static). Verified against `merian-quake/res/shader/render_mcpg/mc.glsl`:

  - **Adaptive cell width** scales with camera distance:
    `w(pos) = 2·tan(α/2)·dist(cam, pos)`. Levels are an exponential or quadratic
    ladder of widths — matches our cascade with `forceDescendFootprintPx`.
  - **Hash key = (grid_idx, normal, level)** via `hash_grid_normal_level(...)`.
    Same shape as our `pcgHash` with normal folded into qa.
  - **Spatial sharing IS jittered cell lookup.** `grid_idx_interpolate(pos, w,
    rand)` jitters the quantized index per query — Binder 2018, identical to
    our `gJitterFilter` mode. There is **no separate neighbour-exchange pass**;
    the "stochastic resampling between adjacent cells" advertised in the
    abstract is exactly the per-query jitter giving probabilistic cell
    membership at boundaries.
  - **Multilevel = jittered level lookup.**
    `level = target + uint(-log2(1 - rand))` — a one-sided exponential offset
    *above* target. Most queries hit target; coarser levels with falling
    probability (½, ¼, ⅛, …); never queries below target.
  - **Static grid (fixed world width)** runs in parallel to the adaptive grid
    in the same buffer (offset indexing). Catches state the adaptive grid
    misses on camera teleport / fast motion — adaptive cells are camera-tied
    and lose persistence.
  - **MLE update with floor on α:** `α = max(1/N, MIN_ALPHA)` — sample-count-
    driven EWMA with a learning-rate floor that prevents stale state from
    being unable to adapt.
  - Memory: one buffer, ~10⁶ entries × 44 B = 44 MB total.

**Variance-Aware Path Guiding — Rath/Grittmann/Slusallek 2020**. Variance is
the right learning target, not radiance. Sampling proportional to a
variance-aware proxy beats radiance-proportional guidance.

**Reframing (post-MK2006-priority correction): convergent validation, not deltas to port.**

MCPG 2025 and our 2026 work arrived at structurally equivalent multilevel-hash
designs from completely different problem framings — theirs from
Dittebrandt's screen-space MCMM (vMF mixtures, MCMC, path guiding); ours
from MK2006's binary-V visibility cache (Bernoulli, CV+RRR, shadow-ray
reduction). Different cached quantity. Different update math. Different
bias defence. **Same data structure**.

Eight primitives in common (the design-convergence list):

1. Flat single-buffer hash table, levels co-mingled
2. Pos+normal joint cell key (`hash_grid_normal_level` ↔ our `qa` with oct-normal)
3. Level XOR'd into the hash key (level lives in the index, not in a separate table)
4. Distance/footprint-driven cell width (`2·tan(α/2)·dist` ↔ our `vhfCellPixels` + `forceDescendFootprintPx`)
5. Fingerprint-based collision detection
6. Jitter-before-quantize on lookup (their `grid_idx_interpolate(pos, w, rand)` ↔ our `gJitterFilter`)
7. Stochastic LOD selection (their `target + uint(-log2(1-u))` ↔ our `wsCellLevelJitter`)
8. MLE α-floor on per-cell EWMA blending (their `α = max(1/N, MIN_ALPHA)` ↔ our `mlAlphaFloorN`)

The convergence is **not on the algorithm**. Algorithms differ. The
convergence is **on the data structure**: the flat multilevel jittered spatial
hash with pos+normal cell key, fingerprint collision check, distance-driven
sizing, and α-floor blending is the right data structure for online-learned
per-cell statistics in real-time path tracing. Five other contemporary
teams (Boissé 2021, ReGIR 2021, GI-1.0 2022, SHaRC 2024, MCPG 2025)
arrived at the same design from the radiance-caching, light-reservoir,
and path-guiding lineages. We arrived at it from the visibility-caching
lineage (MK2006 → 2026). **Six independent confirmations of the design.**

**Two small probabilistic-form refinements we adopted from MCPG**
(landed 2026-05-04, framed as "matching their probabilistic form" not
"borrowing missing features"):

1. **One-sided exponential level draw.** `wsLevelJittered` now uses
   `dl = uint(-log2(1−u))` clamped to `[0, J]` — we previously had
   symmetric `dl ∈ [−J/2, +J/2]`. Querying levels below target wastes
   queries on cells finer than the ray footprint; the one-sided form
   never does. Implementation: `WSReservoirIO.slang:63–80`.
2. **MLE α-floor.** `mlAlphaFloorN` lowers the existing 1/8 in-line
   overflow-decay trigger from 0xE000 (~57K samples ≈ near-no-forgetting)
   to N* (typ. 256–1024). Steady-state per-sample weight ≈ 1/N*, the
   discrete analogue of `α = max(1/N, MIN_ALPHA)`. The 1/8-decay
   machinery was already there (race-tolerant under concurrent writers);
   only the trigger threshold is the new knob. Implementation:
   `VisCache.slang:1357–1369`.

**One genuinely additive feature MCPG has and we don't (yet):**

3. **Static grid in parallel to the camera-distance-adaptive cascade.**
   All our levels scale with camera distance; on camera teleport / fast
   motion they all go cold simultaneously. A single fixed-world-width
   hash table appended in the same buffer carries persistent state across
   camera moves. Cheap: one extra hash table, fingerprint-validated like
   the rest. Action item, unimplemented.

**Other path-guiding cluster items:**

- Variance-aware guiding (Rath 2020) reinforces EARS's lesson from §2:
  variance is the right signal everywhere, not radiance. Our EWMA already
  tracks Bernoulli variance — we just under-use it (vt is scalar threshold,
  not a proportional knob).
- Müller PG 2017 is mostly historical for us — SD-tree is heavier than what
  we need for binary visibility — but the *online learning during render*
  idea is shared, and the paper is the canonical reference.

**Citation framing for paper §3.0** (Data Structure as Convergent Design Point):
list MCPG 2025 alongside Boissé 2021 / ReGIR 2021 / GI-1.0 2022 / SHaRC
2024 as one of five independent re-developments of the design. The
[Kugelmann 2006 §3.2.2] thesis already explored the cell-keying criteria.
Frame the structural convergence as **validation that the design is right**,
not as derivation from any single contemporary work.

Sources: [PG 2017 (CGF)](https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.13227) ·
[Dittebrandt 2023 (KIT)](https://cg.ivd.kit.edu/english/mcmm.php) ·
[Real-Time Markov Chain PG 2025 (PACMCGIT)](https://dl.acm.org/doi/10.1145/3728296) ·
[Variance-aware PG (DL)](https://dl.acm.org/doi/abs/10.1145/3386569.3392441)

---

## 5. Light selection — Bayesian and neural

**Bayesian Online Regression — Vévoda, Kondapaneni, Křivánek 2018**
(`Vevoda2018_BayesianLightSampling.pdf`). Adaptive light-selection PDF learned
online via Bayesian regression. Per-region statistics; uses control variates
for further variance reduction. Contains visibility implicitly through
contribution observations. Same shape as VisCache: per-cell statistics drive
sampling.

**Neural Importance Sampling of Many Lights — SIGGRAPH 2025**. Neural
extension. Predicts light selection PDFs from neural features per shading
point. Higher quality than Vévoda but with NN cost.

**Importance Sampling of Many Lights with Adaptive Tree Splitting —
Estevez & Kulla 2018**. Dominant production technique for many lights;
splits a light tree adaptively per shade.

**Hooks for VisCache:**
- Vévoda's *per-region control variate on visibility* is the most direct
  philosophical match to CV+RRR. Different cached quantity
  (light-selection PDF vs. visibility), same correction idea (CV residual).
  Cite as a parallel application of the CV+RRR principle to light selection,
  alongside our visibility application. Already in `REFERENCE_SUMMARIES.md`'s
  "Missing from references.md" — should promote to actual reference.
- The light-tree splitting technique (Estevez/Kulla) is upstream of our
  ReSTIR DI integration — RTXDI uses a light tree under the hood. Not a
  direct VisCache cite, but useful when explaining why RTXDI's per-light
  cost is variable, which is part of why CV+RRR helps more on some lights
  than others.

Sources: [Vévoda 2018 (cgg.mff.cuni.cz)](https://cgg.mff.cuni.cz/~jaroslav/papers/2018-bayesianlighting/index.htm) ·
[Neural IS Many Lights 2025 (DL)](https://dl.acm.org/doi/10.1145/3721238.3730754) ·
[Estevez & Kulla 2018 (DL)](https://dl.acm.org/doi/10.1145/3233305)

---

## 6. Control variates — broader context

**Image-Space Control Variates — Rousselle, Jarosz, Novák 2016**. Builds a
cheap rendering as a control variate, integrates the residual with MC. Same
mathematical pattern as CV+RRR but at image scale (whole frame, not per-cell).

**Neural Control Variates — Müller et al. 2020**. Neural network as the
control variate's analytic integral. Unbiased thanks to standard CV.

**Imperfect Image-Space Control Variates — TOG 2025**. Recent extension
loosening the "approximation must be tight" constraint of NCV.

**Vector-Valued / Ratio CV 2025**. Generalisations.

**Hooks for VisCache:**
- We are a **point-wise** control variate (per-cell μ); the Rousselle line is
  **frame-wise** (one big proxy). Two regimes of the same CV machine —
  worth a sentence in §11 saying so. CV+RRR is the per-cell, Bernoulli-domain
  version of the same trick.
- Neural CV (Müller 2020) is a useful citation for "yes, learned proxies
  in CV are well-studied; visibility is just a particularly tractable target
  because V ∈ {0,1}".

Sources: [Rousselle 2016 (Dartmouth)](https://cs.dartmouth.edu/~wjarosz/publications/rousselle16image.pdf) ·
[NCV 2020 (DL)](https://dl.acm.org/doi/10.1145/3414685.3417804) ·
[Imperfect ICV 2025 (DL)](https://dl.acm.org/doi/10.1145/3763335)

---

## 7. GPU hash table foundations

**Real-Time Parallel Hashing on the GPU — Alcantara et al. SIGGRAPH 2009**.
First end-to-end GPU cuckoo hash; 35.7 ms to build a 5M-pair table.

**DyCuckoo 2021**, **Compact Parallel Hash Tables on the GPU 2024**.
Modern variants with shared-memory bucket-then-cuckoo hierarchy and
compact storage.

**Hooks for VisCache:**
- We use double-hash open addressing (Binder 2018/2019 style). Cuckoo is the
  alternative approach for guaranteed O(1) worst-case lookup. Not worth
  switching for VisCache — our payload is small (~16 B/cell) and our miss
  rate from collisions is already well-tolerated by EWMA — but worth knowing
  the alternative exists if we ever need worst-case-bounded latency
  (e.g. for a real-time deadline-driven shader).
- The shared-memory bucket-then-cuckoo pattern from Compact CHT 2024 is
  interesting for VisCache *insert*: per-warp shared-memory accumulation
  before atomic write to global. Could reduce DRAM traffic on hot cells.
  Speculative — measure before doing.

Sources: [Real-Time Parallel Hashing 2009 (DL)](https://dl.acm.org/doi/10.1145/1618452.1618500) ·
[Compact Parallel Hash Tables 2024 (Springer)](https://link.springer.com/chapter/10.1007/978-3-031-69766-1_16)

---

## 8. Photon mapping — historical hash precedent

**Hachisuka & Jensen — Parallel Progressive Photon Mapping on GPUs 2010**.
Spatial hash grid with cell size ≈ query radius. Stochastic Hash Grid: store
only a subset to avoid explicit construction phase.

**Knaus & Zwicker — Progressive Photon Mapping: a Probabilistic Approach 2011**.
Real-time PPM via probabilistic radius reduction.

**Hooks for VisCache:**
- The stochastic-store idea (don't store all entries, just a sampled subset)
  could map onto `WSCellPool` slot allocation: instead of overwriting on
  collision, *probabilistically accept/reject* the new sample with a rate
  tied to slot maturity. Mostly of historical interest — ReGIR's M-cap
  schedule is the modern, theoretically grounded answer to the same
  problem.

Sources: [SPPM (Hachisuka)](https://cs.uwaterloo.ca/~thachisu/sppm.pdf) ·
[Parallel PPM on GPUs](http://graphics.ucsd.edu/~henrik/papers/gpuppm_talk.pdf)

---

## 9. Denoising — adjacent, mostly orthogonal

**SVGF — Schied et al. 2017** (`Schied2017_SVGF.pdf`). Reference real-time
denoiser; uses temporal accumulation + variance-guided wavelet filter.

**ReBLUR — NVIDIA NRD**. Production. ~2× SVGF speed at higher quality via
recurrent blurring.

**Denoising-Aware Adaptive Sampling — Firmino et al. 2023**. Allocates
samples where the *denoiser* will benefit most, not just where rendering
variance is highest. Output-aware sampling.

**Hooks for VisCache:**
- We deliberately compare in *pre-tonemap EXR* (per `CLAUDE.md`) and don't
  involve a denoiser. That isolates the algorithm but loses the
  output-aware signal that Firmino 2023 exploits. Not worth changing for
  the paper's controlled comparison, but a denoiser-output-aware variant of
  VisCache (allocate trace budget where denoiser fails) is a clean future
  extension.
- SVGF/ReBLUR's variance estimate has the same shape as our per-cell
  variance — these denoisers are doing locally what VisCache does globally.
  Worth a sentence in §11 noting that VisCache's per-cell variance is a
  *structural* analogue of SVGF's per-pixel variance.

Sources: [SVGF (NVIDIA)](https://research.nvidia.com/publication/2017-07_spatiotemporal-variance-guided-filtering-real-time-reconstruction-path-traced) ·
[Denoising-Aware AS 2023 (DL)](https://dl.acm.org/doi/10.1145/3588432.3591537)

---

## What this survey opens up — actionable summary

Ordered by likely payoff against ladder pain (Sponza ceiling, ct=2 saturation):

1. **EARS-style cost-and-variance RR (cluster 2).** Single biggest fit: our
   vt-saturated regime is exactly where variance-only gating fails. Adding
   a per-cell trace-cost EWMA to drive the RR rate is a small shader change
   with a clear theoretical basis. Reference target: `Rath2022_EARS.pdf`
   §4–5.
2. **SHaRC-style fill-pre-pass (cluster 3).** Cures cold-cache K-RIS bias on
   `WSCellPool` (recorded in `wsrestir_visibility_blind_bias`). Reuse the
   existing PathTracer with a tight ray budget per cell, sequenced before
   shading queries. Reference target: SHaRC integration guide.
3. **Per-cell age + decay (clusters 3, 5).** Replaces our global `ct` with
   per-cell adaptive — directly addresses `project_scene_dependent_ct.md`.
   Reference targets: GI-1.0 §5, Vévoda 2018 §4.3.
4. **Topology/value separation (cluster 1).** Splitting `WSCellPool` slots
   from cascade hash entries lets us resize K independently. Cite fVDB
   IndexGrid as precedent. Already partially in place (single-slot
   reservoir + N=8 pool live in separate buffers keyed by the same
   `WSCellAddress`). Marginal payoff to formalize further.
5. **One-sided exponential level draw (cluster 4, MCPG 2025).** Replace
   symmetric `dl ∈ [−J/2, +J/2]` in `WSReservoirIO.slang:wsLevelJittered`
   with `dl = uint(-log2(1−u))` clamped to `[0, maxOffset]`. Querying
   below target is wasted; coarse fallback is what we want when target
   is cold. Two-line shader change.
6. **Static-grid fallback in parallel to the cascade (cluster 4, MCPG 2025).**
   One extra fixed-world-width hash table sharing the cell buffer.
   Catches state across camera teleport / fast motion when adaptive
   cells go cold simultaneously. Single hash + fingerprint check at
   lookup; same insert path.
7. ~~**MLE α-floor on per-cell EWMA (cluster 4, MCPG 2025).**~~ **DONE
   2026-05-04.** Implemented as `mlAlphaFloorN` (typ 256–1024). Reuses
   the existing race-tolerant 1/8 inline-decay machinery in
   `vhfOverflowDecay` — when the param is set, the trigger threshold
   drops from 0xE000 (≈57K, near-no forgetting) to N*. Steady-state
   per-sample weight ≈ 1/N*, the discrete analogue of MCPG's
   `α = max(1/N, MIN_ALPHA)` with `MIN_ALPHA = 1/N*`. Wired through
   `VisCache.h` Params + GPUParams, `VisCache.cpp` props/dict/GUI/binding,
   `PathTracer.cpp` per-field cbuffer site, `VisCache.slang`
   `gMLAlphaFloorN` cbuffer + `vhfOverflowDecay` trigger. Paper update
   in §6 (`viscachepaper/sections/06-eviction-and-temporal-decay.md`).

## Open questions raised by the survey

- **Variance-aware path guiding (Rath 2020) vs. our variance-aware
  CV+RRR — are they the same operator on different state?** Both replace
  "sample proportional to f" with "sample proportional to a variance-weighted
  proxy". Worth a half-page comparison in §11.
- **Why does EARS not converge to "always trace" on grazing surfaces?**
  Their cost model includes per-cell variance + per-cell cost. If grazing
  surfaces have both high variance *and* high cost, the optimal RR factor
  is non-trivial — exactly our Sponza regime. Need to read EARS §5.2
  carefully and model our regime against it.
- **Do SHaRC's collision statistics match ours?** Their tuning advice is
  "buffer size vs. collision rate" — no smarter scheme. Our double-hash +
  fingerprint is more elaborate. Is the difference measurable on Bistro?
  One A/B run on the existing harness would tell us, but it's not on the
  ladder. Park as a side-investigation.

---

## Citation map (delta from REFERENCE_SUMMARIES.md graph)

```
Adaptive resolution lineage:
  Stotko 2025 (TSDF, variance) ←→ §7 write-depth gate
  fVDB 2024 (topology/value split) → WSCellPool architecture idea
  Walker WACV 2025 (entries-where-error) ←→ same principle, neural setting

RR/splitting theory:
  Vorba 2016 ADRRS ─→ Rath 2022 EARS ─→ Grittmann 2024 MARS
                                  ↘─→ NRRS 2025 (neural)
                              ↘─→ VisCache CV+RRR (cost dimension MISSING)

Online-learned proxy lineage:
  Müller 2017 PG ─┬─→ Dittebrandt 2023 MCMM ─→ Real-Time MC PG 2025 (WS hash)
                  └─→ Rath 2020 var-aware PG ─→ EARS 2022
  Vévoda 2018 Bayesian DI ─→ Neural IS Many Lights 2025
                          ↘─→ VisCache CV+RRR (visibility, not lights)

World-space caches:
  Majercik 2019 DDGI (probes) ─→ Boissé 2022 GI-1.0 (hash, two-level)
                              ─→ NRC 2021 (neural) ─→ SHaRC 2024 (hash)
                              ─→ ReGIR 2021 (per-cell light reservoirs)
                              ─→ VisCache (per-cell visibility)

Control variates lineage:
  Rousselle 2016 (image-space) ─→ Müller 2020 NCV (neural)
  Szirmay-Kalos 2005 (CV+RRR) ─→ VisCache (point-wise, Bernoulli)
```

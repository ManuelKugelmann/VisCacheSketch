# Ladder Plan — Steps 19–50+ (Forward-Looking)

This document is the **forward** half of the ladder paperwork; the **backward** half — what was decided and why for steps 00–18 — lives in [LADDERLOG.md](LADDERLOG.md). The Dev Log ([devlog/DEVLOG.md](devlog/DEVLOG.md)) keeps cross-cutting findings (e.g. RTXDI parity story) outside the per-step ladder.

The ladder progresses in stages, each adding one axis of complexity over the previous stage's canonical config. Every stage's first step is a reference run that ties cost+quality back to the new reference baseline; every stage's last step picks a single canonical config that the next stage opens with.

## Where VisCache plugs in

VisCache is a single substrate (flat multilevel hash, CV+RRR estimator, μ output) that touches the rendering algorithm at four distinct points. Each point is opened in its own stage so the gain is attributable rather than tangled.

| stage | rendering algorithm | VisCache use | reference baseline |
|-------|---------------------|--------------|--------------------|
| A     | n/a (references)    | none         | self (GT)          |
| B     | PT DI single-bounce | shadow-ray RR (V cache, single level)             | `vanilla` x{1..4096}        |
| C     | PT DI single-bounce | shadow-ray RR (V cache, multilevel cascade)       | stage B canonical            |
| D     | ReSTIR DI           | μ-weighted light selection + amortized V          | `rtxdi`, `restir_2d`, `restir_3d` |
| E     | PT multibounce      | V cache at all bounces + per-bounce RR            | `vanilla_b{1,4,8}`           |
| F     | ReSTIR PT           | reconnection-shift V revalidation (paper §12) + μ-NEE at indirect | `restirpt_b{1,4,8}` |
| G     | BDPT (open)         | sensor-side reconnection (MK2006 §7), eye-cache   | TBD                          |

## Stage layout

| range  | stage | rendering algorithm                                | status                      |
|--------|-------|----------------------------------------------------|-----------------------------|
| 00     | A     | references (vanilla / RTXDI / restirpt / restir_2d/3d) | done — keep as-is       |
| 01–10  | B     | single-level VisCache on PT DI                     | done                        |
| 11–18  | C.1   | multilevel VisCache on PT DI                       | done (post-alignment)       |
| 19–20  | C.2   | multilevel PT DI — final validation + canonical    | **next**                    |
| 21–30  | D     | multilevel + WS-ReSTIR DI                          | parity achieved off-ladder; ladder structure pending |
| 31–40  | E     | multilevel + PT multibounce                        | new                         |
| 41–50  | F     | multilevel + ReSTIR PT multibounce                 | new                         |
| 51+    | G     | BDPT (open)                                         | open                        |

## Reuse from existing data

Step 00 already runs vanilla x{1..16} + x4096 GT, vanilla_b{1,4,8} x{1..16} + x4096 GT, restirpt_b{1,4,8} x{1,4}, rtxdi x{1,4}, and restir_2d/3d x{1,4} — across `ALL_SCENES` ∪ `MULTI_LEVEL_SCENES`. Every later stage reads its references straight from `captures/ladder/00/<scene>/`; no rerun needed unless the metric changes. **Re-emit only the postprocess/CSVs** when the metric changes, never the EXRs.

The post-merge-order multilevel sweep at steps 19–25 lives in `runtime/captures/ladder/archive_post_v2/`. Steps 19/20 below are clean re-curations of that data under the current canonical metric (Reinhard-tonemapped OkLab vs x4096 GT) — no re-render expected.

The WS-ReSTIR parity matrix from the *Final canonical config* section of DEVLOG.md is the natural starting point for Stage D step 21; its EXRs live under `runtime/captures/wsrestir/` (not the ladder root). Stage D step 21 imports them by reference rather than re-rendering.

---

# Stage C.2 — multilevel PT DI: validation + canonical (steps 19–20)

## Step 19 — Final-validation: multilevel-PT-DI canonical on full scene matrix

**Hypothesis.** The post-step-18 carry `pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm010` (single-carry recommendation in DEVLOG §"Practical conclusion") holds across the full 7-scene matrix at x{1,4,16} under the current absolute-err-vs-GT metric.

**Axes.** None — single config, validation only.

**Scenes.** `MULTI_LEVEL_SCENES` (32PointLights + Bistro × 2 + Sponza) + the 4 Cornell variants.

**SPPs.** x1, x4, x16. (x4096 GTs already present in step 00.)

**Reuse.** Existing `archive_post_v2/18/` EXRs for 5 scenes. Re-render only Cornell_1AL + Cornell_1PL + Cornell_3AL if those configs weren't in the archive sweep.

**Pass criterion.** `error_delta_blob_pct ≤ 10` on every scene × SPP — no visible cache artifacts.

**Carry.** `viscache_canonical_pt_di` (full config dict, written to `picks.json`).

**Compute.** ~10 min (5 cached scenes × postprocess only + 3 fresh Cornell renders × ~30 s each at x{1,4,16}).

## Step 20 — Cumulative cost-quality plate (paper-ready figure)

**Goal.** A single 5-row × 4-col plate of `error_pct` and `rays_traced_pct` vs SPP for each scene, comparing `vanilla` / `viscache_canonical_pt_di`. This is the paper §11 figure for "shadow-ray reduction with bounded error".

**Reuse.** Step 19 + step 00 EXRs.

**Carry.** None — purely figure generation.

**Compute.** Plot generation only.

---

# Stage D — multilevel + WS-ReSTIR DI (steps 21–30)

The WS-ReSTIR DI work in `viscachepaper/sections/09-restir-integration.md` reached functional + qualitative parity with RTXDI off-ladder — the matrix in DEVLOG §"RTXDI Baseline — Final Result" is the seed canonical, not a result to be re-derived. This stage formalises that result as ladder steps so each axis has its own narrowing entry, and so VisCache (μ-weighted light selection) can be enabled on top with a clean A/B.

## Step 21 — Reference + WS-ReSTIR canonical validation

**Hypothesis.** The DEVLOG canonical (`N=128, K_pre=32, K_pool=16, MCap=5, PdfMipmap pre / LightBVH main, Conv B reader-eval, bayerN=4`) reproduces the parity matrix on the full 7-scene set.

**Reuse.** Existing `runtime/captures/wsrestir/` EXRs (if intact). Otherwise one re-render under the canonical config — ~6 min total.

**Carry.** `wsrestir_canonical` (config dict).

## Step 22 — Pool capacity (`wsCellPoolCapacity`)

**Axis.** {64K, 128K (default), 256K, 512K, 1M} slots.

**Hypothesis.** 128K = sweet spot; 64K thrashes on Bistro, ≥256K shows diminishing returns. Tests the substrate-density sensitivity claim.

**Scenes.** Sponza, BistroExt, BistroInt (Cornell_3AL as architecture-trail probe).

**Reuse.** Step 00 references; one fresh sweep.

## Step 23 — K_pre × K_pool

**Axes.** K_pre {16, 32, 64} × K_pool {8, 16, 24}.

**Hypothesis.** K_pool=16 is the lower-variance corner; K_pool=24 over-weights the pool's shading-agnostic distribution (DEVLOG-confirmed). K_pre=32 the sweet spot; K_pre=64 quality cost ~0.1pp.

## Step 24 — Pool addressing (3D cell vs 2D tile vs footprint-derived)

**Axes.** `wsPoolAddrMode` ∈ {0=3D cell, 1=2D tile} × `wsCellPoolFootprintPx` ∈ {0=fixed-level, 8², 16², 32²}.

**Hypothesis.** Substrate equivalence — 2D-tile and footprint-derived 3D-cell within sampling noise on every scene at matched density.

**Pass criterion.** `|restir_2d_err − restir_3d_err| ≤ 0.05pp` on all 7 scenes — proof of paper §3.0 substrate-equivalence claim.

## Step 25 — μ-aware target function (`wsVisInPHat`)

**Axes.** {0=blind, 1=cache-amortized, 2=explicit-V always}.

**Hypothesis.** RTXDI-faithful blind p̂ + V=0 invalidation wins — putting V in K-RIS p̂ adds μ_min-floor bias on emissive scenes (DEVLOG-confirmed).

## Step 26 — VisCache cache-weighted light selection on top

**Axis.** `wsLightSoftness` ∈ {0=uniform-no-cache, 0.25, 0.5, 1.0=full-trust}.

**Hypothesis.** Full-trust steers samples toward visible lights without breaking unbiasedness (μ enters the proposal pdf, not the estimator). On Bistro/Sponza this should win net err while leaving rays unchanged.

**Depends on.** Step 21 canonical + VisCache enabled (master gate `enableWSReservoirs=true && enableVisCacheLightSelection=true`).

## Step 27 — Pre-pass V-amortization via cache

**Axis.** Cache-V at K-RIS pre-pass: off (current) / on.

**Hypothesis.** μ entering p̂ at pre-pass + V at main-pass keeps unbiasedness + reduces eval-cost gap to RTXDI's lean compute presample (DEVLOG Task #29 / Task #32). Eval-cost ~3–4× → ~1.5×.

**Depends on.** Lean dedicated compute pre-pass (Task #29) wired.

## Step 28 — Bayer N × subframe stratification

**Axes.** bayerN ∈ {1, 2, 4, 8}.

**Hypothesis.** bayerN=4 = sweet spot; matches RTXDI's 16K active-pixel × K=8 ≈ 131K presamples. bayerN=8 starves the pool per-subframe.

## Step 29 — wsMCap (temporal cap)

**Axis.** wsMCap ∈ {3, 5 (default), 10, 20 (RTXDI)}.

**Hypothesis.** wsMCap=5 wins on multi-light. 20 uniformly +0.1–0.3pp on multi-light scenes (DEVLOG-confirmed). 3 over-eager temporal-flush.

## Step 30 — WS-ReSTIR DI canonical config + cumulative plate

**Goal.** Lock the carry for stages E + F. Paper-ready 7-scene × {x1, x4} grid: vanilla / rtxdi / restir_2d / restir_3d / **wsrestir+viscache** error and rays.

**Carry.** `wsrestir_canonical_v1` (full config dict including VisCache enables and `wsLightSoftness`).

---

# Stage E — multilevel + PathTracer multibounce (steps 31–40)

PT with `maxBounces > 0`. Cache used for visibility queries at every bounce. Reference is `vanilla_b{1,4,8}` from step 00 — already rendered.

## Step 31 — Bounce-depth scan: vanilla vs viscache_b{1,4,8}

**Axis.** `maxBounces` ∈ {1, 2, 4, 8}.

**Reference.** `vanilla_b{N}` from step 00.

**Hypothesis.** Cache wins more as bounces increase (every secondary bounce is a fresh shadow ray).

**Carry.** Per-bounce config baseline (no per-bounce-depth tuning yet).

## Step 32 — Cache use at indirect-only vs all-bounces

**Axis.** {primary-only, indirect-only, all-bounces}.

**Hypothesis.** All-bounces wins; indirect-only is the cheap-but-leaky compromise; primary-only is what stages B + C already validated.

## Step 33 — Per-bounce ct/vt tuning

**Axes.** `bootThreshold` per-level ramp shape (uniform vs coarse-HIGH-fine-LOW already exposed via `bootThresholdFine`) × `varThreshold` ∈ {0.01, 0.03, 0.05}.

**Hypothesis.** Deeper bounces have noisier μ (more stochastic noise upstream) → tighter vt or higher ct at finer levels helps. Tests `bootThresholdFine` knob.

## Step 34 — Reconnection-shift V queries (pos × pos addressing)

**Axis.** `enableVisCacheDirDistAddr` off vs on for indirect bounces; mixed pos×pos for primary, pos×dir_dist for indirect.

**Hypothesis.** Reconnection-shift queries are pos→pos symmetric (paper §12) — pos×pos addressing avoids the asymmetry penalty of dir-dist for the GI revalidation case.

## Step 35 — Throughput-weighted adaptive pMin (paper §8.1.1)

**Axis.** `enableVisCacheAdaptivePMin` × `fireflyBudget` ∈ {0.01, 0.05, 0.10}.

**Hypothesis.** High-throughput paths warrant more rays (fireflies cost more there). The cache's confidence-weighted pMin already exists (`enableVisCacheAdaptivePMin`); this step validates it specifically at multi-bounce where throughput variance is wide.

## Step 36 — Hierarchical consistency at indirect bounces

**Axis.** `enableHierarchicalConsistency` off vs on × `hierarchicalMuTolerance` ∈ {0.05, 0.10, 0.20}.

**Hypothesis.** HC's value rises with bounce count (each indirect query has more chances to hit a coarse-level over-trust pothole).

## Step 37 — μ-driven NEE selection at indirect bounces

**Axis.** `enableVisCacheLightSelection` off vs on at indirect bounces.

**Hypothesis.** Same gain as in stage D step 26, but applied at every NEE call along the path. Quality should compound.

## Step 38 — Cumulative cost reduction across bounces

**Goal.** Per-bounce `rays_traced_pct` panel — visualises where the cache pays off most.

**Reuse.** Steps 31 + 37 EXRs.

## Step 39 — Quality plate: cache vs vanilla_b{N} at every depth

**Goal.** Paper §11 figure for multibounce.

## Step 40 — PT+VisCache canonical config

**Carry.** `viscache_canonical_pt_mb` (full dict with per-bounce policy).

---

# Stage F — multilevel + ReSTIR PT multibounce (steps 41–50)

ReSTIR PT (DQLin port at `Source/RenderPasses/ReSTIRPTPass/`) with VisCache plugged into reconnection-shift V revalidation (paper §12) and into NEE at indirect bounces.

## Step 41 — ReSTIR PT bounce sweep — viscache vs restirpt_b{N}

**Axis.** `maxBounces` ∈ {1, 2, 4, 8}.

**Reference.** `restirpt_b{N}` from step 00.

**Hypothesis.** Cache helps the reconnection-shift revalidation step specifically; gain scales with shift count per pixel.

## Step 42 — Cache-amortized reconnection-shift V (paper §12)

**Axis.** Reconnection-shift V revalidation — {full-trace (current), cache-only-no-trace (biased), CV+RRR (cache+stochastic correction)}.

**Hypothesis.** CV+RRR matches full-trace error but at lower ray cost — the headline §12 claim. **Bias-bounded** by the variance-driven RR.

**Pass criterion.** `|err_CV+RRR − err_full-trace| ≤ 0.1pp` AND `rays_CV+RRR < rays_full-trace × 0.7` on Bistro/Sponza.

## Step 43 — μ-aware light selection in ReSTIR PT NEE

**Axis.** `enableVisCacheLightSelection` off vs on at every NEE call inside ReSTIR PT.

**Hypothesis.** Same gain as stage D step 26 / stage E step 37.

## Step 44 — Spatial reuse vs cache V — interaction sanity

**Axes.** Spatial reuse {off, k=4, k=8} × cache V {off, on}.

**Hypothesis.** Independent — spatial reuse and cache V act on orthogonal axes; combined gain ≈ product.

## Step 45 — Per-bounce cache use in ReSTIR PT

**Axis.** Bounce ranges {primary-only, primary+indirect, all-bounces}.

## Step 46 — Cache-suffix reconnection (Lin 2026 dup-maps replacement)

**Axis.** Cache-suffix shift {off, on}.

**Hypothesis.** Per-cell partial-path generators (memory entry `project_partial_path_cell.md`) replace Lin 2026's dup-maps for the cache-side; the cell hash already provides the indexing.

## Step 47 — Quality vs DQLin restirpt_b{N}

## Step 48 — Cost reduction (rays_traced) on multi-bounce ReSTIR

## Step 49 — Combined paper-ready plate (DI + multibounce + ReSTIRPT, all-in-one)

## Step 50 — ReSTIRPT+VisCache canonical config

**Carry.** `viscache_canonical_restirpt` (full dict).

---

# Stage G — BDPT (open, steps 51+)

The 2006 thesis's bidirectional / backtracing chapter sketched sensor-side reconnections inspired by Metropolis mutations + photon-mapping imperfect reconnections. Lin 2026 ReSTIR BDPT is the modern published direction.

Open questions (no committed steps yet):
- Eye-cache addressing — pos+normal at sensor vertex, or pos+normal+wo?
- Sensor-side reconnection unbiasedness under MIS — same argument as paper §12 V-revalidation, applied at the eye end.
- Bidirectional reservoir merge inside per-pixel reservoir, or as a separate eye-side cell pool?

Steps 51+ deferred until stage F lands and the BDPT Falcor pass exists.

---

# Run order recommendation

Sequential dependencies that block:
- 19 → 20 → 21 (need stage C canonical to start stage D)
- 21 → 22..29 (parallel within D once 21's canonical is set)
- 30 → 31..39 (parallel within E once 30's canonical is set)
- 40 → 41..49 (parallel within F once 40's canonical is set)

Suggested wall-clock budget:
- Stage C.2 (19–20): ~30 min total (mostly postprocess)
- Stage D (21–30): ~6 h compute (mostly fresh sweeps)
- Stage E (31–40): ~12 h compute (multibounce is expensive — x{1,4,16} × b{1,2,4,8} × scenes)
- Stage F (41–50): ~24 h compute (ReSTIR PT is the most expensive renderer)

Estimates are upper bounds at 512² with current per-scene Mogwai isolation.

---

# Cross-cutting items (not ladder steps)

- **Lean compute pre-pass** (Task #29) — needed before step 27 to be a fair RTXDI eval-cost comparison.
- **Per-pass `VisCacheParams`** (Task #32) — needed before step 27 (different bayerN per pass).
- **Bayer-aligned cell-pool slot indexing** (Task #33) — close-out of WS-ReSTIR DI work; may slot into step 28 or step 22.
- **Cornell_3AL_x4 architectural trail** — confirmed structural in DEVLOG; not on the ladder, no closure expected within the per-cell pool architecture.

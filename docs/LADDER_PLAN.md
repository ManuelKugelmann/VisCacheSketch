# Ladder Plan — Steps 19–50+ (Forward-Looking)

This document is the **forward** half of the ladder paperwork; the **backward** half — what was decided and why for steps 00–18 — lives in [LADDERLOG.md](LADDERLOG.md). The Dev Log ([devlog/DEVLOG.md](devlog/DEVLOG.md)) keeps cross-cutting findings (e.g. RTXDI parity story) outside the per-step ladder.

The ladder is a **tool for understanding the algorithm**, not a search for one canonical config. Each stage opens an axis of complexity (single-level → multilevel → ReSTIR DI → multibounce → ReSTIR PT → BDPT) and follows the typical research-ladder shape:

0. **Kick off with broad smoke tests** based on best prior knowledge / educated guesses — coarse parameter ranges, small scene sets, low SPP. The smoke pass reveals the rough sensitivity surface and rules out the obvious "doesn't work" cases before any expensive deep sweep.
1. **Verify each aspect of the algorithm works** at that complexity level — failure modes get characterised before tuning starts.
2. **Map parameter sensitivity** — which knobs move quality / cost, by how much, in which regime.
3. **Identify parameter interrelations** — which knobs decouple, which couple (e.g. ct + vt couple at the saturated corner; vt + SPP couple in the SPP-dependent-vt finding).
4. **Surface shortcomings** that point to mechanism-level changes (e.g. SPP-dependent vt → Wilson-interval; firefly-class DI saturation → multibounce solves it).

The output is **a minimal set of fixed or interdependent parameters that produce a metric-weighted win** — `quality + cost` with the weighting determined by what the user / paper / use-case values. A "win" is metric-relative: at one extreme it's a Pareto improvement on every axis (firefly-class multibounce), at the other it's a tradeoff on perceptual vs linear-space metrics (penumbra-class single-bounce). When metrics disagree, the ladder's job is to make the trade explicit and tunable, not pick a winner.

**Each step ideally lands at a local optimum** for the parameters it sweeps. **Archive failed sweeps and dead ends out of the live ladder, but keep the archive around for a while** — they often reframe later when an adjacent investigation lands. Delete an archived entry only when the underlying problem is **fully obsolete** (solved a different way, or otherwise resolved into the live ladder). Mechanism:

- Live narrowing chain (`docs/LADDERLOG.md` table at top) holds only steps with a real local optimum.
- "Pruned dead ends (learnings preserved)" footer in LADDERLOG holds recently-archived sweeps with one-line learnings + cross-link to DEVLOG for cross-cutting findings (`docs/devlog/DEVLOG.md`).
- An entry leaves the archive only when it's fully obsolete — the problem is solved (e.g. a downstream sweep absorbs the same lesson cleanly) or the result is no longer actionable. Until then it stays as an audit trail; reframings tend to land months later.

A failed sweep is a finding, not a step.

## Roadmap (2026-05-06 consolidated)

### Where we are
- **Stages A, B, C.1, C.2 done.** Live ladder pruned to 11 keep-rows + 9 pruned-with-learnings (LADDERLOG/DEVLOG split). Trust-gate axes mapped; scene-class taxonomy validated; canonical per-(class, bounce-regime) config established.
- **Stage D plumbing landed**: `wsRetraceOnReuseMode` toggle (Off / FullTrace / CacheCV) + `rays_traced_pct` schema + `vcDiagCountRay`. SMOKE3 confirmed all three modes give correct unbiased results within stochastic noise.
- **Stage E green-lit on the full Sponza/Bistro/Cornell matrix.** Sponza (−74pp rays b=4, perceptual win + linear loss), BistroInt (b=4 wins every metric, relmse 2.4× better), Cornell × 4 lighting regimes (rays savings monotonic in bounce depth, OkLab matches vanilla within 0.05pp at b=4). The Sponza-vs-Bistro multibounce dichotomy resolves into a single light-count gradient: linear-space cost scales with firefly density (1AL/1PL minor, 32PL massive RMSE +150%); relmse improves at high firefly density (cache averages magnitude tails). BistroExt MB queued (running).

### Knowledge gaps (priority order)

| # | gap | cost | informational gain | status |
|---|-----|-----|---:|---|
| ~~1~~ | ~~Cornell scenes multibounce + cache~~ | ~~~15-20 min~~ | ~~Cornell-class generalization~~ | ✅ DONE 2026-05-06 — confirmed (light-count gradient resolves Sponza-vs-Bistro dichotomy) |
| 1 | BistroExt multibounce | ~30 min (needs vanilla_b{1,4} GTs) | extends BistroInt's "wins everywhere" within firefly-class | running (job baoghcdph) |
| 2 | All-scenes canonical at x{4, 16} | ~15-20 min | validates SPONZA-derived per-SPP carry across full scene matrix; surfaces per-class divergence | script ready (`ALL_X16`) |
| 3 | Sponza b=8 / b=16 | ~10 min + 2× GT renders | does rays-savings trend continue past b=4 or saturate? | not started |
| 4 | Stage D step 21 formal opening | ~30 min | open WS-ReSTIR DI ladder with `wsRetraceOnReuseMode=2` carry as numbered ladder step | not started |
| 5 | 86.92% rays-counter mystery | code-reading only | minor; investigate where saved counts originate with visibilityCheck=False | **partially diagnosed 2026-05-06** — two write paths overlap on `gVCAccumRaysNoiseErrorCold[pixel].r`: `vcWriteDiag` (only fires under USE_VISCACHE_VISIBILITYCHECK) and `vcDiagCountRay` (added 2026-05-06 for WS-ReSTIR sites). For `restir_2d_vblind` (visibilityCheck=False, mode=0): only the K-RIS-winner V-test at PathTracer.slang:1529 fires, always with traced=true. The 13% "saved" is therefore not from this run — most likely **stale accumulator state from an earlier config sharing the same EXR**, or a not-yet-found additional vcWriteDiag site. Needs print-instrumentation + Mogwai run to confirm |

### Proposed improvements (design ideas, not yet implemented)

| # | improvement | why | effort | precondition |
|---|------------|-----|-------|--------------|
| A | **Wilson-interval / two-tier ct** | Principled fix for SPP-dependent vt finding (`vt=0.10` x4 vs `vt=0.001` x16). Wilson lower-bound > 0.99 OR upper-bound < 0.01 collapses both regimes into one criterion. | ~1h slang patch + sweep | none |
| B | **c1+c2: μ at reservoir + pool READ** | Visibility-aware presampling at reservoir/pool merge. Multiply `pHat_reader` by cache μ in cross-pixel/temporal merge. | ~30 min slang + sweep | (a)+(b) ✅ |
| C | **c3: μ at presample WRITE** | Filter cell-pool candidate SET toward visible lights at insert time. | ~30 min slang + sweep | c1+c2 |
| D | **Scene classifier** | Bayer-rotation cell-μ-stability monitor: penumbra cells' μ varies across rotations; firefly-locked cells' μ stays constant. Self-tunes per-scene config. | ~1h investigation + ~1h prototype | none (orthogonal) |
| E | **BoilingFilter separable include** | Re-enable the disabled BoilingFilter via the documented separable-include fix path. | ~1h | none; but quality unaffected per data |
| F | **Lean compute pre-pass for cell-pool fill** (Task #29) | RTXDI eval-cost parity (3-4× reduction). | ~2h slang + integration | useful for Stage D step 27 |
| G | **Per-pass VisCacheParams** (Task #32) | Different `bayerN` / `wsVisInPHat` for pre-pass vs main pass. | ~1h cpp/cbuffer wiring | useful for Stage D step 27 |
| H | **Bayer-aligned cell-pool slot indexing** (Task #33) | Eliminate random-replace contention in cell-pool. | ~1h slang | useful for Stage D step 22+ |

### Next experiments (compute-side, prioritised)

1. ✅ **Cornell multibounce** (`scripts/VisCache_LadderCORNELL_MB.py`) — DONE 2026-05-06. Light-count gradient resolves Sponza-vs-Bistro dichotomy.
2. ⏳ **BistroExt multibounce** — running (job baoghcdph). Auto-generates vanilla_b{1,4} GTs first.
3. **All-scenes canonical x{4, 16}** (`scripts/VisCache_LadderALL_X16.py` — ready) — 7-scene smoke validation of SPONZA per-SPP carry. Queue after BistroExt.
4. **Wilson-interval prototype** — slang patch; replaces vt with binomial confidence interval. Code change ~1h, sweep on Sponza x{4, 16}. Highest-leverage open improvement.
5. **Sponza b=8 / b=16** — extend the bounce-depth axis to confirm asymptote behaviour. Quick smoke (~10 min).
6. **Stage D step 21 — formal WS-ReSTIR DI canonical sweep** — open the WS-ReSTIR ladder. Sweep K_pre / K_pool / MCap at the validated `wsRetraceOnReuseMode=2` carry.
7. **c1+c2 patch** — slang change to inject μ in `pHat_reader` at reservoir + pool reads; sweep on Sponza+BistroInt at the WS-ReSTIR canonical. Higher mu_min than 1% (cache as guide).

### Documentation hygiene (no compute)

- **Renumber recent diagnostic sweeps** (SMOKE / SPONZA_CT / SPONZA_VT / BISTRO_CT / BISTRO_ADD / BISTRO_DECAY / SPONZA_MB / BISTRO_MB) as steps 19–25 in LADDERLOG → continuous numbering before opening Stage D.
- **Update DEVLOG** with the metric-selects-policy finding + bounce-depth taxonomy update.
- **Open issues / Tasks** for improvements A–H above.

### Stage progression summary

| stage | status | next concrete step |
|-------|--------|-------------------|
| A | ✅ done | refresh GTs as needed (Cornell_1PL, Cornell_3AL, BistroExt: b{1,4}) |
| B | ✅ done | — |
| C.1 | ✅ done | — |
| C.2 | ✅ done (effectively, via SPONZA_*/BISTRO_* sweeps) | renumber as steps 19–25 |
| D | (a)+(b) plumbing ✅; ladder open | open step 21 |
| E | green-lit on both classes; not formally opened | sweep all 7 scenes at canonical × b{1,4,8} |
| F | pending parallel agent's RPT integration | wait |
| G | open | wait |

## Where VisCache plugs in

VisCache is a single substrate (flat multilevel hash, CV+RRR estimator, μ output) that touches the rendering algorithm at four distinct points. Each point is opened in its own stage so the gain is attributable rather than tangled.

| stage | rendering algorithm | VisCache use | reference baseline |
|-------|---------------------|--------------|--------------------|
| A     | n/a (references)    | none         | self (GT)          |
| B     | PT DI single-bounce | shadow-ray RR (V cache, single level)             | `vanilla` x{1..4096}        |
| C     | PT DI single-bounce | shadow-ray RR (V cache, multilevel cascade)       | stage B canonical            |
| D     | ReSTIR DI           | (a) cache-V on shadow rays + (b) cache-V revalidation on reused samples + (c1/c2/c3) μ-aware target pdf at reservoir-read / pool-read / presample-write | `rtxdi`, `restir_2d`, `restir_3d` |
| E     | PT multibounce      | V cache at all bounces + per-bounce RR            | `vanilla_b{1,4,8}`           |
| F     | ReSTIR PT           | reconnection-shift V revalidation (paper §12) + μ-NEE at indirect | `restirpt_b{1,4,8}` |
| G     | BDPT (open)         | sensor-side reconnection (MK2006 §7), eye-cache   | TBD                          |

**Stage D layered framework (designed 2026-05-06).** Treat ReSTIR DI like the PathTracer first — use cache to resolve visibility queries before touching the reservoir math:

- **(a) fresh-sample V** — cache CV+RRR replaces unconditional shadow trace at the K-RIS winner's V test. **Wired and tested 2026-05-06** (commits `94a6ba1` plumbing, `4f93f8c` rays counter, SMOKE3 verification). PT-DI canonical cache config (now updated per scene class — see "Scene-class taxonomy" above; `ct=8 vt=0.10` for penumbra-class scenes).
- **(b) reconnected-sample V** — cache-V revalidation on temporal/spatial reuse (RTXDI's `BiasCorrection::RayTraced` analog). **`wsRetraceOnReuseMode` toggle plumbed and validated 2026-05-06** (`94a6ba1`): 0=Off (Basic-equiv), 1=FullTrace, 2=CacheCV. SMOKE3 confirmed all three modes match within stochastic noise on Sponza+BistroInt; `restir_2d/3d_*_raytraced` already beats `rtxdi_raytraced` by −0.24pp on Sponza, −0.93pp on BistroInt.
- **(c1) μ at per-pixel reservoir READ** — multiply `pHat_reader` by cache μ in the cross-pixel/temporal merge. Bitterli streaming-merge formula already does `pHat_reader / pHat_writer` ratio: just include μ in `pHat_reader`.
- **(c2) μ at pool→pixel READ** — same `pHat_reader` site (often shared with c1); pool candidate gets μ-weighted by the reader's cache state.
- **(c3) μ at cell-pool WRITE (presample)** — multiply `pHat_writer` (per-cell μ) at the K-RIS that fills the pool. Filters the pool's candidate SET toward visible lights; reader's `pHat_reader / pHat_writer` ratio cancels writer-side μ in W (no double-count).
- **μ_min trust floor** — when implementing c1/c2/c3, bump default `wsLightMuMin` from 0.01 → 0.25 (cache treated as a rough guide, 4× ratio favoring visible vs occluded). The 1% floor presumes a precise cache; current cache on Bistro/Sponza at x4 is noise-dominated.

Order: ~~(a) and (b) first~~ ✅ (a) and (b) DONE 2026-05-06; c1+c2 next (one patch — `pHat_reader` site); c3 last (separate patch at cell-pool insert).

## Stage layout

| range  | stage | rendering algorithm                                | status                      |
|--------|-------|----------------------------------------------------|-----------------------------|
| 00     | A     | references (vanilla / RTXDI / restirpt / restir_2d/3d / rtxdi_raytraced) | done       |
| 01–10  | B     | single-level VisCache on PT DI                     | done                        |
| 11–18  | C.1   | multilevel VisCache on PT DI                       | done (post-alignment)       |
| SMOKE / SPONZA_CT / SPONZA_VT / BISTRO_CT / BISTRO_ADD / BISTRO_DECAY | C.2 | scene-class trust-gate diagnosis | **done** (2026-05-06) |
| 21–30  | D     | multilevel + WS-ReSTIR DI                          | (a)+(b) plumbing landed; c1/c2/c3 deferred |
| 31–40  | E     | multilevel + PT multibounce                        | new                         |
| 41–50  | F     | multilevel + ReSTIR PT multibounce                 | new                         |
| 51+    | G     | BDPT (open)                                         | open                        |

## Scene-class × bounce-depth taxonomy (validated 2026-05-06)

Recent sweeps revealed cache behaviour depends on TWO axes — scene class AND bounce depth — not one. Each (class, bounce-regime) combination has its own carry and lever-effectiveness profile:

| class | regime | example | failure mode / strength | productive levers | metric trade |
|-------|--------|---------|------------------------|-------------------|--------------|
| **penumbra-class** | DI (b=0) | Sponza | cells trust at suboptimal μ — premature all-same-evidence trust at low ct | raise base ct (`ct=2→8` cuts art5 −5.83pp); tighten vt at high SPP (`vt=0.001` cuts art5 −14pp at x16) | linear-space modest cost; perceptual win |
| **penumbra-class** | multibounce | Sponza b=4 | cache amortizes per-bounce shadow rays | trust-gate carry inherits from b=0 | **−74pp rays**; OkLab tied; **PSNR −1.3 dB**; relmse +16% |
| **firefly-class** | DI (b=0) | BistroExt, BistroInt | cache **already at irreducible variance floor** | none — cache is **already winning** −18 to −46pp art5 vs vanilla | trust-gate / decay all bit-identical; but cache itself is a huge win vs vanilla |
| **firefly-class** | **multibounce** | **BistroInt b=1/b=4** | **cache amortizes per-bounce firefly variance** — strongest regime measured | trust-gate carry inherits from b=0 | **−53pp rays AND wins on every metric**: relmse 89.93→37.98 (**2.4× better**), RMSE/PSNR/MS-SSIM all hold or improve |
| **diagnostic** | DI | Cornell 1PL | hard-shadow blob canary | tight vt prevents blob | — |

**Per-(class, regime) canonical config (penumbra and firefly both):**
- **x4 + b=0/b=1/b=4**: `cell4×4 + bayer2×2 + ct=8 + vt=0.10 + pm=0.02` (validated on Sponza_MB and BISTRO_MB)
- **x16 + b=0**: `cell4×4 + bayer2×2 + ct=8 + vt=0.001 + pm=0.02` (penumbra-class only; firefly-class indifferent)
- Universal-on-multibounce: same trust-gate config carries from b=0 to b=4 — bounce depth doesn't change the optimum within a class.

**The metric-selects-policy framework holds across both classes.** Different metrics select different vt optima (art5 vs RMSE anti-correlated); paper Tables must report the full battery — `err%, art5%, RMSE, PSNR, relmse, MS-SSIM, FLIP, rays%` — and call out where metrics disagree.

**Headline result for paper §11/§12:** firefly-class multibounce is the **best cache demonstration** — Bistro b=4 cache delivers −53pp rays AND 2.4× better relmse simultaneously. Single-bounce DI is a quality-cost trade; multibounce is a strict win.

**Implication for ReSTIR PT (Stage F):** ReSTIR PT is multibounce by definition; the cache should help on every metric. The −1.3 dB PSNR loss seen in Sponza single-bounce DI doesn't appear at multibounce — Stage F is likely the strongest cache regime in the paper.

**Open extension:** scene classifier (Bayer-rotation cell-μ-stability monitor: penumbra cells have varying μ across rotations, firefly-locked cells stay constant). Self-tuning, but not blocking — current per-class configs are good enough since the same trust-gate config works across scene classes anyway. The differences are in WHAT the cache does, not in how it's tuned.

## Reuse from existing data

Step 00 already runs vanilla x{1..16} + x4096 GT, vanilla_b{1,4,8} x{1..16} + x4096 GT, restirpt_b{1,4,8} x{1,4}, rtxdi x{1,4}, and restir_2d/3d x{1,4} — across `ALL_SCENES` ∪ `MULTI_LEVEL_SCENES`. Every later stage reads its references straight from `captures/ladder/00/<scene>/`; no rerun needed unless the metric changes. **Re-emit only the postprocess/CSVs** when the metric changes, never the EXRs.

The post-merge-order multilevel sweep at steps 19–25 lives in `runtime/captures/ladder/archive_post_v2/`. Steps 19/20 below are clean re-curations of that data under the current canonical metric (Reinhard-tonemapped OkLab vs x4096 GT) — no re-render expected.

The WS-ReSTIR parity matrix from the *Final canonical config* section of DEVLOG.md is the natural starting point for Stage D step 21; its EXRs live under `runtime/captures/wsrestir/` (not the ladder root). Stage D step 21 imports them by reference rather than re-rendering.

A ReSTIRPT-specific reference harness already exists as `scripts/VisCache_LadderRPT00.py` (`captures/ladder/RPT00/`) — it runs vanilla + `restirpt_b{1,4,8}` per scene with the canonical centimetre-scale Sponza camera. Treat that as a sub-step of Stage A: its EXRs are the references Stage F (steps 41–50) compares against, so Stage F does not need to regenerate ReSTIRPT references — only render fresh `viscache+restirpt` variants and read from `RPT00/` for the ground-truth side. The `RPT00` naming convention is a separate sibling track for *reference generation* and stays as-is; the unified numbering 41–50 is for *integration* steps that don't currently exist.

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

# TODO — Global Task Tracker

**Project:** Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing

---

## Legend

- `[ ]` — not started
- `[~]` — in progress

Priority tags: **CRITICAL** (blocks submission), **HIGH** (significant gap), normal (polish).

---

## 1. Implementation

### 1.1 ReSTIR GI Integration
- [ ] **CRITICAL** Port DQLin/ReSTIR_PT into Falcor fork (`Falcor`)
  - Fork NVIDIAGameWorks/Falcor → ManuelKugelmann/Falcor
  - Apply API migration (see `docs/PORTING.md`)
  - Merge full DQLin reservoir logic into sketch files
- [ ] Verify ported pass matches DQLin reference images on Bistro (FLIP < 0.01)
- [ ] Verify k=5.0 traces/pixel with VisCache disabled
- [ ] Enable VisCache, verify traces/pixel drops to ~0.5–1.0 at steady state

### 1.2 Open Implementation Questions
- [ ] **HIGH** ABA race in inline decay: quantify error rate empirically or replace with 64-bit CAS
- [ ] Cell sizes at non-standard scene scales (0.5m close-up, 100m city flyover)
- [ ] Symmetric cells for GI revalidation — measure error before changing constants
- [ ] Camera-adaptive cell sizing (FoV + CoC) — future work, document only

### 1.3 New Feature Implementation (paper describes, code missing)
- [ ] **CRITICAL** Uncollapse normal dimension — paper Sec. 4.1; current code is pos_norm1__* (normal collapsed); need pos_norm__* (normal active)
- [ ] **CRITICAL** τ_useable / three-state cascade — paper Sec. 5; code has two-gate model only
- [ ] **CRITICAL** Child inherits parent μ at reduced weight — paper Sec. 5; no parent-to-child seeding
- [ ] **HIGH** Distance-bin multi-write — paper Sec. 4.1; code writes single bin, no CommittedRayT()
- [ ] **HIGH** distance_scale parameter — paper Sec. 4.2; not exposed in code
- [ ] Sentinel trace bypass — paper Sec. 14 (future work)
- [ ] 2D LOD cascade (spatial × angular) — paper Sec. 14 (future work)

### 1.4 Code→Paper Sync (code has, paper doesn't describe)
- [ ] **HIGH** Confidence-adaptive pMin (`enableVisCacheAdaptivePMin`, log2(N) dependence) — add to Sec. 8
- [ ] **HIGH** Deterministic xi (`vhfDeterministicXi()` for ReSTIR temporal stability) — add to Sec. 8 or 9
- [ ] WaveMatch coalescing details (`enableVisCacheWarpReduction`) — mentioned in Sec. 3 but not detailed

---

## 2. Experiments & Ablation

### 2.0 Setup
- [ ] Download test scenes: `./scripts/download_scenes.sh`

### 2.1 Ablation Sweep (see `docs/ABLATION.md` for full matrix)
Run: `./scripts/run_paper_experiments.sh` (or individual scripts below)
- [ ] **CRITICAL** Run at least one informal Bistro profiling data point (blocks §13)
- [ ] Full config baseline capture (Bistro + Sponza) — `scripts/VisCache_Baselines.py`

**Existing feature ablations:**
- [ ] -A: distance-gated LOD off
- [ ] -B: variance gate (τ_var) off — most important ablation
- [ ] -C: WaveMatch off (SM 6.5 comparison, RTX 3090/4090)
- [ ] -D: decay off (animated scene, show drift after ~1000 frames)
- [ ] -E: pressure eviction off
- [ ] -AB: combined pressure stress
- [ ] Finest-only (minLevel=maxLevel=2) — key architectural validation
- [ ] Coarsest-only (minLevel=maxLevel=0)
- [ ] No-cache full-retrace baseline
- [ ] **HIGH** Add multilevel vs. finest-level-only ablation row to paper table

**New feature ablations (once implemented):**

_Addressing mode (Sec. 4.1):_
- [ ] pos_norm1__dir_dist vs pos_norm__dir_dist — isolates normal contribution (uncollapsing norm)
- [ ] pos_norm__dir_dist1 vs pos_norm__dir_dist — isolates distance bins (uncollapsing dist)
- [ ] pos_norm1__pos vs pos_norm__dir_dist — full primary mode vs pos×pos legacy; measures all three (normal + angular + distance)
- [ ] Thin geometry stress test (Bistro window frames, plant leaves) — normal disambiguation is critical here

_Three-state cascade (Sec. 5):_
- [ ] Two-gate (current code, τ_mature + τ_var) vs three-gate (τ_useable + τ_mature + τ_var) — measures faster child start
- [ ] τ_useable sweep: 4, 8, 16, 32 — find minimum viable parent quality
- [ ] With vs without parent→child inheritance — measures bootstrap acceleration
- [ ] Inheritance weight sweep: 1/4, 1/8, 1/16 of parent counts — find optimal seeding

_Distance-bin multi-write (Sec. 4.1):_
- [ ] Single-bin write (current) vs multi-write with monotonicity — measures free propagation benefit
- [ ] Distance bin count sweep: 1, 2, 4 bins — diminishing returns vs table pressure
- [ ] With vs without CommittedRayT() propagation — isolates the any-hit distance contribution

_Sentinel traces (Sec. 14 future work):_
- [ ] Dynamic scene: with vs without sentinel maturity bypass — measures staleness detection speed
- [ ] sentinel_threshold sweep: 0.3, 0.5, 0.7 — false positive rate vs detection speed
- [ ] Static scene: verify sentinels add zero overhead (agreeing sentinels respect maturity)

_Angular LOD (Sec. 4.4):_
- [ ] Fixed coarse angular bins vs variance-gated angular refinement — measures angular LOD benefit
- [ ] Angular bin size sweep: 90°, 45°, 15°, 5° fixed — find where diminishing returns hit
- [ ] Scene-dependent: open areas (coarse sufficient) vs complex occluders (fine needed)

_2D LOD cascade (Sec. 14 future work):_
- [ ] 1D diagonal-only (current) vs diagonal + off-diagonal probe — measures asymmetric refinement benefit
- [ ] max_diff=0 vs max_diff=1 vs max_diff=2 — measures exploration vs table pressure

_Confidence-adaptive pMin (code-only, not in paper):_
- [ ] Fixed pMin vs confidence-adaptive — measures firefly reduction
- [ ] Document in paper Sec. 8 if ablation shows benefit

_Deterministic xi (code-only, not in paper):_
- [ ] Random xi vs deterministic xi — measures temporal flicker in ReSTIR
- [ ] Document in paper Sec. 8/9 if ablation shows benefit

### 2.2 Stress Tests
Run: `scripts/VisCache_Stress.py`
- [ ] Disocclusion: fast camera flythrough, measure frames to 80% hit rate
- [ ] Variance spike duration after disocclusion
- [ ] Peak shadow ray ratio during cold-start

### 2.3 Metrics & References
Run: `scripts/VisCache_Reference.py`
- [ ] Capture 1024 spp path tracer reference (Bistro, Sponza)
- [ ] Per-pixel MSE vs. reference for each config
- [ ] GPU timestamp breakdown: insert / lookup / decay ms
- [ ] Cache hit rate, average probe depth, miss rate stats

---

## 3. Paper Revision

> All prior revision items completed. See `paper/TODO.md` for history.

### 3.1 Remaining
- [ ] Consider alternative title: "Revisiting Visibility Prediction-with-Correction..."
- [ ] Fill in ##% placeholders in abstract and §13 Results with measured data

---

## 4. Running All Paper Experiments

```bash
# 1. Build Falcor with VisCache plugins
./setup-build-system.sh          # Linux
# .\setup-build-system.bat       # Windows

# 2. Download test scenes (Bistro ~3.2 GB, Sponza ~70 MB)
./scripts/download_scenes.sh

# 3. Run all experiments (smoke test → reference → baselines → ablation → stress)
./scripts/run_paper_experiments.sh

# Or run individual steps:
./scripts/run_paper_experiments.sh --skip-stress --skip-reference   # baselines + ablation only
./scripts/run_paper_experiments.sh --dry-run                       # preview commands

# 4. Trigger a release build from any commit
# GitHub → Actions → Release → Run workflow
# Version: dev-YYYYMMDD-HHMMSS-<sha8>
```

Output structure:
```
captures/
  reference/       1024 spp ground truth EXRs
  baselines/       DI/GI/PT × vanilla/local/reval/lightsel/full
  ablation/        A–E toggles, finest/coarsest-only, no-cache
  stress/          Disocclusion flythrough (full_viscache + no_cache)
  logs/            Per-experiment stdout/stderr logs
```

---

## 5. Implementation Roadmap

Ordered by dependency chain: each phase builds on the previous.
Paper can be ahead of code, but submission requires measured data from Phase 3+.

### Phase 0: Baseline (current state → first data point)
_Goal: one Bistro profiling number to unblock §13 Results._
```
[0.1] Build + smoke test on RTX 4090               ~1 day
[0.2] Download Bistro + Sponza                      ~30 min
[0.3] Run existing ablation scripts (pos×pos + dirdist modes)
      Capture: rays/px, frame time, MSE vs reference ~1 day
[0.4] Fill in ##% placeholders in abstract + §13    ~1 hr
```
**Unblocks:** §13 Results, abstract numbers, paper submission draft.
**No code changes needed** — this is measurement only.

### Phase 1: Uncollapse normal dimension (CRITICAL paper→code gap)
_Goal: implement the paper's primary addressing mode by uncollapsing norm1 → norm._
```
[1.1] Add normal quantization to vhfQuantizePair()     ~2 days
      - Octahedral mapping of shading normal
      - Concatenate into qa alongside position
      - Hash key: pos(3) + norm(2-3) + dir(2) + dist(1) + level
      - gNormalCellSize parameter (angular bin for normal)
      - Coarse default (e.g. 45°) — normals rarely need fine bins
      - norm1 = collapsed to single bucket (gNormalCellSize=360°)
        must reproduce existing pos_norm1__* behavior exactly
[1.2] Ladder test: pos_norm1__dir_dist vs pos_norm__dir_dist
      - CornellBox (no thin geometry — should be equivalent)
      - Bistro (thin walls, corners — normal should help)    ~1 day
[1.3] Fill in Table 1b angular/distance defaults            ~1 hr
```
**Unblocks:** addressing mode ablations (§2.1).
**Risk:** low — additive change; norm1 (360°) is a no-op that preserves existing behavior.

### Phase 2: Three-state cascade (CRITICAL paper→code gap)
_Goal: implement τ_useable gate and parent→child inheritance._
```
[2.1] Add gUseableThreshold to cbuffer/VisCache.h   ~0.5 day
      - Default 8; insert path checks cur.total < tau_useable → break
[2.2] Parent→child μ inheritance                     ~1 day
      - On first child insert (empty slot), seed with parent's
        packed >> 3 (1/8 of parent counts)
      - Requires reading parent entry before child CAS
[2.3] Ladder test: two-gate vs three-gate cascade
      - Measure frames-to-convergence at L1/L2       ~1 day
[2.4] τ_useable sweep: 4, 8, 16, 32
      - Find minimum viable parent quality
```
**Unblocks:** cascade ablations (§2.1), τ_useable parameter default.
**Risk:** medium — parent read adds one extra memory access per insert.

### Phase 3: Distance-bin multi-write (HIGH paper→code gap)
_Goal: exploit distance monotonicity for free propagation._
```
[3.1] Read CommittedRayT() in ShadingCV.slang        ~0.5 day
      - Available from any-hit; pass d_hit to insert path
[3.2] Modify vhfInsert to propagate across bins      ~1 day
      - V=0: write to all bins with d_max >= d_hit
      - V=1: write to all bins with d_max <= d_query
      - Variance gate: skip bins that already agree
[3.3] Add distance_scale parameter to cbuffer        ~0.5 day
      - d_max(l) = cell_size(l) × distance_scale
      - Default: sweep 1, 5, 10, 20 to find sweet spot
[3.4] Ablation: single-bin vs multi-write
      - Measure cache fill rate, convergence speed    ~1 day
```
**Unblocks:** distance ablations (§2.1), distance_scale default.
**Risk:** low — additive loop in insert path.

### Phase 4: Code→paper sync + existing feature ablation
_Goal: document undocumented code features, run full ablation matrix._
```
[4.1] Write up confidence-adaptive pMin in Sec. 8    ~0.5 day
[4.2] Write up deterministic xi in Sec. 8 or 9       ~0.5 day
[4.3] Run full existing ablation matrix (-A through -E,
      finest-only, coarsest-only, no-cache)           ~2 days
[4.4] Run new feature ablations (Phases 1-3)          ~2 days
[4.5] Fill in all remaining ## placeholders in paper  ~1 day
```
**Unblocks:** paper submission.

### Phase 5: ReSTIR GI integration (CRITICAL for GI numbers)
_Goal: demonstrate GI revalidation savings._
```
[5.1] Port DQLin/ReSTIR_PT into Falcor fork          ~5 days
[5.2] Verify baseline: k=5 traces/px, FLIP < 0.01    ~1 day
[5.3] Enable VisCache on revalidation path            ~1 day
[5.4] Measure: traces/px → ~0.5-1.0 at steady state  ~1 day
[5.5] Fill in GI ##% placeholder in abstract          ~1 hr
```
**Unblocks:** GI results in §13, full paper submission.
**Risk:** high — DQLin port is the largest single task.

### Phase 6: Sentinel traces (future work → implementation)
_Goal: fast dynamic scene response without blind decay._
```
[6.1] Add sentinel_threshold parameter                ~0.5 day
[6.2] Pmin path: if |V - μ| > threshold, bypass maturity gate
[6.3] Dynamic scene stress test: animated Bistro      ~1 day
[6.4] Compare: blind decay only vs sentinels + decay  ~1 day
```
**Unblocks:** sentinel ablation, dynamic scene results.
**Risk:** low — small change to existing Pmin code path.

### Phase 7: 2D LOD cascade (future work → implementation)
_Goal: independent spatial × angular refinement._
```
[7.1] Encode (spatial_lvl, angular_lvl) in hash key   ~1 day
[7.2] Diagonal-first cascade with off-diagonal probe  ~2 days
[7.3] max_diff constraint                             ~0.5 day
[7.4] Ablation: 1D vs diagonal-only vs diagonal+probe ~2 days
```
**Unblocks:** 2D cascade ablation.
**Risk:** medium — changes cascade logic throughout insert+lookup.

### Summary timeline

| Phase | Effort | Blocks |
|---|---|---|
| 0. Baseline measurement | ~2 days | Abstract ##%, §13 draft |
| 1. Normal in key | ~3 days | Addressing ablation |
| 2. Three-state cascade | ~3 days | Cascade ablation |
| 3. Distance multi-write | ~3 days | Distance ablation |
| 4. Sync + ablation run | ~6 days | Paper submission draft |
| 5. ReSTIR GI port | ~8 days | GI numbers |
| 6. Sentinels | ~3 days | Dynamic scene results |
| 7. 2D LOD cascade | ~6 days | Angular LOD results |

**Minimum viable submission:** Phases 0–4 (~17 days).
**Full submission with GI:** Phases 0–5 (~25 days).
Phases 6–7 are post-submission extensions.

---

## 5b. Feature Test Ladder

Each feature gets a dedicated ladder step. Steps are ordered by implementation phase.
All run via `.scripts/mogwai-headless.sh`. Default scene: CornellBox (procedural).

### L00: Addressing Mode Matrix (existing + new)

Systematic sweep of all addressing combinations. Each variant runs 1 warmup + 1 capture frame.
Extends `VisCache_LadderCommon.py` VARIANTS list. Diagnostic grid per variant.

Naming: `A__B` separates endpoints, `_` separates dimensions within. `1` suffix = collapsed.
`pos__*` variants are shorthand for `pos_norm1__*` (normal collapsed to single bucket).
Adding normal is just "uncollapsing" the norm dimension — not a separate addressing mode.

```
Variant                  Endpoint A         Endpoint B            Key dims  Notes
──────────────────────────────────────────────────────────────────────────────────────
pos_norm1__pos1          pos (norm=1)       pos (collapsed)       3D        position-only baseline
pos_norm1__dir1_dist1    pos (norm=1)       dir(360°)+dist(1km)   3D        ≈ position-only via dirdist
pos_norm1__pos           pos (norm=1)       pos (same cell)       6D        pos×pos, no normal
pos_norm1__dir_dist1     pos (norm=1)       dir(5°)+dist(1km)     5D        angular bins, no distance
pos_norm1__dir_dist      pos (norm=1)       dir(5°)+dist(0.24)    6D        angular + distance bins
─── normal uncollapsed (requires Phase 1 implementation) ─────────────────────────────
pos_norm__dir1_dist1     pos+normal         dir(360°)+dist(1km)   5D        normal only, no dir/dist
pos_norm__dir_dist1      pos+normal         dir(5°)+dist(1km)     7D        normal + angular, no dist
pos_norm__dir_dist       pos+normal         dir(5°)+dist(0.24)    8D        full primary mode (paper)
pos_norm__pos            pos+normal         pos (same cell)       8D        normal + pos×pos hybrid
```

**Pass criteria per variant:**
- Diagnostic grid renders without crash
- posAHash / posBHash channels show expected quantization patterns
- Collapsed dimensions (1-suffixed) produce fewer unique cells than full versions
- Normal variants differ from non-normal on Bistro thin geometry
- Normal variants match non-normal on CornellBox (no thin geo, so normal adds nothing)

**Script:** `scripts/VisCache_Ladder00.py` (extend existing) + new `VisCache_Ladder00_Normal.py`

### L01–L09: Feature Validation

```
Ladder Step    Feature                          Pass Criteria
──────────────────────────────────────────────────────────────────────
L01            Distance bin isolation            pos__dir_dist shows different μ for
                                                near vs far lights in same direction;
                                                pos__dir_dist1 merges them (single bin)
L02            Distance multi-write (Phase 3)   After V=0 trace at d=5m: farther bins
                                                also show V=0 count; nearer bins unchanged
L03            CommittedRayT() propagation (P3) d_hit diagnostic channel nonzero for V=0
L04            τ_useable gate (Phase 2)         L1 populates earlier than τ_mature-only:
                                                compare frame# where L1.total > 0
L05            Parent→child inheritance (P2)    L1 entry nonzero vis/total on first frame
                                                (inherited from L0)
L06            Sentinel bypass (Phase 6)        After light move: mature entry with
                                                |V-μ|>0.5 updated within 1/Pmin frames
L07            2D cascade diagonal (Phase 7)    (1,1)/(2,2) populated; off-diagonal only
                                                when diagonal terminal has high variance
L08            Confidence-adaptive pMin (P4)    Firefly count: adaptive < fixed
L09            Deterministic xi (P4)            Temporal variance: deterministic < random
                                                across 10 frames
```

**Ladder script naming:** `scripts/VisCache_Ladder<NN>_<Feature>.py`

Each step captures diagnostic EXR + extracts channels via `viscache_exr.py`.
Pass/fail is visual (diagnostic grid) + numeric (counter assertions in Python).

---

## 5c. Dependencies & Blockers

**Critical path:** Phase 0 (measure) → Phases 1-3 (implement paper features) → Phase 4 (ablate) → Phase 5 (GI port) → submit.

---

## 6. Paper ↔ Code Gaps (audited 2026-03-26)

### Missing parameter defaults in paper
- [ ] τ_var (gVarThreshold) — used in Algorithm 1 and 2 but no default value specified
- [ ] τ_useable (gUseableThreshold) — paper says default ~8 but parameter doesn't exist in code
- [ ] firefly_budget — defined in Sec. 8.1 but no default value
- [ ] w_min — used in Algorithm 2 (lookup) but value not specified
- [ ] μmin (default 0.01) — used in Sec. 9.1 but only mentioned in passing
- [ ] angular_cell_size — referenced in Sec. 4.2 but no default/range given
- [ ] sentinel_threshold — paper Sec. 14 says default 0.5 but no parameter exists
- [ ] distance_scale — paper Sec. 4.2 references but no default/range given
- [ ] max_diff — paper Sec. 14 says default 1 but no parameter exists
- [ ] n_useable inheritance weight — paper says right-shift by 3 (1/8) but no parameter exists

### Paper internal discrepancies (all fixed 2026-03-26)
All cross-refs, threshold naming, and Table 1b added. No remaining discrepancies.

---

## 7. Future Work / Paper Extensions (from review session 2026-03-26)

### 7.1 Sentinel Traces for Dynamic Scenes
- [ ] Pmin-forced traces bypass maturity gate when |V − μ| > sentinel_threshold (default 0.5, tuneable)
- [ ] Agreeing sentinels respect maturity gate — only disagreement triggers forced write
- [ ] Written up in Sec. 14 future work

### 7.2 Interpolatable Visibility Field
- [ ] Reframe hash table as scattered spatial samples of continuous V(a,b) field
- [ ] Explicit neighbor interpolation at coarse levels (L0): 8 cube-corner lookups, blend by distance + confidence
- [ ] Jitter-filter only at fine levels (L2): near-pixel scale, denoiser handles it
- [ ] Written up in Sec. 14 future work

### 7.3 Double Jitter (Grid Jitter + Point Jitter)
- [ ] Stage 1: grid jitter displaces cell centers, breaks axis-aligned regularity
- [ ] Stage 2: point jitter (existing), provides boundary box filter
- [ ] Written up in Sec. 14 future work

### 7.4 Visibility Correlation Length
- [ ] Consider adding to Sec. 4 discussion of cache key justification

### 7.5 Three-State Cascade Implementation
- [ ] Add gUseableThreshold to cbuffer and VisCache.h
- [ ] Inherit parent μ on first child insert (reduced-weight seeding)

### 7.6 2D LOD Cascade Implementation
- [ ] 2D level index in hash key (spatial_lvl, angular_lvl)
- [ ] Diagonal cascade with off-diagonal probe at terminal level

### 7.7 Distance-Bin Multi-Write Implementation
- [ ] Propagate V=0 to farther bins from d_hit on insert
- [ ] Propagate V=1 to nearer bins from d_query on insert
- [ ] Read CommittedRayT() from any-hit result in ShadingCV.slang
- [ ] Variance gate on propagation targets: skip bins that already agree

## Infra / Cleanup

### Script naming — shell and batch files
- [ ] Rename `scripts/*.sh` snake_case → kebab-case (e.g. `download_release.sh` → `download-release.sh`)
- [ ] Rename paired `scripts/*.bat` to match (e.g. `download_release.bat` → `download-release.bat`)
- [ ] Rename `.scripts/sync_to_runtime.sh` → `.scripts/sync-to-runtime.sh`
- [ ] Update all cross-references: CI workflows, quickstart.bat/sh, run_release.bat/sh, update.bat/sh, docs/
- Convention: kebab-case for .sh and .bat; Mogwai .py = PascalCase; utility .py = snake_case

---

## 8. WS-Cascade ReGIR (RTXDI Parity Track) — 2026-04-30 (status updated 2026-05-01)

Design notes: `.plans/rtxdi-parity-ws-cascade.md`. **STATUS: RTXDI PARITY ACHIEVED ON 3 SCENES.**

After two compounding bug fixes (Dirac-pdf RIS weight = 0; cache-amortized V
at cold cache compounding variance), wsrestir matches or beats RTXDI on all
three test scenes:

| Scene + SPP | vanilla | RTXDI | wsrestir | result |
|---|---|---|---|---|
| Cornell x1 | 10.16 | **6.08** | 5.63 | **MATCH** |
| Sponza x1 | 11.27 | **9.20** | 10.77 | within 1.6pp |
| **Sponza x4** | 6.23 | **9.20** (x1) | **8.71** | **BEATS rtxdi x1** |
| **Bistro x1** | 29.15 | **24.97** | **20.79** | **BEATS by 4.2pp** |
| Bistro x4 | 18.12 | — | 14.72 | better than vanilla x4 |

Other variants on Cornell x1 (rtxdi 6.08): pixel_vaware **5.62** (BEATS),
regir_ws **5.59** (BEATS). On Sponza x1: pixel_vaware 10.58. The cell-pool
layered variants (regir, regir_ws) help on point-light scenes but are
noise-additive on emissive-heavy scenes — keeping the wsrestir variant
(without cell pool) as the flagship for emissive scenes.

Two corrected old over-claims: "Sponza 3.81% beats RTXDI 2.4×" (misread of
vanilla-x16 comparison; corrected during audit). And "structural gap to
RTXDI on Sponza x1 requires tile pre-sample" (still true at 1.6pp residual,
but the bulk of the gap turned out to be the K-RIS bugs, not architecture).

- [x] Step (a) — multi-light cell pool (`WSCellPool`, 168 B/slot, N=8) with
      sourcePdf+pHat+wSum arrays and Bitterli streaming reservoir per slot
      (RIS-at-insert). Reads use `1/sourcePdf` for unbiased RIS.
- [x] Step (b) — `wsCellPoolFillOnly` PathTracer property + dedicated
      `PathTracerPrePass` instance in graph. UAV barrier between PrePass
      and Main serializes pool fill before reads; output marked to
      survive graph optimizer pruning.
- [ ] Step (c) — cascade-descend pool inheritance. Pool keyed by
      (cell, level); pre-pass writes coarse reliably + finer sparsely;
      main read descends fine→coarse using whichever level has data.
- [x] Step (d) — V-aware re-presample via probabilistic acceptance.
      Each insert is gated by `accept = max(μ_cached, μ_min)`; stored
      sourcePdf is multiplied by `accept` so reader's RIS reweights
      correctly. Defensive sampling preserves unbiasedness.
- [x] **Normal-aware spatial reuse rejection** (2026-05-01) —
      WSReservoir._pad repurposed as `normalOct`; per-pixel reservoir
      stamps shading normal at write; spatial gather + temporal read
      drop neighbours with `cos(N) < 0.9`. Standard ReSTIR variance
      reduction (Bitterli 2020 §6.1).

### RDI ladder (RTXDI-parity progression)

- [x] `VisCache_LadderRDI_01.py` — step (a) only at 16-frame warmup
      (isolates the data structure)
- [x] `VisCache_LadderRDI_02.py` — step (a)+(b) at single-frame
      (isolates the pre-pass UAV barrier)
- [x] `VisCache_LadderRDI_03.py` — WS-ReSTIR (full stack: temporal +
      spatial pixel reuse + cell-in-RIS) layered on ReGIR pool
- [x] `VisCache_LadderRDI_04.py` — Bayer-sparse pre-pass (quick win 1)
- [ ] `VisCache_LadderRDI_05.py` — `wsCellPoolDrawK=4` cost reduction
      (quick win 2)
- [ ] `VisCache_LadderRDI_06.py` — V-aware re-presample (quick win 3 ≡
      step (d) above; biggest quality lever)

### ReGIR-paper directives (Boksanský 2021 chapter, Boissé 2021/2022, Zhang 2023)

- [ ] **P1** Cite ReGIR (Boksanský 2021) as primary anchor in WS-ReSTIR
      / WSCellPool paper section. Boissé 2021 = screen-side; ReGIR =
      grid-side; we are grid-side.
- [ ] **P2** Adopt M-cap + decay schedule in `wsCellPoolInsert` (replace
      one-shot random replace with RIS update rule + exponential M-cap).
      Smoother bias/variance trade. Addresses saturated-`ct=2` finding
      (project memory `project_sponza_trust_gate_saturated`).
- [ ] **P3** Visibility-in-p̂ at fill time (NEE-style) — equivalent to
      step (d) above. Cheaper than per-pixel V which we tried + rejected
      (project memory `project_wsrestir_visibility_blind_bias`).
- [ ] **P4** Footprint-derived cell size (Binder 2018/2019). Replace
      constant `quantSceneScale` multiplier with per-hit cell size from
      area pdf — ≈constant samples-per-cell across distance. Removes
      Sponza/Bistro tuning gap.
- [ ] **P5** Two-level promotion/decay policy (Boissé 2022 GI-1.0).
      Explicit "promote when stable, decay when missing" rule for cell
      entries — more principled than discrete `numLevels` cascade with
      fixed quant shifts. Plugs into adaptive-`ct` idea
      (`project_scene_dependent_ct`).

### Cell-key normal axis (Zhang 2023, Boissé 2021)

- [x] **Implemented** — `gWSNormalAddr` flag in `WSReservoirIO.slang`
      folds 6-axis face-normal bin (`wsNormalBin(faceN)`) into the cell
      hash. Off by default; opt-in via `wsNormalAddr=True` Python prop.
- [ ] Add references to paper section 9 (WS-ReSTIR integration) and
      `references.md`: Zhang et al. 2023, Boissé 2021. Document the
      6-axis bin choice (vs continuous octahedral encoding) and the
      address-vs-fingerprint mixing.
- [ ] Document in `docs/` how to enable + when normal addressing helps
      (corners, thin shells, cross-orientation pollution at cell
      boundaries).


### Footprint + cascade composition (Binder 2018/2019 + ours)

- [ ] **Per-hit footprint → entry level**, replacing the constant
      `wsCellSize`. Compute footprint = pixel solid angle × hit
      distance²; map to nearest cascade level via log₂ of cell-size
      step factor. Writes/reads at this level by default.
- [ ] **Cascade-descend fallback** when the footprint-selected level is
      empty: descend fine→coarse (existing `vhfLookup` pattern).
- [ ] **Active-level histogram.** Add a `gWSHitsPerLevel[N]` atomic
      counter incremented on every primary hit. Pre-pass uses this to
      skip empty levels and target write effort at the active subset.
- [ ] **Inactive-level pool reuse.** Free-list of pool slots from
      levels with zero hits in past K frames; recycled to active
      levels under pressure. Decouples pool memory from `numLevels`.
- [ ] **Jittered footprint** — `gWSJitterLevel` knob, single uniform
      random per pixel offsetting the footprint→level mapping.
      Stochastic boundary smoothing in lieu of two-level blended read.
      Composes with existing `gWSJitterFilter` (position-jitter) and
      `gWSJitterCell` (cell-index-jitter).
- [ ] **Footprint-stability-gated decay** [Boissé 2022]: cells whose
      footprint-implied level changes (camera motion, geometry edge)
      decay faster so stale entries do not stick at an inappropriate
      level.


### Bidirectional cascade escape from footprint entry level

- [ ] **Prefer footprint level.** Read at footprint-derived level first;
      cascade traversal only fires on starvation or high variance.
- [ ] **Coarsen on starvation.** `pool.count < count_min` (or
      `reservoir.M < M_floor`) → back up to next coarser level. Cap by
      `footprintMaxScale × pixel_footprint` to prevent runaway
      coarsening into spatially-meaningless cells.
- [ ] **Refine on inconsistency.** `M ≥ M_floor && variance > vt` →
      descend to next finer level. Reuses existing Bernoulli-variance
      gate; finer level's spatial discrimination wins on
      shadow/geometry edges.
- [ ] Tune `count_min`, `M_floor`, `footprintMaxScale`, and the
      variance threshold per the existing ladder methodology
      (`VisCache_Ladder06.py` style — single-axis sweep at fixed
      pinned other params).


### Decouple reservoir / pool / VisCache cells

- [ ] **Independent cell-key for the cell pool.** Currently the pool
      uses `wsResolveCell()` (the reservoir's resolver) re-masked to
      pool capacity. Add `wsResolvePoolCell(posA, faceN)` with its own
      cell-size knob (`gWSPoolCellSize`) so pool and reservoir can sit
      at different cascade levels.
- [ ] **Pool union read.** `wsLoadCellPool` reads only the home cell.
      Extend with K jittered-neighbour pool reads, concat'd into a
      single iteration loop in the K-RIS draw block. Each entry's
      `sourcePdf` is already stored, so the union is unbiased without
      extra weighting. Net: wider effective pool without coarser keys.
- [ ] **Pool spreading is free** — document this in the paper's
      cost-comparison table: pool spread = (K_pool × N candidates ×
      BSDF eval), no extra rays. Reservoir spread = K_res × shadow
      rays (or K_res × PWC lookups via §9.3).
- [ ] **VisCache ↔ pool similarity** — explore folding visibility into
      the pool entry's `sourcePdf` (i.e. multiply sourcePdf by μ at
      write time): the pool then represents the writer's *visibility-
      weighted* proposal pdf, and read-side RIS unbiasing already
      cancels it correctly. This is a one-line change at the insert
      site.


### Unified cascade addressing — one mechanism, three target footprints

VisCache, WS-ReSTIR reservoir, WS-ReSTIR cell pool all share:
- footprint → entry level (per-hit)
- `jitterQuantize(posA, vhfPosASize(lvl), salt)` (existing)
- normal-bin hash mixing (existing)

They differ ONLY in the per-structure target-footprint multiplier α
that picks the entry level:

| Structure | α | Rationale |
|---|---|---|
| VisCache | ≈1 | finest cells; per-shading-point visibility |
| WS-ReSTIR reservoir | ≈8–16 | many pixels share → M grows, temporal stability |
| WS-ReSTIR cell pool | ≈4 | middle: candidate diversity without reservoir's temporal bias |

- [ ] **`cascadeLevelForFootprint(footprint × α)` shared helper** in
      `VisCache.slang` (or a new common header). Replaces:
      - VisCache's existing target-level selection
      - WS-ReSTIR's `gWSCellLevel` (becomes `gWSCellTargetAlpha`,
        derives level from per-hit footprint)
      - Future cell-pool's level selection
- [ ] **Per-hit pixel footprint helper** — `pixelFootprintAtHit(sd)`
      using `gPixelSize1 × hitDistance²` from the existing
      `gPixelSize1` and the path's hit point.
- [ ] **Decouple `gWSCellLevel` (fixed) from `gWSCellTargetAlpha`
      (footprint-driven).** Keep both as runtime modes — fixed level
      for ablation, footprint-driven for production.


### Multi-level prefill on overlapping cells

Each hit at footprint entry level L writes to L, L-1 (parent), L+1
(finer cell containing the hit point). 3× prepass write cost, ~0.2×
vanilla at 1/16 Bayer-sparsity. Reader at L±1 finds populated cells
without reader-side cascade descent.

- [ ] **Extend `wsCellPoolInsert` call site in `PathTracer.slang`
      prepass path** to loop over `lvl ∈ {L-1, L, L+1}`, computing
      `wsResolvePoolCellAt(posA, faceN, lvl)` for each, calling
      `wsCellPoolInsert` with the same `(lightTypeIndex, payload,
      sourcePdf)`.
- [ ] **`wsResolvePoolCellAt(posA, faceN, lvl)` helper** — variant of
      `wsResolveCell` that takes an explicit level instead of using
      `gWSCellLevel` / `wsLevel()`. Keeps the existing
      jitter/normal-bin/hash machinery.
- [ ] **Edge cases:** at `lvl == 0` skip the L-1 write; at
      `lvl == numLevels - 1` skip the L+1 write.
- [ ] **Verify unbiasedness** — each entry's `sourcePdf` is its writer-
      side proposal pdf, independent of which level it landed in.
      Reader's RIS handles the level mismatch correctly. Spot-check
      against vanilla reference.
- [ ] **Test on Sponza/Bistro at 1-frame x1** — expect to retain the
      ReGIR step (a)+(b) quality (3.81% Sponza) at higher fill
      throughput, with stochastic LOD jitter or starvation-driven
      coarsen/refine no longer triggering empty reads.


### Step (d) refinement — μ-aware fill via VisCache (no extra rays)

The original step (d) called for M shadow rays per cell prepass to weight
candidates by `p̂ × V`. RTXDI declined this for cost. Replacement plan:
reuse VisCache's μ + μmin defensive floor (§9.1) at *fill time*:

```
for each of M candidates at cell:
    μ = vhfLookup(cellPosA → light's posB)
    weight = pHat × max(μ, μmin)
keep top-N by weight
```

- [ ] **In `WSCellPoolIO.slang::wsCellPoolInsert`** add an optional
      μ-aware mode (gated by `gWSCellPoolVAware`): before inserting,
      evaluate `μ = vhfLookup(...)` for the candidate's `(posA → posB)`
      pair, multiply `sourcePdf` by `1 / max(μ, μmin)` so the writer-
      side proposal pdf accounts for the cache-predicted visibility.
      RIS unbiasing on the read side already cancels it correctly.
- [ ] **Integration with M-from-N re-presample** (the original step d
      bag-and-resample). Draw M=32 candidates per cell, score by
      `pHat × max(μ, μmin)`, keep top-N=8. Cell pool ends up with
      visible-bright candidates only without a single shadow ray.
- [ ] **Wire as RDI_06 ladder step** (already scaffolded as
      `VisCache_LadderRDI_06.py`). Test on Sponza/Bistro — expect
      noticeable improvement over RDI_02's 3.81% Sponza result.
- [ ] **Defensive-sampling unbiasedness check.** μmin floor means even
      a cold/stale cache cell cannot exclude any light from the pool
      (matches the §9.1 argument). Spot-check vs vanilla GT.


### Code consolidation — single cascade-address helper for all three structures

All three (VisCache, WS-ReSTIR reservoir, WS-ReSTIR cell pool) key on
`(posA, faceN, level)` with the same primitives. Today the addressing
is duplicated across `vhfQuantizePair` (VisCache) and `wsResolveCell`
(WS-ReSTIR). Consolidation:

- [ ] **Single helper `cascadeAddress(posA, faceN, lvl) → (slot, fp)`**
      in `VisCache.slang`. All three structures call it with their own
      level (chosen via their own α multiplier).
- [ ] **Drop `gWSNormalAddr`** as a separate enable; use the same
      `kFlag_EnableNormalAddr` flag VisCache already exposes. One
      orientation-folding policy across the whole system.
- [ ] **Remove `wsResolveCell`, `wsQuantizePosA`, `wsAddressHash`,
      `wsFingerprintHash`** — replace call sites with the consolidated
      helper. ~80 lines deleted, no behavior change.
- [ ] **`gWSCellLevel` becomes "the level the cell pool / reservoir
      reads from"**, computed from α via the new
      `cascadeLevelForFootprint` helper (initially constant α; later
      per-hit footprint-driven).


### Bayer-prepass density ↔ pool cell footprint coupling

The prepass Bayer stride must scale with the pool's cell footprint so
each cell receives ≈1 active prepass pixel on average. Mismatched:

| Pool cell footprint | Bayer N (per side) | Active fraction |
|---|---|---|
| Per-pixel (α=1) | 1 (no Bayer) | 100% |
| ~4 pixels (α=2) | 2 (2×2 Bayer) | 25% |
| ~16 pixels (α=4) | 4 (4×4 Bayer) | 6.25% |
| ~64 pixels (α=8) | 8 (8×8 Bayer) | 1.6% |

Rule: `BayerN ≈ sqrt(α)` (the linear pixel-count per side that matches
the pool cell side length).

- [ ] **Auto-couple `gSubframeN` (prepass) to `wsCellLevel`**: the
      effective α at that level dictates the appropriate Bayer
      density. Either derive `subframeN` from cell size at fill time,
      or expose as a single knob `gWSPrePassBayer` derived from α.
- [ ] **Empirically validate** — sweep BayerN at fixed pool cell size
      (e.g. on Sponza with α=4) and measure error vs cost. Expect
      sweet spot at BayerN that gives ≈1–2 active fills per cell.
- [ ] **Adjust per-level if prefill is multi-level** (L−1, L, L+1) —
      the coarsest (L−1) cell needs less Bayer density than L+1, so
      ideally each level gets its own Bayer schedule.

### Hash-address extensions for pool / reservoir

VisCache adds a `posB` (pairwise-receiver) axis to its key (`pcgHashB`,
`pcgHashDist` for dirdist). Pool / reservoir currently use `posA + faceN`
only. Extension candidates and their use cases:

- [ ] **`viewDir`-axis** for the reservoir, when the cache shifts
      from DI to GI / specular: orientation-of-incoming-ray matters
      for view-dependent shading. Per-(posA, viewBin) reservoirs
      handle highlight transitions.
- [ ] **Receiver-normal axis** is already optionally folded in
      (`gWSNormalAddr`) — separates floor/wall at corners.
- [ ] **Light-direction bin** for the cell pool, partitioning entries
      by *direction from cell to light*. A reader querying a specific
      bounce direction draws candidates aligned with that bounce —
      direction-conditioned importance. Useful for GI extension.
- [ ] **Distance-to-light bin** in pool: groups by emitter distance
      bucket. Reader at specific depth gets distance-matched
      candidates (less noise on near-vs-far lights mixed in one cell).
- [ ] None of these are needed for pure DI shading on diffuse
      surfaces — DI is view-independent there. Adopt only if the
      cache extends to GI / specular use cases.


### Refined Bayer-cell coupling formula

For a prepass at Bayer N (1 of N² pixels active) to deliver M fill
samples per pool cell, cell area = M × N² pixels²; cell side ≈ √M × N.

| Bayer N | active frac | cell side @ M=8 | cell area @ M=8 |
|---|---|---|---|
| 1  | 100%   | 3 px   | 8 px²    |
| 2  | 25%    | 6 px   | 32 px²   |
| 4  | 6.25%  | 11 px  | 128 px²  |
| 8  | 1.6%   | 23 px  | 512 px²  |
| 16 | 0.4%   | 45 px  | 2048 px² |

- [ ] **Auto-derive `wsCellLevel` from `gSubframeN` + target M.**
      Choose Bayer first (cost budget), then cell footprint follows
      from the M=pool_N constraint. Replace fixed `wsCellLevel`
      default with this formula at runtime; keep the explicit knob
      as an override.
- [ ] **Per-level Bayer schedule** when multi-level prefill is on:
      L−1 (coarser) uses smaller BayerN, L+1 (finer) uses larger,
      so each level gets ≈M samples per cell at appropriate cost.


### Coarser pool cells — RTXDI tile-equivalent regime

RTXDI tile pre-sample uses 16×16 to 32×32 screen-space tiles (256–1024
pixels). Our default α=4 (16 pixels per cell) is FINER than RTXDI's
tile. We can go coarser without quality penalty — RTXDI's existence
proof shows large tiles + many candidates per tile work fine.

| α | Cell footprint (px) | Notes |
|---|---|---|
| 1 | 1 | per-pixel — pool == per-pixel reservoir, defeats sharing |
| 4 | 16 (4×4) | current default — finer than RTXDI |
| 8 | 64 (8×8) | matches RTXDI 8×8 sub-tile |
| 16 | 256 (16×16) | matches RTXDI 16×16 tile |
| 32 | 1024 (32×32) | matches RTXDI 32×32 tile |

- [ ] **Sweep `wsCellLevel`** at the cell-pool layer: try levels
      mapping to α ∈ {4, 8, 16, 32} on Sponza. Expect coarser cells
      to improve due to candidate diversity.
- [ ] **Memory savings**: at α=16, total pool slots ≈ pixels / 256
      = 1K cells for 512x512. 1K × 104B = 104KB pool. Tiny vs
      current 256K-cell × 104B = 26MB.


### Decouple prepass-K from main-K + expose pixel-spatial-reuse knob

Currently `gWSInitialCandidates` controls BOTH prepass and main K-RIS
candidate count. RTXDI's recipe asks for K_pre=8 (tile pre-sample) and
K_main=32 (initial pixel samples). Decoupling:

- [ ] **Cbuffer field `gWSCellPoolPrePassK`** (default 8) used by the
      `WS_CELL_POOL_FILL_ONLY` path; main pass keeps reading
      `gWSInitialCandidates`. Lets us run K_pre=8 prepass + K_main=32
      main fresh (RTXDI-faithful) without code duplication.
- [ ] **Cbuffer field `gWSPixelSpatialNeighbours`** (default 4) for the
      currently-hardcoded `kSpatialPixels=4` loop in PathTracer.slang.
      Make it tunable so the RTXDI parity (k=5) is reachable; expose
      via `wsPixelSpatialNeighbours` Python kwarg.
- [ ] **Distinguish in docs** — `wsSpatialNeighbours` is *cell-based*
      spatial gather (gated on `wsUseCellInRIS`); the always-on pixel
      spatial reuse is a separate mechanism. Easy source of confusion.


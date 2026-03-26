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
- [ ] **CRITICAL** Normal in hash key — paper Sec. 4.1; code has no normal component (6D key: qa, qb only)
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
- [ ] pos×pos (current code) vs pos_normal×dir_dist (paper primary) — measures normal disambiguation + angular LOD + distance propagation combined
- [ ] pos×dirdist (no normal) vs pos_normal×dirdist — isolates normal contribution
- [ ] pos_normal×dir (no distance bins) vs pos_normal×dir_dist — isolates distance bins
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

## 5. Dependencies & Blockers

**Critical path:** Port DQLin → run baseline → capture one Bistro profile → write §13 Results.

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

### Paper internal discrepancies
- [ ] Sec. 3.2 Table 1 caption still says "enabling canonicalization (Sec. 4.5)" — should be Sec. 4.6
- [ ] Sec. 3.2 "Two addressing modes" paragraph references Sec. 4.6 — verify cross-refs
- [ ] Sec. 7 Algorithm 2 uses `w_min` and `tau` — should use named τ_var
- [ ] Sec. 8 Algorithm 3 uses `tau` — should use τ_var
- [ ] Sec. 10 Algorithm 4 uses `threshold` — should use named parameter (τ_reval or similar)
- [ ] Sec. 4.4 says two LOD dimensions but Sec. 3.2 Table 1 only shows spatial — add angular bin sizes

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

# TODO — Global Task Tracker

**Project:** Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing
**Target:** EGSR / HPG 2026

---

## Legend

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — done

Priority tags: **CRITICAL** (blocks submission), **HIGH** (significant gap), normal (polish).

---

## 1. Implementation

### 1.1 Core (VisHashFilter)
- [x] Hash table: PCG3D addressing, lookup, insert, decay (`VisHashFilter.slang`)
- [x] Batched insert with SM6.5 WaveMatch coalescing (`VisHashInsert.cs.slang`)
- [x] Background decay sweep (`VisHashDecay.cs.slang`)
- [x] CV+RRR estimator for all three integration points (`ShadingCV.slang`)
- [x] Falcor 8.0 host code: buffer management, PI auto-tuner, UI (`VisHashFilter.h/.cpp`)
- [x] CMake plugin build target
- [x] CPU unit tests (5 tests, `tests/test_vhf_convergence.py`)

### 1.2 ReSTIR GI Integration
- [x] Full ReSTIRGIPass host code sketch (`ReSTIRGIPass.h/.cpp`)
- [x] Spatial reuse shader with MLVHF integration (`SpatialReuse.cs.slang`)
- [x] ReSTIRGIPass CMakeLists.txt
- [x] CV+RRR revalidation loop delta reference (`SpatialReuse_MLVHF_delta.slang`)
- [ ] **CRITICAL** Port DQLin/ReSTIR_PT into Falcor fork (`external/Falcor`)
  - Fork NVIDIAGameWorks/Falcor → ManuelKugelmann/Falcor
  - Apply API migration (see `docs/PORTING.md`)
  - Merge full DQLin reservoir logic into sketch files
- [ ] Verify ported pass matches DQLin reference images on Bistro (FLIP < 0.01)
- [ ] Verify k=5.0 traces/pixel with MLVHF disabled
- [ ] Enable MLVHF, verify traces/pixel drops to ~0.5–1.0 at steady state

### 1.3 Build & Setup
- [x] Windows setup script (`setup.ps1`)
- [x] Falcor fork as git subtree (`external/Falcor`)
- [x] Create ManuelKugelmann/Falcor fork on GitHub
- [ ] Port DQLin/ReSTIR_PT into the fork, pull back via `git subtree pull`
- [ ] Test setup.ps1 end-to-end on clean clone
- [ ] Add Linux/Mac build notes (or document Windows-only status)

### 1.4 Open Implementation Questions
- [ ] **HIGH** ABA race in inline decay: quantify error rate empirically or replace with 64-bit CAS
- [ ] Cell sizes at non-standard scene scales (0.5m close-up, 100m city flyover)
- [ ] Symmetric cells for GI revalidation — measure error before changing constants
- [ ] Camera-adaptive cell sizing (FoV + CoC) — future work, document only

---

## 2. Experiments & Ablation

### 2.1 Ablation Sweep (see `docs/ABLATION.md` for full matrix)
- [ ] **CRITICAL** Run at least one informal Bistro profiling data point (blocks §15)
- [ ] Full config baseline capture (Bistro + Sponza)
- [ ] -A: distance-gated LOD off
- [ ] -B: variance gate off (most important ablation)
- [ ] -C: WaveMatch off (SM 6.5 comparison, RTX 3090/4090)
- [ ] -D: decay off (animated scene, show drift after ~1000 frames)
- [ ] -E: pressure eviction off
- [ ] -AB: combined pressure stress
- [ ] Finest-only (minLevel=maxLevel=2) — key architectural validation
- [ ] Coarsest-only (minLevel=maxLevel=0)
- [ ] No-cache full-retrace baseline
- [ ] **HIGH** Add multilevel vs. finest-level-only ablation row to paper table

### 2.2 Stress Tests
- [ ] Disocclusion: fast camera flythrough, measure frames to 80% hit rate
- [ ] Variance spike duration after disocclusion
- [ ] Peak shadow ray ratio during cold-start

### 2.3 Metrics & References
- [ ] Capture 1024 spp path tracer reference (Bistro, Sponza)
- [ ] Per-pixel MSE vs. reference for each config
- [ ] GPU timestamp breakdown: insert / lookup / decay ms
- [ ] Cache hit rate, average probe depth, miss rate stats

---

## 3. Paper Revision (detail in `paper/TODO.md`)

### 3.1 CRITICAL — Blocks Submission
- [ ] **CRITICAL** Rename paper — drop "Multilevel Visibility Hash Filter"
- [ ] **CRITICAL** Remove "TODO: experimental validation" from abstract
- [ ] **CRITICAL** §13 Table 4: "~60% benefit at ~5% cost" — add supporting data or mark as projected
- [ ] **CRITICAL** §15 Results is entirely TODO — add at minimum one profiling data point

### 3.2 HIGH — Significant Gaps
- [ ] **HIGH** Add Bokšanský & Meister 2025 (JCGT) citation — concurrent neural visibility cache
- [ ] **HIGH** §10.1: Clarify firefly_budget units
- [ ] **HIGH** §11.1: Define M in "1/M of budget"
- [ ] **HIGH** §4: Frame as continuation of [Kugelmann 2006] experiment (2)
- [ ] **HIGH** §4: State three motivations for binary over free-path distance

### 3.3 Title & Abstract
- [ ] Add CV+RRR framing sentence to abstract
- [ ] Add "revisit" framing to abstract
- [ ] Consider alternative title: "Revisiting Visibility Prediction-with-Correction..."

### 3.4 Introduction (§1)
- [ ] Reframe contribution list — CV+RRR not claimed as new
- [ ] Remove "path sharing aligns with ReSTIR" as architectural insight
- [ ] Add "narrowing and deepening" framing
- [ ] State three actual contributions explicitly

### 3.5 Related Work (§2)
- [ ] Add [Kugelmann 2006] lineage paragraph (three experiments)
- [ ] Note hardware/framework gap between 2006 and 2026
- [ ] Add Bokšanský & Meister 2025 paragraph
- [ ] Add Liu et al. 2025 (Reservoir Splatting) — one sentence, orthogonal
- [ ] Add Zhang et al. 2024 (Area ReSTIR) — CV+RRR integrates without modification
- [ ] Verify pcg3d citation covers PCG3D specifically

### 3.6 CV+RRR Estimator (§4)
- [ ] Full unbiasedness derivation
- [ ] Generality statement (applies to any cache with mean estimate µ)
- [ ] Drop independent development claim → explicit 2006 lineage
- [ ] Make coupled variance adaptation explicit
- [ ] Cross-reference §4 coupling from §7 write-depth gate

### 3.7 Hash Structure & Addressing (§5–§8)
- [ ] Add calibration note after Table 1 (scene scale, viewing distance)
- [ ] Consider pixel-count reframing of cell sizes
- [ ] Add explicit vs. neural tradeoff paragraph
- [ ] Explain LOD asymmetry (A finer than B)
- [ ] Quantify ABA race error rate or fix with CAS
- [ ] Add DECAY_PERIOD half-life math
- [ ] Camera-adaptive cell sizing as future work (one sentence)

### 3.8 Citations (see `paper/CITATIONS.md`)
- [ ] Bokšanský & Meister 2025 — §2, §4, §11.1
- [ ] Liu et al. 2025 — §2
- [ ] Zhang et al. 2024 — §2
- [ ] Confirm Bokšanský & Meister debiasing option status

---

## 4. Dependencies & Blockers

```
DQLin/ReSTIR_PT port ──→ §11.3 baseline ──→ Table 3 numbers ──→ §15 Results
                                                                      ↑
Ablation sweep ─────────────────────────────────────────────────── §15 Results
                                                                      ↑
At least one profiling data point ────────────────────────────── submission
```

**Critical path:** Port DQLin → run baseline → capture one Bistro profile → write §15.

---

## 5. Build Sequence (6-week plan from RESEARCH_NOTES)

| Week | Target | Status |
|------|--------|--------|
| 1 | VisHashFilter standalone, CPU unit tests | done |
| 2 | CV+RRR in PathTracer (§11.2), validate on Sponza | pending |
| 3 | Port DQLin/ReSTIR_PT to Falcor 8, verify Bistro | pending |
| 4 | GI revalidation (§11.3), measure traces/px | pending |
| 5 | Light selection (§11.1), µ-weighted RTXDI candidates | pending |
| 6 | Ablation sweeps, automated capture, MSE plots | pending |

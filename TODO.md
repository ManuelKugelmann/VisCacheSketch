# TODO — Global Task Tracker

**Project:** Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing

---

## Legend

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — done

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
- [ ] Warm-start level refinement: seed fine-level entries from coarse-level mu on first insert.
  `vhfInsert()` already walks coarse→fine for the variance write gate — carry `prevMu`/`prevTotal`
  through the loop and widen the initial `delta` when claiming a new slot (`origFp == 0`).
  Zero extra lookups, zero extra atomics. Inspired by SHaRC's `SHARC_BLEND_ADJACENT_LEVELS`
  (adjacent-level blending on camera move), but adapted: VisCache's LOD is fixed (not
  camera-distance-based), so the analogue is cold-start acceleration at finer levels.
  Caveat: coarse mu may be wrong for specific fine cells (e.g., coarse mu=0.8 but fine cell
  is deep shadow mu=0.0) — keep seed count small (cap ~4–8) so real samples dominate quickly.

---

## 2. Experiments & Ablation

### 2.0 Setup
- [x] Ablation capture script (`scripts/VisCache_Ablation.py` — 10 configs)
- [x] Baseline capture script (`scripts/VisCache_Baselines.py` — 14 DI/GI/PT configs)
- [x] Reference capture script (`scripts/VisCache_Reference.py` — 1024 spp)
- [x] Stress test script (`scripts/VisCache_Stress.py` — flythrough)
- [x] Scene download script (`scripts/download_scenes.sh` — Bistro, Sponza)
- [x] Full paper runner (`scripts/run_paper_experiments.sh` — runs all of the above)
- [x] Manual release workflow (`.github/workflows/release.yml` — timestamp+SHA versioning)
- [ ] Download test scenes: `./scripts/download_scenes.sh`

### 2.1 Ablation Sweep (see `docs/ABLATION.md` for full matrix)
Run: `./scripts/run_paper_experiments.sh` (or individual scripts below)
- [ ] **CRITICAL** Run at least one informal Bistro profiling data point (blocks §15)
- [ ] Full config baseline capture (Bistro + Sponza) — `scripts/VisCache_Baselines.py`
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

## 3. Paper Revision (detail in `paper/TODO.md`)

### 3.1 CRITICAL — Blocks Submission
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

**Critical path:** Port DQLin → run baseline → capture one Bistro profile → write §15.

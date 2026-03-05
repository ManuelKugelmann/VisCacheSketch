# Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing

**Author:** Manuel Kugelmann  
**Target venue:** EGSR / HPG 2026  
**Status:** Implementation in progress, paper draft in revision

---

## Overview

This paper develops the binary visibility experiment from [Kugelmann 2006] into a complete real-time system. The 2006 Diplomarbeit ran three separate cache experiments — irradiance (point, dir) → ℝ, binary visibility (point, point) → {0,1}, and free-path distance (point, dir) → ℝ≥0 — each with CV+RRR correction rates driven by their respective variances, stored in a fixed-resolution single-level spatial hash. This work narrows to binary visibility and deepens the architecture.

### Core mechanism

The **control-variate estimator with Russian roulette (CV+RRR)** converts a spatial visibility cache into an unbiased shadow ray estimator regardless of cache accuracy:

```
if rand < p:
    V = traceShadowRay()
    return µ + (V - µ) / p    # unbiased correction
else:
    return µ                   # no trace, use cached mean
```

where `p = clamp(var / varThreshold, pMin, 1.0)` and `var = µ(1 − µ)`.

The **Bernoulli structure** of binary visibility is what makes this clean: variance is fully determined by the cached mean — no separate variance estimator needed. The same scalar µ gives you both the cached estimate and the variance, enabling joint adaptation of correction rate and spatial resolution with a single threshold.

### The coupling (key architectural property)

The same variance signal drives two reinforcing mechanisms:
1. **Correction rate** — RR survival probability p in the CV+RRR estimator
2. **Spatial resolution** — write-depth gate determines which LOD levels receive updates

High-variance regions trace more often *and* at finer spatial resolution. Low-variance regions trace rarely and only update the coarse level. This self-regulating behaviour makes the system practical without per-scene tuning. The coupling was absent from the 2006 work where spatial resolution was fixed; it is one of two principal extensions in this paper.

### Three ReSTIR integration points

A single shared hash table serves three integration points:

| Point | Section | What it replaces | Benefit |
|-------|---------|-----------------|---------|
| DI candidate selection | §11.1 | V=1 assumption in RIS target | µ-weighted selection, better candidates |
| Post-shading correction | §11.2 | Unconditional shadow ray | ~88% shadow ray reduction |
| GI revalidation | §11.3 | k=5 full retrace per pixel | ~0.5–1.0 traces/px vs. 5.0 |

---

## Repository structure

```
Falcor/                      Git subtree — ManuelKugelmann/Falcor fork
                             (Falcor 8.0 + ported DQLin/ReSTIR_PT)
  .gitmodules                Falcor's own submodule file (upstream-facing)
  setup.bat / setup.sh       Falcor's original: submodule init + packman deps
  setup_vs2022.bat           Falcor's original: setup.bat + CMake VS2022 configure

Source/RenderPasses/
  VisHashFilter/             Complete Falcor 8.0 RenderPass plugin
    VisHashFilter.slang      Hash table: PCG3D addressing, lookup, insert, decay
    VisHashInsert.cs.slang   Batched insert with SM6.5 WaveMatch coalescing
    VisHashDecay.cs.slang    Background decay sweep
    ShadingCV.slang          CV+RRR estimator — all three integration points
    VisHashFilter.h/.cpp     Falcor 8 host: buffer management, PI auto-tuner, UI
    CMakeLists.txt           Plugin build target
  ReSTIRGIPass/              ReSTIR GI with MLVHF revalidation
    ReSTIRGIPass.h/.cpp      Falcor 8.0 host code (full port sketch)
    SpatialReuse.cs.slang    Spatial reuse kernel with CV+RRR integration
    SpatialReuse_MLVHF_delta.slang  Original delta reference
    CMakeLists.txt           Plugin build target

scripts/
  MLVHF_Graph.py             Mogwai render graph
  MLVHF_Ablation.py          Automated ablation capture (10 configs)

tests/
  test_vhf_convergence.py    CPU unit tests (5 tests, no GPU required)

paper/
  TODO.md                    Revision checklist (28 items, 4 critical)
  RESEARCH_NOTES.md          Design decisions, framing discussions, open questions
  CITATIONS.md               Citation integration plan for all 6 additions

docs/
  PORTING.md                 DQLin/ReSTIR_PT → Falcor 8.0 port guide
  ABLATION.md                Ablation matrix and per-config metric targets
  DESIGN.md                  Architecture decisions and tradeoffs
  ThesisMK.pdf               2006 Diplomarbeit
  multilevel-visibility-hash-filter-paper.pdf

.gitmodules                  Root submodule config (mirrors Falcor/.gitmodules)
.githooks/pre-commit         Blocks commits if .gitmodules files are out of sync
sync-submodules.sh           Bidirectional sync between root and Falcor .gitmodules
setup.sh                     Setup (submodules, packman, hooks, plugin copy)
TODO.md                      Global task tracker
```

---

## Lineage: Kugelmann 2006

The 2006 Diplomarbeit "Efficient Adaptive Global Illumination Algorithms" (Universität Ulm, supervisor Alexander Keller) established the prediction-with-correction framework used here. Three distinct experiments were conducted:

**Experiment 1 — Irradiance:** (point, direction) → ℝ. Continuous incident radiance cached in a fixed-resolution spatial hash. CV+RRR correction rate driven by irradiance variance.

**Experiment 2 — Binary visibility:** (point, point) → {0,1}. Direct ancestor of this paper. Fixed-resolution hash, CV+RRR with Bernoulli variance. Promising but limited by single-level resolution and offline rendering constraints.

**Experiment 3 — Free-path distance:** (point, direction) → ℝ≥0. Richer than binary — captures partial occlusion. Not pursued here: binary is sufficient for shadow decisions, cheaper to store, and the Bernoulli structure gives variance for free.

**What this paper adds beyond 2006:**
- Variance now governs spatial resolution via write-depth gate (absent in 2006, resolution was fixed)
- Three-level hash replacing single-level
- Bernoulli simplification made explicit — var = µ(1−µ), no separate estimator
- ReSTIR integration at three points (framework did not exist in 2006)
- Real-time hardware (inline DXR, SM 6.5)

---

## Hash table design

**Three LOD levels** with asymmetric cell sizes:

| Level | Cell A (shading pt) | Cell B (light/secondary) |
|-------|--------------------|-----------------------|
| L0 (coarse) | 10.0 m | 10.0 m |
| L1 (mid)    | 1.25 m | 2.50 m |
| L2 (fine)   | 0.08 m | 0.62 m |

Asymmetry justified for DI (B = light, spatially coherent emission). GI revalidation (B = surface) may warrant symmetric cells — flagged for future work.

Cell sizes calibrated for primary viewing distances 2–20 m (Bistro, Sponza). Camera-adaptive sizing via FoV + CoC is future work.

**Addressing:** PCG3D hash [Jarzynski & Olano 2020], jitter-before-quantize [Binder et al. 2018], double-hash probe (max 8 steps), pressure-scaled eviction (steps 0–1 protected).

**Entry format:** 8 bytes — uint fingerprint + packed [vis:16 | total:16].

**SM 6.5 WaveMatch:** coalesces threads targeting the same L0 cell into a single atomic — ~16× reduction in L0 contention.

---

## Ablation matrix

| Config | Toggle | Primary claim |
|--------|--------|--------------|
| Full | — | Baseline |
| −A | Distance-gated LOD off | LOD gate reduces insert cost in smooth regions |
| −B | Variance-gated depth off | Fine levels only needed at shadow boundaries |
| −C | WaveMatch off | SM6.5 reduces L0 atomic contention ~16× |
| −D | Decay off | Prevents mean drift after 1K+ frames |
| −E | Pressure eviction off | Protects probe chain length |
| −AB | Both A and B off | Maximum table pressure stress |
| Finest-only | minLevel=maxLevel=2 | Multilevel necessary for GI amortization |
| Coarsest-only | minLevel=maxLevel=0 | Coarse level insufficient for shadow boundaries |
| No-cache | VHF disabled | Full-retrace baseline |

Ablation −B (variance gate) is the most important: must show negligible MSE gain at measurable insert cost increase.

Finest-only tests the central architectural claim: without coarse levels, within-frame GI path-sharing amortization breaks (50–100 pixels → 50–100 distinct L2 cells instead of 3–5 L0 cells).

---

## Build instructions

```bash
# Clone (Falcor is included as a subtree — no extra flags needed)
git clone https://github.com/ManuelKugelmann/VisCacheSketch.git
cd VisCacheSketch

# Setup (copies plugins into Falcor tree, patches CMake, runs tests, enables hooks)
./setup.sh

# Fetch Falcor dependencies (packman: CUDA, slang, nvtt, etc.)
# Linux:
Falcor/setup.sh
# Windows:
Falcor/setup_vs2022.bat          # deps + generates VS2022 .sln
# or just deps without VS solution:
Falcor/setup.bat
```

`Falcor` is a git subtree of the ManuelKugelmann/Falcor fork (Falcor 8.0
with DQLin/ReSTIR_PT ported in). It lives directly in the repo — no submodule
init required. `setup.sh` copies the VisHashFilter and ReSTIRGIPass plugins
into the Falcor tree, registers them with CMake, and enables the pre-commit
hook for submodule sync checking. Falcor's own setup scripts (`Falcor/setup.bat`,
`Falcor/setup.sh`, `Falcor/setup_vs2022.bat`) handle submodule init and
packman dependency fetching — these are original NVIDIA scripts.

See `tests/test_vhf_convergence.py` for CPU unit tests (no GPU required).

Requirements: Visual Studio 2022, CUDA 12.x, Windows 10 SDK 10.0.19041+, GPU with DXR 1.1 (RTX 20xx minimum, RTX 30xx/40xx recommended for SM 6.5).

### Submodule sync (subtree workflow)

Because Falcor is a git subtree (not a submodule), there are **two** `.gitmodules` files:
- **Root `.gitmodules`** — what git actually reads for submodule config
- **`Falcor/.gitmodules`** — what upstream Falcor maintains

These must stay in sync. The pre-commit hook blocks commits if they diverge.
Use `sync-submodules.sh` to fix:

```bash
# After pulling upstream Falcor (Falcor/.gitmodules is authoritative):
git subtree pull --prefix=Falcor falcor master --squash
./sync-submodules.sh from-upstream
git add .gitmodules && git commit --amend --no-edit

# Before pushing to upstream Falcor (root .gitmodules is authoritative):
./sync-submodules.sh to-upstream
git add Falcor/.gitmodules
git commit -m "sync submodules for upstream"
git subtree push --prefix=Falcor falcor my-branch

# Just check (no changes):
./sync-submodules.sh check
```

---

## Related work

| Paper | Relation |
|-------|---------|
| Kugelmann 2006 (Diplomarbeit) | Direct ancestor — experiments (1)(2)(3) |
| Binder et al. 2018 | Spatial hashing, jitter-quantize, double-hash probe |
| Lin et al. 2022 (GRIS/ReSTIR_PT) | Essential baseline for §11.3 Table 3 ground truth |
| Bokšanský & Meister 2025 (JCGT) | Concurrent — neural visibility cache for light selection |
| Liu et al. 2025 (SIGGRAPH) | Orthogonal — Reservoir Splatting for temporal reuse |
| Zhang et al. 2024 (SIGGRAPH) | Orthogonal — Area ReSTIR for DOF/AA |
| Müller et al. 2022 (instant-ngp) | Hash grid backbone used by Bokšanský & Meister |
| Jarzynski & Olano 2020 (JCGT) | PCG3D hash function |

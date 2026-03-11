# Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing

**[Paper sketch](viscachepaper/paper-sketch.md)** | **[Combined paper](https://ManuelKugelmann.github.io/VisCacheSketch/paper.html)** | **[2006 Diplomarbeit (PDF)](docs/references/Kugelmann2006_ThesisMK.pdf)**

**Author:** Manuel Kugelmann
**Target venue:** EGSR / HPG 2026
**Status:** Implementation in progress, paper draft in revision

---

## History

The 2006 Diplomarbeit by MK ("Efficient Adaptive Global Illumination Algorithms", Universität Ulm, supervisor Alexander Keller) suffered multiple problems — side work for financial reasons, theft of personal belongings, overambitious scope, and experiments that were not automated enough — and was never properly finished.

The thesis developed a general framework called *predictions with correction at random* (Sec. 3.4) — using a cached prediction as control variate and Russian roulette to decide whether to correct, with generalized variance (tracked explicitly per cache entry) driving RR survival probability as adaptive sampling (Sec. 3.4.1). The framework was applied through many explorative cache experiments — visibility prediction (Sec. 3.2.2), contribution prediction (Sec. 3.2.3), and others — all using general variance estimators. The idea of using variance — not absolute light — to drive sampling rate was inspired by hints in Keller's lectures at Universität Ulm.

Using a control variate instead of zero on RR termination is standard Monte Carlo variance reduction — combining two textbook techniques (Knuth 1973; Hammersley and Handscomb 1964). The idea is at least implicit in the "go with the winners" family (Aldous and Vazirani 1994; Grassberger 2002). In the graphics context, Szécsi, Szirmay-Kalos and Kelemen [2003] formalized the non-zero termination estimate for rendering (CV, but with fixed RR probability). Szirmay-Kalos et al. [2005] added variance-driven RR via a splitting/RR framework using a scene-global average radiance estimate. The Kugelmann thesis arrived at the same CV+RR math independently but refined the **estimation source** (per-point spatial cache rather than a scene-global constant) and the **variance signal use** (generalized variance closing the cache-quality → trace-rate loop). The overlap with Szécsi et al. was found late in the writing process.

The spatial grids were visible in the thesis — screenshots show grid cells. What was an unmentioned implementation detail was the use of *spatial hashing* [Teschner et al. 2003] to map grid cells to memory — inspired by Teschner's work to sidestep the curse of dimensionality in naive grids. Spatial hashing was encountered during teaching assistant work on Keller's "Simulation Algorithms" lecture at Universität Ulm, where it was used for broad-phase physical collision detection. The thesis used it but did not describe or frame it as a technique.

The Bernoulli optimization (var = μ(1−μ), requiring no separate variance accumulator for binary visibility) was not realized in 2006 — the thesis used generalized variance estimation across all cached quantities. Narrowing to binary visibility and exploiting the Bernoulli structure is a contribution of this paper.

The test case was Instant Radiosity [Keller 1997], but the caching method was always algorithm-agnostic: it operates on pairwise queries regardless of the rendering algorithm generating them.

See [`docs/references/Kugelmann2006_ThesisMK.pdf`](docs/references/Kugelmann2006_ThesisMK.pdf) for the thesis and [`docs/references/Szecsi2003_VarianceReductionRR.pdf`](docs/references/Szecsi2003_VarianceReductionRR.pdf) for the Szécsi et al. [2003] paper (also on [ResearchGate](https://www.researchgate.net/publication/221546555_Variance_Reduction_for_Russian-roulette)).

---

## Overview

This paper develops the binary visibility prediction from [Kugelmann 2006] into a complete real-time system. The 2006 Diplomarbeit developed a general *prediction-with-correction* framework (Sec. 3.4) applied through many explorative experiments to visibility, contribution, and other cached quantities, with generalized variance-driven adaptive sampling. This work narrows to binary visibility — exploiting Bernoulli structure for free variance — and deepens the architecture with improvements from the intervening two decades.

### Core mechanism

The **control-variate estimator with Russian roulette (prediction-with-correction (CV+VRRR))** converts a spatial visibility cache into an unbiased shadow ray estimator regardless of cache accuracy:

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
1. **Correction rate** — RR survival probability p in the prediction-with-correction (CV+VRRR) estimator
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
  VisCache/             Complete Falcor 8.0 RenderPass plugin
    VisCache.slang      Hash table: PCG3D addressing, lookup, insert, decay
    VisCacheInsert.cs.slang   Batched insert with SM6.5 WaveMatch coalescing
    VisCacheDecay.cs.slang    Background decay sweep
    ShadingCV.slang          prediction-with-correction (CV+VRRR) estimator — all three integration points
    VisCache.h/.cpp     Falcor 8 host: buffer management, PI auto-tuner, UI
    CMakeLists.txt           Plugin build target
  ReSTIRPTPass/              ReSTIR PT with VisCache revalidation (DQLin's ReSTIR PT [SIGGRAPH 2022] ported to Falcor 8; maxBounces=1 for single-bounce GI, higher for multi-bounce PT)
    ReSTIRPTPass.h/.cpp      Falcor 8.0 host code (full port sketch)
    SpatialReuse.cs.slang    Spatial reuse kernel with prediction-with-correction (CV+VRRR) integration
    SpatialReuse_VisCache_delta.slang  Original delta reference
    CMakeLists.txt           Plugin build target

scripts/
  VisCache_Graph.py             Mogwai render graph (interactive + ablation presets)
  VisCache_Ablation.py          Automated ablation capture (10 configs, §15)
  VisCache_Baselines.py         Automated baseline capture (14 DI/GI/PT configs)
  VisCache_Reference.py         1024 spp path tracer ground truth capture
  VisCache_Stress.py            Disocclusion flythrough stress test
  smoke_test.py                 Headless plugin registration + graph wiring test
  download_scenes.sh            Download Bistro + Sponza test scenes
  run_paper_experiments.sh      Run all captures for the paper (end-to-end)

tests/
  test_viscache_convergence.py    CPU unit tests (5 tests, no GPU required)

paper/
  TODO.md                    Revision checklist (28 items, 4 critical)
  RESEARCH_NOTES.md          Design decisions, framing discussions, open questions
  CITATIONS.md               Citation integration plan for all 6 additions

docs/
  PORTING.md                 DQLin/ReSTIR_PT → Falcor 8.0 port guide
  ABLATION.md                Ablation matrix and per-config metric targets
  DESIGN.md                  Architecture decisions and tradeoffs
  references/                 Reference PDFs (auto-downloaded + own papers)
  multilevel-visibility-hash-filter-paper.pdf

.gitmodules                  Root submodule config (mirrors Falcor/.gitmodules)
.githooks/pre-commit         Blocks commits if .gitmodules files are out of sync
sync-submodules.sh           Bidirectional sync between root and Falcor .gitmodules
setup.sh                     Linux setup: calls Falcor/setup.sh + VisCache plugin copy
setup.bat                    Windows setup: calls Falcor/setup_vs2022.bat + VisCache plugin copy
TODO.md                      Global task tracker
```

---

## Lineage: Kugelmann 2006

The 2006 Diplomarbeit "Efficient Adaptive Global Illumination Algorithms" (Universität Ulm, supervisor Alexander Keller) established the prediction-with-correction framework used here. The thesis developed a general framework called *predictions with correction at random* (Sec. 3.4), applied through many explorative experiments to:

- **Visibility prediction** (Sec. 3.2.2): (point, point) → {0,1}. Direct ancestor of this paper.
- **Contribution prediction** (Sec. 3.2.3): predicting full lighting contributions rather than just visibility.
- And other cached quantities — all using generalized variance estimators.

The spatial grids were visible in the thesis (screenshots show grid cells). The grids used spatial hashing [Teschner et al. 2003] internally to map cells to memory — inspired by Teschner's work to sidestep the curse of dimensionality — but hashing itself was an unmentioned implementation detail, encountered during TA work on Keller's "Simulation Algorithms" lecture but not described as a technique in the thesis.

**What this paper adds beyond 2006:**
- Robust hashing with position-seeded jitter (modifying [Binder et al. 2018], hash from [Jarzynski & Olano 2020])
- Variance now governs spatial resolution via write-depth gate (absent in 2006, resolution was fixed)
- Three-level hash replacing single-level, LOD in the hash key [Gautron 2020, 2021]
- Bernoulli simplification made explicit — var = µ(1−µ), no separate estimator (not realized in 2006)
- ReSTIR integration at three points (framework did not exist in 2006)
- Real-time hardware (inline DXR, SM 6.5, lock-free atomics [Gautron 2021])

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
| No-cache | VisCache disabled | Full-retrace baseline |

Ablation −B (variance gate) is the most important: must show negligible MSE gain at measurable insert cost increase.

Finest-only tests the central architectural claim: without coarse levels, within-frame GI path-sharing amortization breaks (50–100 pixels → 50–100 distinct L2 cells instead of 3–5 L0 cells).

---

## Build instructions

```bash
# Clone (Falcor is included as a subtree — no extra flags needed)
git clone https://github.com/ManuelKugelmann/VisCacheSketch.git
cd VisCacheSketch

# Linux:
./setup.sh

# Windows:
.\setup.bat
```

Each root setup script:
1. Calls Falcor's own setup (submodule init, packman deps, git hooks;
   Windows also generates VS2022 `.sln`)
2. Copies VisCache and ReSTIRPTPass plugins into the Falcor tree
3. Patches CMake to register the plugins
4. Runs CPU unit tests

`Falcor` is a git subtree of the ManuelKugelmann/Falcor fork (Falcor 8.0
with DQLin/ReSTIR_PT ported in). It lives directly in the repo — no submodule
init required.

See `tests/test_viscache_convergence.py` for CPU unit tests (no GPU required).

Requirements: Visual Studio 2022, CUDA 12.x, Windows 10 SDK 10.0.19041+, GPU with DXR 1.1 (RTX 20xx minimum, RTX 30xx/40xx recommended for SM 6.5).

---

## Using a release

Download a release archive from the [Releases page](https://github.com/ManuelKugelmann/VisCacheSketch/releases). Archives are named `viscache-windows-<config>-<sha>.tar.gz`.

### Quick start

```bash
# Extract
tar xzf viscache-windows-Release-*.tar.gz

# Run with a scene (interactive)
Mogwai.exe --script scripts/VisCache/VisCache_Graph.py --scene path/to/Bistro_Interior.pyscene

# Run headless (no window — for capture/batch)
Mogwai.exe --headless --script scripts/VisCache/VisCache_Graph.py --scene path/to/scene.pyscene
```

### Running ablation captures

```bash
# All 10 ablation configs (§15) — 200 warmup + 16 capture frames each
Mogwai.exe --headless --script scripts/VisCache/VisCache_Ablation.py --scene Bistro_Interior.pyscene
# Output: captures/ablation/<config>/frame_NNNN.exr

# All 14 baseline configs (DI/GI/PT × vanilla/local/reval/lightsel/full)
Mogwai.exe --headless --script scripts/VisCache/VisCache_Baselines.py --scene Bistro_Interior.pyscene
# Output: captures/baselines/<pass>_<config>/frame_NNNN.exr
```

### Running a smoke test

```bash
# Verify plugins loaded and graph wiring works (no scene needed, exits immediately)
Mogwai.exe --headless --script scripts/VisCache/smoke_test.py
```

### Triggering a manual release

Go to **Actions > Release > Run workflow** on GitHub. Inputs:

| Input | Default | Description |
|-------|---------|-------------|
| `commit_sha` | HEAD of selected branch | Specific commit to build |
| `config` | Release | Release or Debug build |
| `prerelease` | false | Mark as pre-release on GitHub |

The version tag is auto-generated as `dev-YYYYMMDD-HHMMSS-<sha8>` from the commit timestamp and short SHA. No manual tagging needed.

### Scenes

The release does not include test scenes. Download separately:

- **Bistro** (Amazon Lumberyard) — primary benchmark scene
- **Sponza** (Crytek) — secondary benchmark

Place `.pyscene` files anywhere and pass `--scene path/to/file`.

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
| Kugelmann 2006 (Diplomarbeit) | Direct ancestor — CV+RR with per-point cache, generalized variance-driven adaptive sampling |
| Aldous & Vazirani 1994 | "Go with the winners" algorithms — CV+RR idea implicit |
| Grassberger 2002 | "Go with the winners" for general Monte Carlo |
| Szécsi et al. 2003 | Non-zero termination estimate for rendering (CV, but fixed RR probability) |
| Szirmay-Kalos et al. 2005 | "Go with the winners" for path tracing — added variance-driven splitting/RR |
| Hammersley & Handscomb 1964 | Monte Carlo Methods — textbook CV and RR |
| Knuth 1973 | TAOCP Vol. 3 — double hashing (Sec. 6.4) |
| Keller 1997 | Instant Radiosity — original 2006 test case |
| Gautron 2020, 2021 | LOD in hash key, lock-free GPU hash updates |
| Stotko et al. 2025 (MrHash) | Independent: variance-driven resolution in flat hash (TSDF domain) |
| Binder et al. 2018 | Spatial hashing, jitter-quantize, fingerprint collision detection |
| Lin et al. 2022 (GRIS/ReSTIR_PT) | Essential baseline for §11.3 Table 3 ground truth |
| Bokšanský & Meister 2025 (JCGT) | Concurrent — neural visibility cache for light selection |
| Liu et al. 2025 (SIGGRAPH) | Orthogonal — Reservoir Splatting for temporal reuse |
| Zhang et al. 2024 (SIGGRAPH) | Orthogonal — Area ReSTIR for DOF/AA |
| Müller et al. 2022 (instant-ngp) | Hash grid backbone used by Bokšanský & Meister |
| Jarzynski & Olano 2020 (JCGT) | PCG3D hash function |

# Research Notes
_Accumulated design decisions, framing discussions, open questions_
_Sessions: February–March 2026_

---

## Paper framing

### Title evolution
| Candidate | Problem |
|-----------|---------|
| Multilevel Visibility Hash Filter | "Filter" implies image-space denoiser. "Multilevel" buries the lead. CV+RRR invisible. |
| Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing | Current preferred. "Unbiased" carries the differentiating claim. |
| Revisiting Visibility Prediction-with-Correction for Real-Time Path Tracing | Alternative — stronger narrative arc, explicit 2006 lineage. |

**Decision pending.** Second candidate may be stronger for EGSR where the lineage argument is the paper's intellectual backbone. First is safer / more descriptive for a broad HPG audience.

---

### CV+RRR is not new — and that's fine

CV+RRR (control variates + Russian roulette gating) is a classical variance reduction technique. Appears in Szirmay-Kalos et al. and explicitly in [Kugelmann 2006] for both irradiance and visibility. It is underrated in the real-time path tracing literature despite being:
- Provably unbiased for any cache quality
- Easy to implement (one conditional + one division)
- Self-regulating (variance drives its own correction rate)

**Framing decision:** do not claim CV+RRR as a contribution. Claim the *application* — pairwise binary visibility, multilevel hash, ReSTIR integration — and use §4 as advocacy for the underused technique. The generality statement ("applies to any cache that provides a mean estimate µ — spatial hash, neural network, temporal reprojection") positions the paper as a reference for the technique, not just for the specific system.

---

### The 2006 lineage

[Kugelmann 2006] "Efficient Adaptive Global Illumination Algorithms", Diplomarbeit, Universität Ulm, supervisor Alexander Keller.

Three separate cache experiments:
1. **Irradiance** — (point, direction) → ℝ. CV+RRR correction rate driven by irradiance variance.
2. **Binary visibility** — (point, point) → {0,1}. CV+RRR with Bernoulli variance. Fixed-resolution single-level hash. Promising, underdeveloped.
3. **Free-path distance** — (point, direction) → ℝ≥0. Richer representation, not pursued in 2026 paper.

The cache was **fixed-resolution** — variance drove the **correction rate** only, not spatial resolution. This is the key distinction from the 2026 paper where variance also governs write depth.

**Framing:** "narrowing and deepening." 2006 was broader (irradiance + visibility) but shallower in each. 2026 narrows to binary visibility and deepens: multilevel structure, variance-driven spatial resolution, ReSTIR integration.

---

### The coupled variance adaptation

The central architectural property and the sharpest novelty claim:

> The same variance signal (var = µ(1−µ)) drives two reinforcing mechanisms simultaneously:
> 1. RR survival probability p = clamp(var / varThreshold, pMin, 1.0) — governs correction rate
> 2. Write-depth gate — governs spatial resolution of cache updates

High-variance regions: trace more often + write fine levels. Low-variance regions: trace rarely + only update coarse level.

**Why this works:** the Bernoulli structure of binary visibility means variance is fully determined by the cached mean. No separate variance estimator needed. One scalar µ gives everything.

**Why 2006 didn't have this:** spatial resolution was fixed. The coupling only becomes possible (and necessary) when the cache has multiple levels to adapt between.

**Claim:** variance-driven correction rate was [Kugelmann 2006]. Variance-driven spatial resolution + the coupling between them is new in 2026.

---

### Variance-based vs. value-based write depth

**Variance-based (current):** uses accumulated var = µ(1−µ) at the coarse level. Population signal — requires evidence across many samples before triggering fine writes. Robust against outlier samples.

**Value-based:** uses instantaneous residual |V − µ| from the just-traced ray. Sample signal — reacts to individual disagreements between trace and cache. Risk of noise-chasing (outlier V triggers unnecessary fine writes).

**Hybrid:** write fine levels only if (a) coarse variance is high AND (b) current sample disagrees with current level. Avoids smooth-region writes (variance gate) and noise-chasing (residual gate).

**Decision:** keep variance-based as primary. The hybrid formulation belongs in §7 as a design-space discussion, not implementation. If ablation −B shows the variance gate is not earning its keep, reconsider.

---

## Implementation decisions

### Hash table size
4M entries (1<<22) = 32 MB at 8 bytes/entry. Adequate for Bistro + Sponza. Scale to 16M for larger scenes. Entry count must be power-of-two (mask addressing).

### Cell size asymmetry (A finer than B)
Justified for direct illumination: endpoint A is the shading point (view-dependent BRDF, geometric normal — needs fine resolution), endpoint B is the light source (spatially coherent emission — tolerates coarser). GI revalidation breaks this: B is also a surface. Options: symmetric cells at L2 value, or separate CELL_GI configuration. Flagged for future work — do not implement before ablation shows it matters.

### ABA race on packed uint32
The current inline CAS decay does: read packed, compute decay delta, InterlockedAdd(-sub). If another thread writes between read and add, the subtracted amount is computed from stale data. Worst case: slightly over-decays by one sample's worth. Claimed as "wastes traced sample" in §6 — this is too casual. Either quantify (expected error rate ~1/waveSize ≈ 3%) or replace with proper 64-bit CAS that atomically reads and decays. **Do not dismiss without data.**

### WaveMatch (SM 6.5)
Coalesces threads targeting the same L0 cell (10m grid — many pixels share the same cell). Reduces atomic contention ~16× at L0. Graceful fallback: set `enableWarpReduction = false` for SM 6.4 hardware, per-lane atomics, ~16× more contention but functionally identical.

### PI controller for decay period
Auto-tunes `decayPeriod` (frames per full table sweep) based on eviction/insert ratio. Target: evict ~10% of inserts. Fast action: tunes down to 15 frames. Static scenes: tunes up to decayPeriodMax (default 600). Quality knobs (varThreshold, pMin) are never auto-tuned — only the decay rate.

### Mogwai graph ordering
VisHashFilter must execute before PathTracer, RTXDIPass, ReSTIRGIPass. It owns the table buffer; downstream passes retrieve it via InternalDictionary. If VisHashFilter is not in the graph, all three downstream passes fall back to V=1 / full retrace with a logWarning.

---

## Open questions

### Cell sizes at non-standard scene scales
Current constants calibrated for 2–20 m primary viewing distances. Will produce incorrect LOD selection at 0.5 m (interior close-up) or 100 m (city-scale flyover). Add calibration note to §5.2. Camera-adaptive scaling via FoV + CoC is the principled fix — defer to future work but state it.

### Symmetric cells for GI revalidation
Current L2 asymmetry: cellA=0.08m, cellB=0.62m. For GI (point-to-point between surfaces), B should probably match A. Quantify the error before changing constants — may not matter at L2 where both A and B are close to each other spatially.

### Free-path distance (experiment 3 from 2006)
Binary is sufficient for hard shadow decisions. But for soft shadows with many-light sampling, free-path distance would be richer — it captures the probability of traversal at a given distance, not just binary hit/miss. Potential future work with a float cache entry instead of bool. Would require separate variance estimator (not Bernoulli). Not in this paper.

### Neural visibility cache (Bokšanský & Meister 2025)
Same §11.1 idea (visibility-weighted WRS for light selection) with a neural hash grid instead of a spatial hash. Their default mode is biased (uses network output directly for shading). CV+RRR would make it unbiased — worth noting as a unifying observation in §4. Confirm: does their paper have a debiasing option? If not, that sentence is a contribution of the discussion.

---

## Comparative forks — build sequence

### Essential (blocks paper)
- **DQLin/ReSTIR_PT** (Lin SIGGRAPH 2022) — must port to Falcor 8.0 (~2 days). Only baseline validating Table 3 "5.0 traces/px at k=5" ground truth. Cannot publish §11.3 without this.
- Falcor built-in PathTracer + RTXDIPass — zero effort, already in tree.

### Secondary (modern context)
- **guiqi134/Area-ReSTIR** (Zhang SIGGRAPH 2024) — Falcor 8.0 native. Modern DI baseline. Orthogonal (DOF/AA via lens×light). CV+RRR applies at same post-shading point.
- **Jebbly/Reservoir-Splatting** (Liu SIGGRAPH 2025) — Falcor 8.0 native. Temporal reuse robustness. Splats path reservoirs, NOT visibility — correct this framing everywhere.

### Monorepo strategy
One Falcor 8.0 tree, each technique in RenderPasses/ subdirectory, shared GBuffer/scene/NRD. Tag `baseline-v0` before any modifications.

---

## Build sequence (6 weeks)

| Week | Target |
|------|--------|
| 1 | VisHashFilter standalone, CPU unit tests |
| 2 | CV+RRR in PathTracer (§11.2), validate on Sponza |
| 3 | Port DQLin/ReSTIR_PT to Falcor 8, verify matches Bistro figures |
| 4 | GI revalidation (§11.3), measure traces/px vs. Table 3 |
| 5 | Light selection (§11.1), µ-weighted RTXDI candidates |
| 6 | Ablation sweeps, automated capture scripts, MSE plots |

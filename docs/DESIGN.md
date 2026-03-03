# Design Decisions
_Architecture rationale and tradeoffs_

---

## Hash table

### Entry format: packed uint32
`[vis:16 | total:16]` in one 32-bit word. Single InterlockedAdd keeps vis and total always in sync — no torn reads possible. Overflow decay (subtract 1/8 when total > 0xE000) preserves mean ratio within ~0.003%. Half-life arithmetic: at 300 frames/sweep, L = 0.875^(300/N) where N is total samples — confirm values are non-arbitrary before submission.

**Alternative considered:** separate uint16 buffers for vis and total. Rejected: two atomics per insert, torn reads possible between them.

### Fingerprint for collision detection
Separate PCG3D hash chain for fingerprint vs. address. Both derived from (qa, qb, lvl) but with different constants — ensures independence. On fingerprint mismatch: treat as empty (competing entry from different cell), apply pressure-scaled eviction if probe step ≥ 2.

### Double-hash probing
Step size h2 = fingerprint | 1 (odd, guarantees full coverage of power-of-two table). Max 8 steps. Beyond 8: skip insert, count as eviction for stats. Steps 0–1 always protected from eviction — preserves well-established entries in preferred slots.

### WaveMatch coalescing (SM 6.5)
L0 cells (10m) are shared by many pixels — without coalescing, hundreds of threads compete for the same atomic per frame. WaveMatch identifies all lanes targeting the same slot, elects one to do a single combined atomic. Reduces L0 contention ~16×. Graceful fallback to per-lane atomics on SM 6.4.

---

## LOD selection

### Distance-gated range
Heuristic: project cell size to screen pixels, gate levels to those within [kFootprintMin=4, kFootprintMax=64] pixels. Not a principled FoV/CoC formula — see future work. Produces stable 2–3 active levels for typical interior/exterior traversal at 2–20m.

### Asymmetric cell sizes
Endpoint A (shading point): finer — BRDF is view-dependent, geometric normal matters at fine scale.
Endpoint B (light/secondary hit): coarser — emission is spatially coherent, slight positional error tolerable.

Breaks for GI revalidation (B = surface). Options:
1. Symmetric cells at L2 value (0.08m both) — more correct, higher memory pressure
2. Separate CELL_GI[3] configuration — correct, more complex
3. Status quo — acceptable if GI revalidation MSE is within tolerance

**Decision:** status quo pending ablation. Revisit if GI revalidation MSE is anomalous vs. DI.

---

## CV+RRR estimator

### pMin floor
Hard lower bound on survival probability. Prevents p → 0 in perfectly smooth regions where var ≈ 0. Without pMin, an entry with µ=1.0 would never correct a suddenly-occluded path. pMin=0.05 means one correction ray per ~20 queries even in perfectly cached regions — sufficient to detect step changes within a few frames.

### Adaptive pMin via firefly budget
`pFloor = clamp(luminance(C) * max(µ, 1-µ) / fireflyBudget, pMin, 1.0)`

High-contribution shadow boundaries get higher floor → more correction rays → cache warms faster at the edges that matter most for visual quality. Low-contribution regions use base pMin → minimal waste.

**Known issue:** firefly_budget units underspecified in §10.1. Needs clarification: is it a luminance threshold, a fraction of average frame luminance, or a fixed constant? Currently treated as a fixed constant — document this.

### µ_min in light selection (§11.1)
`µ_min = 0.05` — epsilon-greedy floor. Ensures every light has nonzero selection probability. Without this: a light that happens to be occluded in all cached samples gets µ=0 and is never selected — feedback death. With µ_min: it stays selectable, can recover if occlusion changes.

This is the unbiasedness guarantee for §11.1: every light has nonzero probability → RIS support condition satisfied → estimator is unbiased. Unlike Bokšanský & Meister 2025 default mode which uses neural output directly (biased).

---

## Decay

### PI controller for decayPeriod
Proportional-integral controller on eviction/insert ratio. Target: ~10% eviction rate. Fast action scenes: decayPeriod tunes down to 15 frames. Static scenes: tunes up to decayPeriodMax (600 default).

Only decayPeriod is auto-tuned. varThreshold and pMin are quality knobs — never auto-tuned.

### Inline overflow decay vs. scheduled decay
Two separate decay mechanisms:
1. **Inline overflow decay:** triggers when total > 0xE000 — prevents uint16 saturation. Subtracts 1/8 of both counters atomically within the insert path. No separate pass needed.
2. **Scheduled background sweep:** csDecay.cs.slang, visits 1/decayPeriod of the table per frame. Handles time-based staleness for animated scenes. Can be disabled (decayPeriod=0) for static rendering.

### ABA race in inline decay
Read packed → compute decay delta → InterlockedAdd(-sub). If another thread writes between read and add: subtract is computed from stale data, slightly over-decays. Expected error: ~1/waveSize ≈ 3% of decay events. **TODO: quantify empirically or replace with 64-bit CAS.**

---

## ReSTIR integration

### InternalDictionary handoff
VisHashFilter executes first, writes mpHashTable ref + params to InternalDictionary. Downstream passes (PathTracer, RTXDIPass, ReSTIRGIPass) retrieve via `dict["vhfTable"]`. If VisHashFilter not in graph: downstream passes log warning and fall back to V=1 / full retrace. No crash, graceful degradation.

### Why three integration points share one table
The same V(A,B) cache entry is useful for:
- §11.2 post-shading correction: A=shading point, B=light sample
- §11.1 candidate selection: same (A,B) pair being evaluated for RIS weight
- §11.3 GI revalidation: A=primary hit, B=neighbor's secondary hit

They can share cache state because all three are querying pairwise binary visibility between surface regions. Different algorithms, same underlying quantity. Single table avoids 3× memory and 3× warm-up cost.

---

## Future work (explicitly deferred)

### Camera-adaptive cell sizing
Replace fixed CELL_A/B constants with:
```
cellSize(lvl, dist) = basePixels[lvl] * max(geoPixelSize(dist), CoC(dist))
```
Makes scheme resolution/scale/FoV-independent. Problems: cell sizes change with camera (triggers accelerated decay), non-monotone near focus plane (CoC dominates). Endpoint B has no natural distance (use dist(A, cam) as proxy). One sentence in §6, defer to future work.

### Free-path distance cache (Experiment 3 from [Kugelmann 2006])
Richer than binary — captures partial occlusion, useful for participating media and many-light soft shadows. Requires float cache entry (not packed bool), separate variance estimator (not Bernoulli). Not in this paper.

### Joint irradiance + visibility cache
2006 approach — cached both quantities in the same hash. Would allow CV+RRR correction of both indirect illumination and direct visibility in one system. Interesting but doubles the entry size and halves the effective cache capacity for each quantity. Not in this paper.

### Symmetric cell sizes for GI revalidation
CELL_GI[3] configuration with symmetric A=B sizes for (point, point) queries where B is a surface rather than a light. Low priority pending ablation results.

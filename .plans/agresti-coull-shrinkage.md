# Agresti-Coull Shrinkage on Cached Cell μ — Design Note

**Status:** Design idea, not implemented. Lower priority than stderr=0.10 (which is already the SPP-adaptive answer per SPONZA_STDERR). File for later if CV+RRR variance at cold cells turns out to be a pain point.

## Distinction from gate work

- **Gate question** (Wilson / stderr / vt): *when do we trust the cached μ?* Resolved: stderr=0.10 (SPONZA_STDERR).
- **Cache-contents question** (this design): *what value should we store as μ in the first place?* Currently: raw `μ = X/N`. Proposed: A-C-shrunk `μ̃ = (X + 2)/(N + 4)` (95%-CI form) or generalized `μ̃ = (X + z²/2)/(N + z²)`.

These are orthogonal — gate decides trust over the existing μ; shrinkage changes the μ that gets compared / used downstream.

## Why it might matter

The cache's μ feeds into multiple sites that are sensitive to extreme values:

1. **CV+RRR estimator (§12)**: residual `(V_obs − μ_cell)`. At a cold cell where the first few samples happened to all be visible (X=N), raw μ=1.0; if the next sample is occluded, the residual is `(0 − 1) = −1` — a 100% swing that gets amplified by the RR scaling. Shrunk μ̃ at small N pulls toward 0.5 (e.g. N=2, X=2 → μ̃=4/6≈0.67), so the residual is smaller and the variance bound tighter.

2. **Adaptive pMin / variance-driven RR**: `p = saturate(var/varThreshold)` uses raw var = `μ(1−μ)`. At μ=1 or μ=0 this is exactly 0 — the gate computes "no variance, fully trust", which is technically correct but presumes the cell is perfectly observed. Shrunk μ̃ never lands at 0 or 1 → variance is always positive → the RR sees the cell as having residual uncertainty.

3. **WS-ReSTIR target-pdf folding (c1/c2/c3 not yet implemented)**: if/when we multiply pHat_reader by cell μ, an extreme μ=0 from cold-cell-with-one-occluded-sample would zero out a candidate that's actually likely to be visible. Shrunk μ̃ would protect against this.

## Math

For 95% CI (z² ≈ 4 → "add 4" form):

```
μ̃ = (X + 2) / (N + 4)
```

For general z² (e.g. 3.84 for 95%, 6.63 for 99%):

```
μ̃ = (X + z²/2) / (N + z²)
```

At large N: `μ̃ → X/N` (no shrinkage). At small N: `μ̃ → 0.5` (uniform prior). Smooth interpolation.

Equivalent to a Beta(z²/2, z²/2) Bayesian prior on the per-cell visibility.

## Implementation sketch

Single line in `vhfLookup` and elsewhere we read μ:

```slang
// In VisCache.slang ~line 989-990:
//   uint  vis = e.packed >> 16u;
//   float mu  = float(vis) / float(total);  // raw
//   float var = mu * (1.0f - mu);

// Replace with shrinkage:
float zsq = gMuShrinkZSquared;  // 0 = off (legacy raw); 4 = "add 2,4"; 3.84 = 95% CI
float Nf  = float(total);
float Xf  = float(vis);
float mu  = (Xf + zsq * 0.5) / (Nf + zsq);
float var = mu * (1.0 - mu);
```

Same shape change wherever else μ is read (vhfMatureRequired, the DI write paths, etc.). Probably 5–10 sites.

Cbuffer field: `gMuShrinkZSquared` (one float, default 0 = legacy).

## Test plan

Sweep on Sponza + BistroInt at canonical x{4, 16}:
- `mu_shrink=0` (raw, baseline)
- `mu_shrink=1` (mild prior, "add 0.5, 1")
- `mu_shrink=4` (95%-CI "add 2, 4")
- `mu_shrink=8` (stronger)

Check whether CV+RRR variance metrics (relmse, RMSE) improve at low SPP without hurting high SPP. The hypothesis is that shrinkage stabilizes cold cells at small N without affecting mature cells (where shrinkage vanishes).

## Risks

- **Bias**: the cached μ is no longer an unbiased estimate of true visibility. CV+RRR's unbiasedness proof relies on `E[V_obs − μ_cache]` being zero in expectation; with shrunk μ̃ this is no longer true at small N. Need to track whether the bias is bounded and whether it's worth the variance reduction.
- **Interaction with stderr gate**: stderr already protects us at low N (refuses trust). With shrinkage AND stderr, we're double-protecting; the shrinkage might be redundant where stderr is active.
- **Storage**: no change — cache still stores X and N (uint16 packed); μ̃ is computed on read. Zero memory cost, one extra fmaa per read.

## Estimated effort

- Slang patch: ~30 min, ~10 LOC across 5–10 sites.
- Cpp wiring: ~30 min (Params + GPUParams + props + GUI + GPU memcpy + PathTracer cross-pass bind).
- Sweep + analysis: ~1 hour.

**Total: ~2 hours**, low risk (additive, gated by `gMuShrinkZSquared > 0`).

## Why this is filed and not built

`stderrThreshold = 0.10` from SPONZA_STDERR resolves the SPP-dependent vt finding cleanly. Shrinkage is a *different* axis — about cache contents at cold cells — that hasn't shown empirical pressure yet. Build only if CV+RRR cold-cell variance becomes a measurable pain point in a downstream sweep, or if c1/c2/c3 (μ in pHat) lands and we observe extreme-μ damage there.

Mentioned in DEVLOG "Failed approaches / future ideas" if needed.

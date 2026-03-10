# 8. Control Variate with Russian Roulette

The cached mean μ serves as a control variate [Szirmay-Kalos et al.]. Analytic lighting (BRDF × Le × G) is always evaluated. Only the shadow ray is gated:

**Algorithm 3: Shading with Cached Visibility**
```
Input: hit, light
analytic <- brdf x Le x G
r <- lookup(hit.pos, light.pos)
if r = MISS then
  V <- trace(hit, light); insert(V)
  return analytic x V
p_s <- clamp(r.var / tau, P_MIN, 1)
if random() < p_s then
  V <- trace(hit, light); insert(V)
  return analytic x (r.mean + (V - r.mean) / p_s)
else
  return analytic x r.mean     // no trace, no insert
```

**Unbiasedness proof.** The estimator V̂ equals μ + (V − μ)/p with probability p, and μ with probability (1−p). E[V̂] = p·(μ + (E[V]−μ)/p) + (1−p)·μ = E[V]. The residual variance is Var[V̂] = (1/p − 1)·Var[V − μ]. When μ = E[V], the residual is zero — a perfect cache needs no correction rays. Cache quality affects only efficiency (residual variance), never correctness. Only traced values are inserted — returning μ without tracing does not update the cache, preventing positive feedback.

**Generality.** CV+RRR converts any visibility estimate μ — whether from a spatial hash (this work), a neural network [Bokšanský and Meister 2025], temporal reprojection, or spatial neighbor polling — into an unbiased estimator wherever a mean estimate is available. The technique is agnostic to the source of μ; cache quality affects only efficiency, never correctness.

**Why binary visibility.** [Kugelmann 2006] explored three cached quantities; we choose binary visibility for three reasons: (1) binary is sufficient for shadow-ray decisions — the ray either hits or misses; (2) Bernoulli structure gives variance for free from μ alone (var = μ(1−μ)), requiring no separate variance estimator; (3) the (point, point) → {0,1} domain aligns naturally with ReSTIR's pairwise queries where each reservoir stores a specific source–target pair. Free-path distance [Kugelmann 2006, experiment 3] is a richer representation but requires a separate variance estimator and is not pursued here.

**Coupled variance adaptation.** The same Bernoulli variance var = μ(1−μ) drives two reinforcing mechanisms simultaneously: (1) RR survival probability p = clamp(var/τ, pmin, 1) governs the correction rate — how often shadow rays are traced; (2) the write-depth gate (Sec. 5.2) governs spatial resolution — whether fine-level cache entries are updated. High-variance regions trace more often *and* update fine levels; low-variance regions trace rarely *and* only update the coarsest level. This coupling is self-regulating: no per-scene tuning is needed because the variance signal adapts to local shadow structure automatically. The coupling only becomes possible with a multilevel cache — [Kugelmann 2006] had fixed resolution, so only the correction rate was variance-driven.

Self-regulating: low σ2 → aggressive RR → few traces. High σ2 → always trace → cache updates → σ2 drops. Lighting change → σ2 rises → traces reallocated. Pmin ≈ 0.05 ensures at least 5% of pixels always trace.

## 8.1 Firefly Mitigation

At Pmin=0.05, surviving samples are amplified up to 1/Pmin = 20×. Worst case: μ≈0, V=1, p=0.05 → V̂ = 0 + (1−0)/0.05 = 20. At shadow edges where μ≈0.5, fireflies are spatially correlated — adjacent pixels share similar psurvive, producing bright clusters that temporal denoisers integrate into persistent bright bands.

**Adaptive Pmin.** Scale the survival floor by shading contribution: pfloor = clamp(luminance(fs·Le·G) / firefly_budget, Pmin, 1). firefly_budget is the maximum tolerable absolute luminance (cd/m²) from a single amplified sample. Example: with firefly_budget = 10 and shading contribution luminance 50, pfloor = 1 — the ray is always traced, preventing a 1000-luminance firefly. A dim contribution of luminance 0.1 gets pfloor = 0.01 — aggressive RR is safe because even 100× amplification produces only luminance 10. Unbiased.

**Output clamp (biased safety net).** Clamp the amplified estimate: V̂ = clamp(V̂, 0, C). Introduces bias bounded by C × p per clamped sample. Equivalent to p → max(p, 1/C). Visually: slight darkening at penumbra edges vs. bright firefly bands.

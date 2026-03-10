# 8. Prediction with Correction

The core estimator, which we call *prediction-with-correction* following the naming in [Kugelmann 2006] (shorthand: CV+VRRR — Control Variate + Variance-driven Russian Roulette Residual), combines two standard Monte Carlo techniques: a control variate and Russian roulette on the residual. Substituting an estimate instead of zero on RR termination is common technique — implicit in the "go with the winners" family [Aldous and Vazirani 1994; Grassberger 2002] and formalized for rendering by Szécsi et al. [2003] and Szirmay-Kalos et al. [2005]. [Kugelmann 2006] arrived at the same math independently (thesis Sec. 3.4, "predictions with correction at random") but refined the **estimation source** — per-point cached predictions rather than a scene-global average — and the **variance signal use** — Bernoulli variance from μ alone drives RR survival probability as adaptive sampling (Sec. 3.4.1). The per-point cache is what makes the technique effective: a good spatial prediction gives near-zero residual variance, while a scene-global average helps little. The idea of using variance — not absolute light — to drive sampling rate was inspired by hints in Keller's lectures at Universität Ulm. We do not claim the CV+RR math as new. We apply prediction-with-correction to a multilevel cache where the same variance signal now also drives spatial resolution (Sec. 5), a coupling that was impossible at fixed resolution.

Analytic lighting (BRDF × Le × G) is always evaluated. Only the shadow ray is gated:

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

**Generality.** Prediction-with-correction converts any visibility estimate μ — whether from a spatial hash (this work), a neural network [Bokšanský and Meister 2025], temporal reprojection, or spatial neighbor polling — into an unbiased estimator. The technique is agnostic to the source of μ; cache quality affects only efficiency, never correctness.

**Why binary visibility.** [Kugelmann 2006] explored both visibility prediction and contribution prediction; we focus on binary visibility for three reasons: (1) binary is sufficient for shadow-ray decisions — the ray either hits or misses; (2) Bernoulli structure gives variance for free from μ alone (var = μ(1−μ)), requiring no separate variance estimator — an optimization not exploited in the original thesis; (3) the (point, point) → {0,1} domain aligns naturally with any pairwise visibility query — whether from ReSTIR reservoirs, instant radiosity VPLs, or classical next-event estimation.

**Variance as adaptive sampling.** Already in [Kugelmann 2006], the Bernoulli variance drove the RR survival probability — this is adaptive sampling: high-uncertainty regions trace more, low-uncertainty regions trace less. The variance signal is free (computed from μ alone) and self-correcting (tracing updates μ, which changes variance, which changes the trace rate). What we add is a second use of the same signal: the write-depth gate (Sec. 5) governs spatial resolution — whether fine-level cache entries are updated. High-variance regions trace more often *and* update fine levels; low-variance regions trace rarely *and* only update the coarsest level. This coupled adaptation is self-regulating and only becomes possible with a multilevel cache.

Self-regulating: low σ² → aggressive RR → few traces. High σ² → always trace → cache updates → σ² drops. Lighting change → σ² rises → traces reallocated. Pmin ≈ 0.05 ensures at least 5% of pixels always trace.

## 8.1 Firefly Mitigation

At Pmin=0.05, surviving samples are amplified up to 1/Pmin = 20×. Worst case: μ≈0, V=1, p=0.05 → V̂ = 0 + (1−0)/0.05 = 20. At shadow edges where μ≈0.5, fireflies are spatially correlated — adjacent pixels share similar psurvive, producing bright clusters that temporal denoisers integrate into persistent bright bands.

**Adaptive Pmin.** Scale the survival floor by shading contribution: pfloor = clamp(luminance(fs·Le·G) / firefly_budget, Pmin, 1). firefly_budget is the maximum tolerable absolute luminance (cd/m²) from a single amplified sample. Example: with firefly_budget = 10 and shading contribution luminance 50, pfloor = 1 — the ray is always traced, preventing a 1000-luminance firefly. A dim contribution of luminance 0.1 gets pfloor = 0.01 — aggressive RR is safe because even 100× amplification produces only luminance 10. Unbiased.

**Output clamp (biased safety net).** Clamp the amplified estimate: V̂ = clamp(V̂, 0, C). Introduces bias bounded by C × p per clamped sample. Equivalent to p → max(p, 1/C). Visually: slight darkening at penumbra edges vs. bright firefly bands.

# 8. Prediction with Correction

The core estimator, *prediction-with-correction*
(shorthand: CV+VRRR —
Control Variate + Variance-driven Russian Roulette Residual),
combines two standard Monte Carlo techniques:
a control variate and Russian roulette on the residual.
Substituting an estimate instead of zero on RR termination is common technique —
implicit in the "go with the winners" family
[Aldous and Vazirani 1994; Grassberger 2002].
Szécsi et al. [2003] formalized the non-zero termination estimate
for rendering (CV+RR, but with fixed RR probability);
Szirmay-Kalos et al. [2005] added variance-driven RR
via the "go with the winners" splitting/RR framework.
[Kugelmann 2006] refined the **estimation source** —
per-point cached predictions rather than a scene-global average —
and the **variance signal use** —
variance drives RR survival probability as adaptive sampling.
The per-point cache is what makes the technique effective:
a good spatial prediction gives near-zero residual variance,
while a scene-global average helps little.
We do not claim the CV+RR math as new.
We apply prediction-with-correction to a multilevel cache
where the same variance signal now also drives spatial resolution (Sec. 5),
a coupling that was impossible at fixed resolution.

Analytic lighting (BRDF × Le × G) is always evaluated.
Only the shadow ray is gated:

**Algorithm 3: Shading with Cached Visibility**
```
Input: hit, light
analytic <- brdf x Le x G
r <- lookup(hit.pos, light.pos)
if r = MISS then
  V <- trace(hit, light); insert(V)
  return analytic x V
p_s <- clamp(r.var / tau_var, P_MIN, 1)
if random() < p_s then
  V <- trace(hit, light); insert(V)
  return analytic x (r.mean + (V - r.mean) / p_s)
else
  return analytic x r.mean     // no trace, no insert
```

**Unbiasedness proof.**
The estimator V̂ equals μ + (V − μ)/p with probability p,
and μ with probability (1−p).
E[V̂] = p·(μ + (E[V]−μ)/p) + (1−p)·μ = E[V].
The residual variance is Var[V̂] = (1/p − 1)·Var[V − μ].
When μ = E[V], the residual is zero —
a perfect cache needs no correction rays.
Cache quality affects only efficiency (residual variance), never correctness.
Only traced values are inserted —
returning μ without tracing does not update the cache,
preventing positive feedback.

**Generality.**
Prediction-with-correction converts any visibility estimate μ —
whether from a spatial hash (this work),
a neural network [Bokšanský and Meister 2025],
temporal reprojection, or spatial neighbor polling —
into an unbiased estimator.
The technique is agnostic to the source of μ;
cache quality affects only efficiency, never correctness.

**Why binary visibility.**
We focus on binary visibility for three reasons:
(1) binary is sufficient for shadow-ray decisions —
the ray either hits or misses;
(2) Bernoulli structure gives variance for free from μ alone
(var = μ(1−μ)), requiring no separate accumulator;
(3) the (point, point) → {0,1} domain aligns naturally
with any pairwise visibility query —
whether from ReSTIR reservoirs, instant radiosity VPLs,
or classical next-event estimation.

**Variance as adaptive sampling.**
Variance drives the RR survival probability —
high-uncertainty regions trace more, low-uncertainty regions trace less.
By narrowing to binary visibility, we exploit Bernoulli structure:
var = μ(1−μ) is free from the mean alone, requiring no separate accumulator.
The signal is self-correcting
(tracing updates μ, which changes variance,
which changes the trace rate).
What we add beyond this is a second use of the same signal:
the write-depth gate (Sec. 5) governs spatial resolution —
each level's variance gates writes to the next finer level.
High-variance regions trace more often *and* cascade updates to fine levels;
low-variance regions trace rarely *and* stop propagation early.
This coupled adaptation is self-regulating
and only becomes possible with a multilevel cache.

**Sample-count-aware trust gate (`stderrThreshold`).**
The naked Bernoulli variance `μ(1−μ)` is the *plug-in* (Wald) variance of a
binomial proportion: well-behaved when the per-cell sample count `N` is
large, but ignoring `N` itself. A cell with `N = 1` and `V = 1` reports
`μ = 1`, `var = 0` — the gate trusts the cache absolutely after a single
observation. Our cells spend most of their time in this regime (small
`N`, μ near 0 or 1), and the symptom in early ladder runs was an
SPP-dependent `vt`: the optimal threshold drifted with the per-frame
sample count (`vt ≈ 0.10` at x4 SPP, `vt ≈ 0.001` at x16 on Sponza).
The fix folds `N` directly into the gate via the standard error of
the cell's μ estimate:

```
stderr = √(μ(1−μ) / N)        — standard error of the cached proportion
p_trust = stderr ≤ τ          — gate is "the estimate is precise enough"
```

A single ladder sweep (SPONZA_STDERR, 2026-05-06) found `τ = 0.10`
covers both x4 and x16 with one config: at low `N` (x4, cold cells)
the gate refuses trust safely (matches the strict `vt = 0.001` baseline);
at higher `N` (x16, mature cells) it trusts aggressively, recovering
the loose-`vt` regime (relMSE 2.5× better than `vt = 0.001`,
artifact-fraction `+0.04 pp`, negligible). A scene-matrix follow-up
(ALL_STDERR) confirmed Pareto-improvement across the full 7-scene
suite with no regressions, so `stderrThreshold = 0.10` replaces `vt`
as the canonical trust gate.

We tested two more theoretically-motivated alternatives in parallel.
The Wilson score interval [Wilson 1927; Brown et al. 2001] inverts
the score test rather than the Wald test, producing well-behaved
coverage at the boundaries and small `N`; in our regime it is
empirically equivalent to the stderr gate (no measurable leverage)
and we keep the simpler form. The Agresti–Coull "+2 successes,
+2 failures" shrinkage [Agresti and Coull 1998] is a closed-form
prior pulling cold-cell μ toward `0.5`; orthogonal to the gate (it
changes the *cached value*, not the *trust criterion*) and queued
as a separate refinement for the CV+RRR estimator's residual
behaviour in the `μ ∈ {0, 1}` corners.

**Analogy to ADRRS p_lim.**
In adjoint-driven RR/splitting [Vorba and Křivánek 2016],
the limiting survival probability p_lim sets a floor
below which paths are terminated —
importance controls the boundary between tracing and termination.
Our variance-driven write-depth gate is the spatial analogue:
σ² sets a ceiling on which hash levels receive updates,
so importance (here: uncertainty) controls the boundary
between fine and coarse resolution.
ADRRS couples one signal (adjoint importance)
to one decision (path continuation);
we couple one signal (Bernoulli variance)
to two decisions — correction rate *and* spatial resolution —
through the shared multilevel structure.
The contribution-weighted pfloor (Sec. 8.1)
closes the circle:
it is the direct shadow-ray counterpart of ADRRS's p_lim,
weighting survival by image-space importance
rather than adjoint transport importance.

Self-regulating:
low σ² → aggressive RR → few traces.
High σ² → always trace → cache updates → σ² drops.
Lighting change → σ² rises → traces reallocated.
Pmin ≈ 0.05 ensures at least 5% of pixels always trace.

## 8.1 Firefly Mitigation

At Pmin=0.05, surviving samples are amplified up to 1/Pmin = 20×.
Worst case:
μ≈0, V=1, p=0.05 → V̂ = 0 + (1−0)/0.05 = 20.
At shadow edges where μ≈0.5,
fireflies are spatially correlated —
adjacent pixels share similar psurvive,
producing bright clusters that temporal denoisers integrate
into persistent bright bands.

**Adaptive Pmin (contribution-weighted survival floor).**
Scale the survival floor by shading contribution:
pfloor = clamp(luminance(fs·Le·G) · max(μ, 1−μ) / firefly_budget, Pmin, 1).
The max(μ, 1−μ) term is the maximum possible residual magnitude:
the CV+RRR estimator returns μ + (V−μ)/p,
and since V ∈ {0,1} the worst-case correction is max(μ, 1−μ)/p.
Near-certain entries (μ≈0 or μ≈1) have small residuals
and tolerate aggressive RR;
uncertain entries (μ≈0.5) have larger residuals
and need higher pfloor.
This is the same factor that appears in Algorithm 4 (Sec. 10).
firefly_budget is the maximum tolerable absolute luminance (cd/m²)
from a single amplified sample.
Example:
with firefly_budget = 10 and shading contribution luminance 50 at μ=0.5,
effective contribution = 50 × 0.5 = 25,
pfloor = 1 — the ray is always traced,
preventing a 500-luminance firefly.
A dim contribution of luminance 0.1 at μ=0.9 gets
effective contribution = 0.1 × 0.9 = 0.09, pfloor ≈ 0.009 —
aggressive RR is safe because even 111× amplification
produces only luminance 10. Unbiased.

**Connection to zero-variance theory.**
This contribution-weighted floor is the shadow-ray analogue
of the weight window in adjoint-driven RR and splitting
[Vorba and Křivánek 2016]:
queries whose answer matters more to the final image
get higher survival probability.
In zero-variance random walk theory,
the optimal RR survival probability at a point
is proportional to the local importance
(the adjoint transport solution).
For a shadow ray,
the "importance" is the shading contribution luminance(fs·Le·G) —
exactly the quantity pfloor scales by.
The variance-driven base probability p_s = var/τ_var
handles cache uncertainty;
the contribution-weighted floor handles image importance.
Together they approximate the efficiency-optimal strategy
identified by Bolin and Meyer [1997]
and pursued for path continuation by EARS [Rath et al. 2022]:
allocate traces where (variance × importance) is high,
suppress where both are low.

**Output clamp (biased safety net).**
Clamp the amplified estimate: V̂ = clamp(V̂, 0, C).
Introduces bias bounded by C × p per clamped sample.
Equivalent to p → max(p, 1/C).
Visually:
slight darkening at penumbra edges vs. bright firefly bands.

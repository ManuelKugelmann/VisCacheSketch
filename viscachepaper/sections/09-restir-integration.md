# 9. ReSTIR Integration

The visibility cache is algorithm-agnostic: it reduces shadow-ray cost for any method that evaluates pairwise point-to-point visibility. The original thesis [Kugelmann 2006] applied it to instant radiosity; it works equally well with classical next-event estimation or photon mapping. ReSTIR [Bitterli et al. 2020; Ouyang et al. 2021] is not related work but a particularly good integration target — spatial reuse concentrates many pixels onto the same light or secondary hit, and a world-space cache amortizes their shared visibility queries automatically. We demonstrate three integration points, all using the same hash table.

## 9.1 Cache-Informed Light Selection

Replace V=1 in ReSTIR's target function p̂ with cached μ during initial candidate generation: p̂ = fs × Le × G × max(μ, μmin). The μmin floor (default 0.01) prevents permanent exclusion of visible lights with stale cache entries. Bokšanský and Meister [2025] independently apply the same visibility-weighted selection idea with a neural cache.

**Unbiasedness.** The cached μ appears only in the target function p̂ used for candidate selection, not in the final estimator. ReSTIR's 1/W normalization cancels p̂ — the selected light's contribution is divided by its selection probability, which includes μ. For this cancellation to hold, every light must have nonzero selection probability. The μmin floor enforces this: even a fully occluded light (true μ=0) retains at least 1% of its BRDF-weighted selection weight.

An exploration candidate (1/M of budget, where M is the number of initial light candidates per pixel, typically 32) uses uniform sampling and always traces its shadow ray — the ε-greedy strategy. Combined with μmin, permanent exclusion is impossible.

L0 suffices for candidate weighting. Occluded lights (μ≈0) are effectively removed from the candidate pool, improving hit rate from ~70% to ~95% in scenes with many occluded lights.

## 9.2 Post-Shading Shadow Ray

After ReSTIR selects a light, apply prediction-with-correction (Algorithm 3) on the final shadow ray. Decoupled from ReSTIR internals — this integration point works identically whether the visibility query comes from ReSTIR DI, instant radiosity, or classical next-event estimation. Saves ~88% of final shadow rays. Modest but zero risk.

## 9.3 ReSTIR GI Revalidation

The cache's strongest integration case. ReSTIR GI spatial reuse borrows neighbor paths and must verify visibility from the current shading point P to the neighbor's secondary hit Q. With k=5 spatial neighbors, unbiased revalidation costs 5 shadow rays per pixel — the main reason production systems use biased skip-revalidation.

Prediction-with-correction makes unbiased revalidation near-free: look up cached V(P, Q), apply contribution-weighted RR (Sec. 10). Expected traces drop from 5 to ~0.7 per pixel. This is where the cache's value is highest, because no screen-space alternative exists for arbitrary secondary hits — temporal reprojection and neighbor polling cannot help when Q is a world-space point unrelated to the current pixel's view.

Note that this integration is not specific to ReSTIR GI. Any path-reuse algorithm that needs to revalidate visibility to borrowed secondary hits would benefit identically.

| Insertion point | Rays saved | Unbiased? | Risk |
|---|---|---|---|
| In target (selection) | M candidates | If μ>0 | Feedback loop |
| Post-shading | ~88% of 1/px | Trivially | Minimal |
| GI revalidation | ~85% of k/px | Pred+corr | Cold on disocclusion |

> **Table 2.** Cache insertion points. All three work with the same hash table. The post-shading and revalidation points are algorithm-agnostic — they apply wherever a pairwise visibility query occurs.

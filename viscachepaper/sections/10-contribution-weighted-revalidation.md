# 10. Contribution-Weighted Revalidation

RR probability proportional to how much the revalidation residual *matters to the pixel*, not just visibility variance. Maximum possible residual for neighbor i: fs × Lo × G × max(μ, 1−μ).

With the cache, three regimes: μ≈1 (known visible, small residual → skip), μ≈0 (known occluded, small residual → skip), μ≈0.5 (uncertain → trace if bright). The cache collapses two of three cases. Without cache, μ=0.5 for all GI queries (no spatial neighbor poll exists for arbitrary secondary hits), degrading to contribution-only RR.

**Algorithm 4: Contribution-Weighted Revalidation**
```
for i <- 0 to K_NEIGHBORS do
  Q <- neighbor[i].secondary_hit
  mu <- lookup(my_pos, Q).mean
  bound <- f_s * Lo * G(my_pos, Q)
  residual <- bound * max(mu, 1-mu)
  p <- clamp(residual / threshold, P_MIN, 1)
  if random() < p then
    V <- trace(my_pos, Q); insert(my_pos, Q, V)
    V_est[i] <- mu + (V - mu) / p
  else
    V_est[i] <- mu
```

## 10.1 Path Sharing

ReSTIR spatial reuse concentrates selections: a good path gets selected by many pixels in the reuse radius. All need to revalidate visibility to the *same* Q from nearby shading points. At L0 quantization (43), nearby points hash to the same cell. The first pixel to trace populates the entry; subsequent pixels find it cached within the same frame.

With 50–100 pixels selecting the same path, they fall into ~3–5 L0 cells. Total traces: ~3–5 instead of ~50–100. This is the strongest architectural argument for L0's coarse resolution — it maximizes sharing across pixels that selected the same reused path.

| Method | Traces/px (k=5) | Visibility signal |
|---|---|---|
| Full revalidation | 5.0 | N/A |
| Contribution RR, no cache | ~1.5 | None |
| Contribution + cache | ~0.5–1.0 | Cached μ |

> **Table 3.** GI revalidation cost.

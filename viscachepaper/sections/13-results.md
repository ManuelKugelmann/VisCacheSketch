# 13. Results

All measurements at 1920×1080, 1 spp, RTX 4090, driver 560.x, DXR 1.1. Reference images: 4096 spp accumulation, same seed. MSE computed in linear RGB.

## 13.1 Test Scenes

| Scene | Triangles | Lights | Character |
|---|---|---|---|
| red | red | red | red |
| red | red | red | red |
| red | red | red | red |

> **Table 5.** Test scenes. Bistro is the primary benchmark; Sponza tests single-light coherence; Cornell Box verifies graceful degradation when the cache offers no spatial advantage.

## 13.2 Shadow-Ray Reduction

| Scene | Mode | DI final | GI reval. | Total rays/px |
|---|---|---|---|---|
| red | Baseline | red | red | red |
| red | Cache | red | red | red |
| red | Baseline | red | red | red |
| red | Cache | red | red | red |
| red | Cache | red | red | red |

## 13.3 Frame Time

| Component | Bistro (ms) | Sponza (ms) |
|---|---|---|
| Lookup | red | red |
| Insert + warp reduce | red | red |
| Decay (1/60 table) | red | red |
| Cache total overhead | red | red |
| Shadow rays saved | red | red |
| **Net frame time &#916;** | red | red |

## 13.4 Convergence

## 13.5 Ablation

| Configuration | Rays/px | MSE | ms |
|---|---|---|---|
| Full system (L0+L1+L2, var gate, warp red.) | red | red | red |
| − variance gate (always write all levels) | red | red | red |
| − maturity gate (always write, no SE check) | red | red | red |
| − warp reduction (per-thread atomics only) | red | red | red |
| − jitter-before-quantize (naive floor, §4.2) | red | red | red |
| L0 only (coarsest, 10 m cells) | red | red | red |
| L2 only (finest, 8 cm cells) | red | red | red |
| − firefly adaptive Pmin | red | red | red |
| No cache (baseline) | red | red | red |

## 13.6 Disocclusion Stress Test

**Graceful degradation.** Where cell resolution is too coarse, variance stays high, psurvive → 1, every ray traces. Rarely-selected lights → MISS → unconditional trace. Baseline cost, zero harm. The cache can never make things worse.

# VisCache Dev Log

Systematic ladder test results. One entry per ladder step.
Full plates and stats in each step's subfolder.

**Diagnostic plate layout** (4×3 grid):

| | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|
| **r1** | render | accum raysTraced | GT-err Δ vs vanilla | accum noise |
| **r2** | frame level | accum maturity | accum mean | accum variance |
| **r3** | accum coldmiss | frame qAHash | frame qBHash | frame probeSteps |

**r1c3 GT-error Δ** = OkLab(viscache, GT) − OkLab(vanilla\_xN, GT) at matched SPP. Continuous ramp anchored at viridis(0) = dark purple for Δ=0. Positive (VisCache degraded) walks the full **viridis** palette (purple → blue → green → yellow). Negative (VisCache denoised) fades from purple toward **black**. Darker-than-purple = better; brighter-than-purple = worse.

---

## [Step 00 — Vanilla Baselines](step00/STEP00.md)

Vanilla PathTracer (no VisCache) at x1 / x16 / x4096 SPP. Error and ground-truth reference for downstream steps.

| x1 SPP | x16 SPP | x4096 SPP |
|--------|---------|-----------|
| ![](step00/renders/CornellBox_1AreaLight_x1.png) | ![](step00/renders/CornellBox_1AreaLight_x16.png) | ![](step00/renders/CornellBox_1AreaLight_x4096.png) |

---

## [Step 01 — Cold-Start Tiling + Subframe Mitigation](step01/STEP01.md)

Single level, RR adaptive, coarse cells, mitigations (K footprint scale, L warmup write-only) ablated off.
Tiles dispatch in parallel within a frame: cells *straddling* tile boundaries see writes from neighbor tiles
and look "trusted", while cells fully inside a tile remain cold — RR skips the boundary cells, producing a
hatched tile pattern.

**Sweep**: 1×1 (artifact baseline), 2×2 (4 frames), 4×4 (16 frames). Subframe gate disperses per-pixel cell
writes across N² frames via Bayer interleaving — breaks the tile-local first-writer-wins pattern while
preserving warp coherence.

![](step01/plates/CornellBox_32PointLights_s_0_1_x1_sub1x1_512x512_pos_norm1__pos1_plate.png)

---

## [Step 02 — Initial Exploration](step02/STEP02.md)

Naive first pass: single level, uniform QUANT_SMALL, all 10 variants (pos_norm1 + pos_norm families), 4 scenes × x1 SPP.
Warmup-write-only ON, footprint OFF, no cascade.

![](step02/overview_rays_02.png)

Best variant: **pos_norm__dir1_dist1** — 39.6% rays traced (60.4% savings), 0.2% cold miss.

![](step02/plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos_norm__dir1_dist1_plate.png)

---

## [Step 03 — Adaptive RR + Quantization Sweep](step03/STEP03.md)

PRESET_MINIMAL + RR_ADAPTIVE. 4 quantization settings (qA→qD, posA 0.03→0.24 geometric) × 3 non-collapsed
norm-active B-side variants (pos, dir_dist1, dir_dist). 12 runs per scene.
Variant names: `pos_norm__<bside>__<qtag>`. Footprint still OFF.

> **Note (2026-04-14):** The original step 03 included a fourth variant `dir_nearest` (later renamed
> `dir_cleardist`) that collapsed the distance bin and stored a per-cell distance signal for a short-ray
> visibility override. The concept was useable under the surface-target assumption but the complexity
> (second per-slot buffer, eviction-reset coupling, bin-homogeneity caveats, firefly risk on mispredictions)
> outweighed the expected gain over proper `dir_dist` binning. Moved to future work — see paper
> conclusion, "Per-cell distance prior for collapsed-distance addressing". Step 03 reruns at 12 variants.

---

## [Step 04 — Norm1 vs Norm, SPP Convergence](step04/STEP04.md)

Fine B-side only × norm vs norm1, x1 and x16 SPP, 4 scenes each.
**Finding: norm vs norm1 makes no measurable difference** on convex geometry.
**Decision: proceed with `pos_norm` only** — uncollapsed normals handle thin-plate geometry
correctly; the CornellBox is too convex to expose the alias risk of `norm1`.
Best: **pos_norm__pos** at 23.4% mean rays x16 (76.6% savings).

![](step04/overview_rays_04.png)

![](step04/plates/CornellBox_1AreaLight_s_1_1_x16_512x512_pos_norm__pos_plate.png)

---

## [Step 05 — Footprint Scale Isolation](step05/STEP05.md)

Same config as step 04 (single level, norm-active subset, x1 and x16 SPP) with **FOOTPRINT_ON**.
Isolates the effect of the footprint-aware trust gate before the cascade is introduced.
Expected: distance-related maturity gradient from earlier steps collapses; near-camera cells wait longer
for spatial diversity, far cells mature quickly.

---

## [Step 06 — Multi-Level Cascade + Footprint](step06/STEP06.md)

Adds `LEVELS_MULTI` + auto-tuned cell sizes on top of step 05.
Cascade descent lets fine levels correct coarse-level early trust decisions.

---

## [Step 07 — Quality Threshold Sensitivity](step07/STEP07.md)

Same as step 06 with `QUALITY_DEFAULT` (bootThreshold=64, varThreshold=0.20 — higher than step 06's 8/0.10).
Isolates the effect of demanding more samples before trusting an entry.

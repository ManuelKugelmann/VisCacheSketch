# VisCache Dev Log

Systematic test ladder results. Each plate shows a 4x3 diagnostic grid per addressing variant.

**Plate layout:**

| | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|
| **r1** | render | accum raysTraced | accum error | accum noise |
| **r2** | frame level | accum maturity | accum mean | accum variance |
| **r3** | accum coldmiss | frame posAHash | frame posBHash | frame probeSteps |

---

## Ladder Step 00 — Vanilla Baselines

Renders vanilla PathTracer (no VisCache) at 1 SPP and 4096 SPP for error/noise comparison.

## Ladder Step 01 — Addressing Variants (fine cells)

**Config:** CornellBox_1AreaLight, 512x512, 1 warmup + 1 render frame, maxBounces=0, cellA=0.06

### pos\_\_pos (canonical pos x pos, cellA==cellB=0.06)
![pos__pos](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos__pos_plate.png)

### posA\_\_posB (asymmetric, cellB=0.12)
![posA__posB](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_posA__posB_plate.png)

### pos\_\_pos1 (position-only, cellB=10000)
![pos__pos1](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos__pos1_plate.png)

### pos\_\_dir1\_dist1 (dirdist, both collapsed)
![pos__dir1_dist1](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos__dir1_dist1_plate.png)

### pos\_\_dir\_dist1 (dirdist, angular=5deg, dist collapsed)
![pos__dir_dist1](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos__dir_dist1_plate.png)

### pos\_\_dir\_dist (dirdist, angular=5deg, dist=0.24)
![pos__dir_dist](plates/CornellBox_1AreaLight_s_1_1_x1_512x512_pos__dir_dist_plate.png)

## Ladder Step 02 — Coarser Cell Sizes

**Config:** CornellBox_1AreaLight, 512x512, 1 warmup + 1 render, x1 and x32 SPP

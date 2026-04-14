# Step 01 — Cold-Start Tiling + Subframe Mitigation

Single level, RR adaptive, coarse cells, with the two cold-start mitigations
(K footprint scale, L warmup write-only) **ablated off** — exposes the
tile-boundary artifact. Then sweeps a third mitigation (**M subframe gate**)
at 1×1 / 2×2 / 4×4 to show how Bayer interleaving breaks the pattern.
K/L are re-enabled by default in steps 02–07.

[← Dev Log overview](../DEVLOG.md)

## Why tiles appear

Within one frame all dispatch tiles run in parallel. A pixel queries the cache
**before** its own tile's writes have committed (atomics commit in
non-deterministic warp order; the lookup happens upstream of the write).

- Cells **fully inside** one tile: every querying pixel sees an empty entry → trace.
- Cells **straddling a tile boundary**: the neighbor tile already wrote → the
  pixel sees a "trusted" entry and lets RR skip the trace.

Result: a hatched pattern of false-trusted cells along tile borders. After
frame 1 every cell has writes, so the artifact disappears in a static scene —
but reappears on camera motion, lighting changes, or any cache reset.

## Mitigations

### K · `enableVisCacheFootprintScale`
Scales the trust threshold by `log2(cellPixels)`. Cells covering many screen
pixels demand more samples before being trusted. Ablated **off** here.

### L · `enableVisCacheWarmupWriteOnly` + `warmupFrames`
For the first N frames, force every ray to trace and skip RR; samples still
write to the cache. By the time RR turns on, the cache is broadly populated.
Ablated **off** here.

### M · `subframeN` — Bayer interleaving (this step's sweep)
`subframeN=N` partitions each N×N pixel block into N² subframes. On frame `f`,
pixels write only if their intra-block position matches slot `f mod N²`
(Bayer order). The cache query is unconditional — writes are gated, reads are not.

- **Advantage**: the tile-local first-writer-wins pattern is broken. Cells
  straddling tile borders are no longer the only early-trusted cells; any cell
  whose assigned subframe has already fired gets writes too. Warp coherence is
  preserved because active pixels stay spatially contiguous.
- **Cost**: a cell needs N² frames to accumulate one sample per slot, so
  warmup takes longer in wall-clock terms. At x1 SPP, 4×4 ≈ 16 frames to fill.

## Config

- Variant: `pos_norm1__pos1` (single endpoint, normal collapsed)
- `posACoarse = 0.5`, `posBCoarse = 1.0` (coarse — makes tile borders large)
- `enableVisCacheFootprintScale = False`, `enableVisCacheWarmupWriteOnly = False`
- Subframe sweep: 1×1 (1 frame), 2×2 (4 frames), 4×4 (16 frames)
- x1 SPP, 512×512, 4 CornellBox scenes

## Plates — CornellBox_32PointLights

### 1×1 (baseline — artifact visible)
![](plates/CornellBox_32PointLights_s_0_1_x1_sub1x1_512x512_pos_norm1__pos1_plate.png)

### 2×2 (4 frames — artifact partially dispersed)
![](plates/CornellBox_32PointLights_s_0_4_x1_sub2x2_512x512_pos_norm1__pos1_plate.png)

### 4×4 (16 frames — artifact gone)
![](plates/CornellBox_32PointLights_s_0_16_x1_sub4x4_512x512_pos_norm1__pos1_plate.png)

The hatched tile pattern in **maturity**, **mean**, **variance**, and
**level** panels thins progressively as N grows. The **render** panel's block
artifacts from false-trusted RR skips disappear once the cache fills uniformly.

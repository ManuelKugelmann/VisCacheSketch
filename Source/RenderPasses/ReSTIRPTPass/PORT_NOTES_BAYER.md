# Design note: Bayer-staged TracePass subframes (Task #22)

## Status

Falcor's PathTracer plugin already has Bayer infrastructure
(`Falcor/Source/RenderPasses/PathTracer/GeneratePaths.cs.slang`:
`kVisCacheBayerN`, `params.subframeIdx`, `subframeRemap`,
`isActiveSubframeSlot`). ReSTIRPTPass does NOT use it. This document
specifies how to port the pattern.

## Why

Per parallel agent (commit b863c24, RDI00 LADDERLOG):
**implicit Bayer-subframe-0 warmup is FREE — no separate pre-pass plugin
needed.**

Subframe 0 of every Bayer cycle lands on a cold-or-stale cache, so it
traces ~100% of its pixels explicitly (no cache-hit gate possible) and
writes those samples into the cell-pool/cell-reservoir. Subframes
1..N²−1 read the warmed cells and trace only at cache-miss positions.
This is the same pattern as RTXDI's `Presampling` pass that fills the
screen-tile pool, but achieved at zero per-pass cost since it's just
a temporal slot rotation.

## Where the existing infra lives

`Falcor/Source/RenderPasses/PathTracer/GeneratePaths.cs.slang`:
- `kVisCacheBayerN` — compile-time Bayer dimension (1 = full frame, no
  gate; 2 = 4-frame cycle of 2×2 Bayer; etc.).
- `params.subframeIdx` — current subframe within the Bayer cycle.
- `subframeRemap(reducedPixel, subframeIdx, N)` — maps a thread's
  reduced-pixel coordinate to its full-resolution pixel based on the
  Bayer slot for this subframe.
- `isActiveSubframeSlot(pixel, subframeIdx, N)` — predicate; pixels in
  inactive Bayer slots get spp=0 (no work).

`Falcor/Source/RenderPasses/PathTracer/Params.slang:91`:
`uint frameCount` — "Logical frame index (shared across subframes of one
Bayer cycle)" — the cell-pool is keyed by frameCount, not subframeIdx,
so within one Bayer cycle the cells persist across subframes.

## Where to insert (PT side)

`Source/RenderPasses/ReSTIRPTPass/TracePass.cs.slang` — the equivalent of
PathTracer's GeneratePaths. Currently traces every pixel every frame.

Modification: add a compile-time `RESTIRPT_BAYER_N` define (default 1 for
no-op) and a `restirptSubframeIdx` cbuffer field. Mirror the
`isActiveSubframeSlot` gate at thread entry; inactive threads early-exit
(no path generation, no reservoir write).

Host side: `ReSTIRPTPass.cpp::execute()` increments `restirptSubframeIdx`
each frame, wrapping at `RESTIRPT_BAYER_N²`. The cell-pool's per-iter
`clearUAV` should be gated on `restirptSubframeIdx == 0` (only clear at
start of a new Bayer cycle, NOT every subframe).

## Composition with R-axis

Bayer staging only matters for variants that read the cell-pool
(modes 1, 2). For mode 0 (R2d, no cell pool) Bayer is a pure cost (skips
samples without amortizing them anywhere).

| variant | Bayer benefit |
|---|---|
| R2d (mode 0) | NEGATIVE — skipped pixels never get sampled within a Bayer cycle, just lower effective SPP |
| R2dR3d (mode 1) | POSITIVE — subframe 0 fills cells, 1+ read from pixel fallback (cell or pixel always available) |
| R3d (mode 2) | POSITIVE — subframe 0 fills cells, 1+ skip-on-miss (drives cell-coverage discipline) |

## Composition with ReSTIR iters per frame

ReSTIR-PT already has multiple iterations per frame (`samplesPerPixel`
maps to `numPasses`). Bayer adds an ORTHOGONAL temporal axis:
- Per-frame iters: spatial reuse within the same Bayer slot.
- Per-Bayer-cycle subframes: covers different pixel patterns,
  amortizes cell fill.

For a typical setup (samplesPerPixel=1, RESTIRPT_BAYER_N=2 → 4-frame
cycle), each pixel fires every 4 frames. Effective SPP across the cycle
is 1; per-frame compute drops 4×.

## Estimated effort

- Bayer-aware TracePass dispatcher: 1 day (mirror GeneratePaths gate).
- frameCount/subframeIdx wiring in `ReSTIRPTPass.cpp`: 0.5 day.
- Conditional clearUAV (only on subframe 0): 0.5 day.
- Validation: 1 day (RPT_ZOO ladder with `RESTIRPT_BAYER_N=2` toggle).

Total: ~3 days for a working Bayer MVP.

## Why we haven't implemented

ReSTIRPTPass's existing `samplesPerPixel × numPasses` per-frame multi-iter
already amortizes cell fill within a single frame. Bayer subframes would
only matter when extending across MULTIPLE frames (e.g. SPP=1 with cell
pool persisting across frames — currently NOT how the pass operates;
clearUAV is per-frame).

The headline R3d firefly-cleanup win on Bistro/Sponza is achieved without
Bayer; adding it would be a perf-only optimization (skip ~75% of pixel
work per frame at N=2) without changing the quality story.

Implement when:
- Stage F (Falcor 8 native PathTracer integration, Task #11) lands and
  the PathTracer's existing Bayer infra naturally extends into the
  reservoir reuse passes.
- A perf-constrained scenario surfaces where ReSTIR-PT's full per-frame
  cost is the bottleneck and SPP can be amortized over multiple frames.

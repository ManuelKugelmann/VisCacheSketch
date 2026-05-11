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
each frame, wrapping at `RESTIRPT_BAYER_N²`.

**clearUAV substrate (unblocked 2026-05-11 by frame-CAS refactor).** The
per-iter `clearUAV(pathReservoirCellPool)` at `ReSTIRPTPass.cpp:664` is
now gated on `restirptCellPoolFrameCAS == 0u`. When FLAG=1, the clear is
skipped entirely; the per-slot frameStamp lock + ready publish
(`PathReservoirCellPool.slang::prCellSlotClaimFrameCAS`) handles stale-
data rejection at the reader. **This removes the historical blocker on
cross-frame cell persistence.**

The remaining piece for Bayer is a one-line change at the reader: relax
the freshness gate from strict `frameStamp == currentFrame` to a windowed
`currentFrame - frameStamp < BAYER_N²`. Writer protocol unchanged
(InterlockedMax still elects one writer per frame); readers accept any
slot whose claim landed within the last BAYER_N² frames. Cells written
on subframe 0 stay readable through subframes 1..BAYER_N²-1.

Older note (pre-frame-CAS) recorded that the per-iter clear was the only
safe refresh strategy. That's no longer true — frame-CAS is the cleaner
substrate, and the parallel-agent-suggested "FREE warmup on subframe 0"
pattern now composes naturally.

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

## Status update 2026-05-11 — substrate now in place

Frame-CAS refactor (`restirptCellPoolFrameCAS=1`) removed the per-iter
clearUAV that previously gated cross-frame persistence. The remaining
work for Bayer-staged subframes is:

1. Add a `RESTIRPT_BAYER_N` compile-time define + `restirptSubframeIdx`
   cbuffer field.
2. Mirror `isActiveSubframeSlot` gate in `TracePass.cs.slang` (skip
   inactive Bayer slots).
3. Relax the reader's freshness gate in
   `prCellPoolReadCascadeFrameCAS` from `frameStamp == currentFrame`
   to `currentFrame - frameStamp < BAYER_N²`.
4. Host: increment `restirptSubframeIdx` each frame, wrap at BAYER_N².

Estimated total: ~1 day (was ~3 days when clearUAV refactor was
required). All four steps are independent of the Falcor 8 PathTracer
integration (Task #11), so this can land standalone.

## Why we still haven't implemented

The headline R3d firefly-cleanup win on Bistro/Sponza is achieved without
Bayer; adding it would be a perf-only optimization (skip ~75% of pixel
work per frame at N=2) without changing the quality story. ReSTIRPTPass's
existing `samplesPerPixel × numPasses` per-frame multi-iter already
amortizes cell fill within a single frame.

Implement when:
- A perf-constrained scenario surfaces where ReSTIR-PT's full per-frame
  cost is the bottleneck and SPP can be amortized over multiple frames.
- The dynamic-scene regime is reached and we want to test cold-cell
  amortization across the Bayer cycle.

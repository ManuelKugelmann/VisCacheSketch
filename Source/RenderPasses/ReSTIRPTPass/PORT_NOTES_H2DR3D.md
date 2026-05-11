# Design note: H2dR3d (mode 3) for ReSTIR-PT (Task #20)

## Status

`restirptAddrMode == 3` is enumerated in `Params.slang` but **not
implemented**. `run_baseline_ReSTIRPT_variant` raises NotImplementedError on
mode=3. This document specifies why the obvious implementation doesn't work
on PT side and what a real implementation needs.

## What it should be (per parallel agent's DI-side clarification, 13fc09c)

H2d is a **graceful-fallback layer for sparse cell coverage**, NOT a
per-pixel temporal accumulator:
- per-pixel buffer = "my last working shading sample"
- read path: try cell-pool first; on empty/disocclusion/cold, fall back to
  per-pixel history slot
- write path: every successful shade updates the per-pixel slot

Under the canonical regime (frame-accumulation x4 with post-warmup
steady-state) cells are well-covered everywhere, so H2d's fallback path is
rarely exercised → H2dR3d ≡ R2dR3d. The relevant test is the cold/sparse
regime: SPP=1 (no warmup), fast camera motion, disocclusion edges,
glancing-angle pixels.

## Why naive impl fails on PT side

Two compounding problems:

**1. Ping-pong buffer semantics.** `outputReservoirs` is swapped from
`temporalReservoirs` each frame (Falcor's standard ping-pong). If mode 3
NEVER writes outputReservoirs, then frame N+1's outputReservoirs =
frame N's outputReservoirs = ... = the initial cleared state. The
fallback on cell-miss reads garbage forever; the pixel buffer never
stabilizes.

**2. TemporalReuse writes outputReservoirs unconditionally.**
`TemporalReuse.cs.slang:316` does `outputReservoirs[centralOffset] =
dstReservoir` every frame. Even if TracePass mode 3 skips the per-pixel
write, TemporalReuse will read garbage (from cleared outputReservoirs)
as central, merge with previous frame's temporal, and write garbage
back. Without ALSO gating TemporalReuse's read+write on mode 3, any
TracePass-side gating is meaningless.

Reference: `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang:2172-2173`
write-site dispatch + `lookupCentralReservoir:283` read-site dispatch +
`TemporalReuse.cs.slang:99,169,316` outputReservoirs read/merge/write.

## Three viable design options

### (a) Conditional pixel write on cell-claim outcome

Pixel buffer is updated ONLY when cell-write SUCCEEDED:
- Cell-claim succeeds → write pixel = current reservoir (cell-validated copy
  for fallback when this slot's cell gets recycled by another pixel later).
- Cell-claim fails → SKIP pixel write (preserves whatever stable data was
  there from a prior frame's successful claim).

Requires: surfacing `prCellSlotClaim`'s outcome from `writeCentralReservoir`
back to the TracePass write site. Touch points: `PathTracer.slang:2172-2173`
(per-pixel write) + `writeCentralReservoir:280-298` (currently void; needs
to return claim-success bool).

**ALSO requires gating TemporalReuse:** the unconditional write at
`TemporalReuse.cs.slang:316` will overwrite the carefully-preserved pixel
data with merged-with-garbage results. Two sub-options here:
- (a.i) Gate TemporalReuse write on mode != 3, AND make its read of
  outputReservoirs[central] read-from-cell-pool when mode == 3.
- (a.ii) Disable TemporalReuse entirely in mode 3 (lose temporal
  resampling). Simpler but kneecaps the variant's quality.

Effort: 1-2 days. Couples TracePass to cell-pool's claim outcome AND
requires TemporalReuse touch point.

### (b) Slim per-pixel sample buffer (16-32 B/pixel)

Allocate a separate slim buffer storing just enough for "fallback shading
sample" — the resolved radiance contribution + light pdf, NOT a full
PathReservoir. ~16 B/pixel = 4 MB for 1024×1024.

When cell read returns empty, the slim buffer provides a stable contribution
that the path can use directly (skipping the GRIS resampling step).

Requires: new buffer allocation in `ReSTIRPTPass.cpp` similar to
`mpPathReservoirCellPool`, slang struct + binding, fallback logic at
`lookupCentralReservoir`. The slim sample composes naturally with simple
shading but doesn't reconstruct full path information needed for some
GRIS shifts.

Effort: ~3 days. Most architecturally faithful to the DI-side H2d
semantics.

### (c) One-shot init pixel buffer (frozen-fallback)

Pixel buffer is written ONCE per scene-load with a synthetic "valid sample"
value (e.g. local diffuse contribution from primary hit). After init, it's
never updated — pure last-known-good fallback.

Requires: new init compute pass that runs ONCE on scene change, generating
`outputReservoirs[pixel]` with a low-quality but valid PathReservoir per
pixel. After that, mode 3 = mode 2 reads (cell-first) with frozen pixel
fallback.

Effort: ~1 day. Simplest semantically; pixel data is permanently stale
which limits its value in dynamic regimes.

## Recommendation

If you implement, start with **option (a)** — minimum new infrastructure,
preserves the existing buffer layout, naturally tracks cell-claim
outcomes. Validate against the SPP=1 cold-cell regime where H2d should
matter most (per parallel agent's "x1 cold-cell test", commit b5de28b).

## Why we haven't implemented

Per parallel agent's DI-side finding (commit 13fc09c, RDI00 LADDERLOG):
- Canonical config has well-covered cells; H2d fallback path rarely fires.
- DI side implemented option (a)-equivalent shortcut, found H2dR3dP3d ≡
  R2dR3dP3d in canonical regime (no measurable win).
- Defer to dynamic-scene stage where camera motion creates persistent cold
  cells.

The current PT-side R3d already achieves a substantial win over R2d on
production scenes (Sponza -46pp at SPP=16) via the cell-pool's
firefly-suppression side-effect — H2dR3d wouldn't add to that headline.
Implement only when a specific cold-cell regression appears that R2dR3d
fallback can't handle.

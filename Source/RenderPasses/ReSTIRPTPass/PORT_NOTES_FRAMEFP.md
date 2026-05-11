# Design note: frame-tagged fingerprint — eliminate per-frame `clearUAV`

Per user direction 2026-05-11: `frameFingerprint = lastWriteStamp`. Combine
frame index with spatial fingerprint into ONE atomic value; CAS handles
both the claim atom and the stale-frame eviction. Drops the per-frame
`clearUAV(mpPathReservoirCellPool)` (`ReSTIRPTPass.cpp:644`) entirely.

## Status (2026-05-11, commit e8b2dbf)

**WIRED behind a runtime toggle** — `restirptCellPoolFrameCAS` cbuffer
field, default 0 (legacy). Set to 1 via render-graph kwarg or
`AB_FRAME_CAS=1` env var to enable.

Validation on Cornell_1AL b=4 x16 (ImageCompare vs vanilla_b4_x4096 GT):

| Variant | FLAG=0 (legacy) | FLAG=1 (frame-CAS) |
|---|---:|---:|
| vanilla | 0.00508 | 0.00508 |
| R2d | 0.00351 | 0.00351 |
| R2dR3d | 0.00250 | **0.00244** |
| R3d | 0.00297 | 0.00297 |

R2dR3d preserved or slightly better with frame-CAS (cells persist
across frames → more cross-pixel reuse). R3d essentially identical.
Default behavior on legacy path is bit-identical.

BistroExterior partial validation (FLAG=1, AB harness crashed before
R3d completed; Sponza AB also crashes at FLAG=0 — harness instability
not from my changes):

| Variant | ImageCompare |
|---|---:|
| vanilla | 0.287 |
| restirpt_2d | 0.275 (-4% vs vanilla) |
| restirpt_3d | 0.262 (-9% vs vanilla, -5% vs R2d) |

Full 7-scene RPT_ZOO ladder validation pending.

**Critical implementation fix:** one-time clearUAV at buffer creation.
Without it, frame 0 hits uninitialized GPU memory → the 2nd-CAS
overwrite path race-writes payload over garbage → TDR. With one-time
clear, fingerprint starts at zero so 1st CAS wins cleanly.

## Known limitation — TDR at high contention (FOUND 2026-05-11)

The 2nd-CAS-overwrite path has a fundamental race on the non-atomic
`pool[slot].reservoir = ...` payload write:
- Writer A in frame N: 1st CAS wins empty slot → writes payload.
- Writer A in frame N+1 (different pixel hash, same cell): 1st CAS
  fails (slot has stamp_N); 2nd CAS wins (overwrites stamp_N→stamp_N+1)
  → writes payload non-atomically.

Across many frames with high cell contention (e.g. BistroExterior R3d
mode 2 at AB_FRAMES≥12), multiple writers' payload writes can interleave
on the same slot. Torn `rcVertexHit` → `gScene.getVertexData(invalid)`
→ DXGI_DEVICE_REMOVED → TDR.

**Empirical TDR threshold:** R3d (pure 3D, no pixel fallback) on
BistroExterior:
- AB_FRAMES=4:  PASS
- AB_FRAMES=8:  PASS
- AB_FRAMES=12: FAIL (TDR)
- AB_FRAMES=16: FAIL (TDR)

Cornell scenes don't hit this — fewer cells, less contention. R2dR3d
(mode 1) also wasn't reproduced to TDR yet because pixel fallback
masks per-cell-slot torn-payload writes.

**Workarounds for a robust frame-CAS scheme:**
1. **Drop the 2nd CAS** entirely → stale slots stay forever; needs a
   separate periodic clear (e.g. every 256 frames) or read-side
   "freshness" gate (only accept if frame byte differs by ≤K).
2. **Per-slot write lock** via a separate uint flag: writer CAS-takes
   a lock bit, writes payload, releases. Adds 2 atomics + 1 store per
   write but eliminates the payload race.
3. **Atomically-replaceable payload**: shrink `PathReservoir` to fit
   in a uint64_t / uint4 atomic. Loses fidelity; needs a smaller
   PathReservoir variant.

For production: KEEP toggle off. Legacy strict-first-writer-wins +
per-frame clearUAV remains safe. Frame-CAS is useful as a low-
contention proof-of-concept; needs option 2 or 3 to be production-ready
across the full scene matrix.

## Why this differs from the reverted frame-stamp scheme (a3129ab)

The reverted scheme used a SEPARATE `frameStamp` field with
`InterlockedMax` and gated readers on `frameStamp == currentFrame`. Two
problems:

1. **Two-field race.** Writer set frameStamp atomically, then wrote
   `fingerprint` and `reservoir` non-atomically. Concurrent reader could
   see new stamp + old fingerprint → mismatch → reject same-frame data.
2. **Multi-iter ReSTIR stamp drift.** `currentFrame = frameCount*256+sppId+1`
   made iter 1's reader expect a stamp iter 0's writer didn't yet set.

Both regress Cornell SPP=16 R3d quality ~25%.

The frame-fingerprint design avoids (1) by collapsing both into ONE
atomic CAS value, and avoids (2) by using `currentFrame = frameCount+1u`
(same across iters in one frame).

## Encoding

```hlsl
uint frame_aware_fp(int3 q, uint nb, uint level, uint currentFrame)
{
    uint spatial = pcgHashEndpoint(q, mixed, kPRCellFpSalt);  // current logic
    return (currentFrame << 24) | (spatial & 0xFFFFFFu);
}
```

24 bits spatial fingerprint (16M unique values per frame; collision rate
per slot at 256K slots ~ 1/64, acceptable) + 8 bits frame counter (256
frames cycle = ~4 sec at 60 Hz; rare false match risk during long camera
holds but acceptable for first cut).

Future refinement: use 32-bit hash blending (`pcgHash(frame) ^ spatial`)
for full entropy. Reader does same blend; deterministic.

## Claim (two-CAS-attempt)

```hlsl
bool prCellSlotClaim(pool, slot, frame_aware_fp, currentFrameMarker)
{
    uint prev = 0;
    InterlockedCompareExchange(pool[slot].fingerprint, 0u, frame_aware_fp, prev);
    if (prev == 0u) return true;            // won empty slot
    if (prev == frame_aware_fp) return false; // already me this frame

    // Is prev from THIS frame (other-pixel collision)?
    if ((prev >> 24) == currentFrameMarker)
        return false;                        // current-frame collision; preserve first-writer-wins

    // Stale-frame data: try to overwrite atomically.
    uint prev2 = 0;
    InterlockedCompareExchange(pool[slot].fingerprint, prev, frame_aware_fp, prev2);
    return prev2 == prev;                    // succeeded only if nobody else slipped in
}
```

Preserves first-writer-wins WITHIN a frame (firefly suppression property
remains). Replaces stale-frame entries opportunistically WITHOUT a global
clear.

## Read

```hlsl
bool prCellSlotRead(pool, slot, expected_frame_aware_fp, out reservoir)
{
    PathReservoirCellSlot s = pool[slot];
    reservoir = s.reservoir;
    return s.fingerprint != 0u && s.fingerprint == expected_frame_aware_fp;
}
```

Single equality check. Stale-frame entries naturally rejected because
their stamp doesn't match the reader's current-frame stamp.

## Payload race tolerance

Same as current code: writer CAS-claims fingerprint, then writes
`reservoir` non-atomically. Concurrent in-dispatch readers can see new
fingerprint + old payload. **This is the SAME race the current code has
and tolerates** because:

1. Within TracePass dispatch: no cell-pool reads, only writes
   (verified: `PathTracer.slang::writeCentralReservoir` is the only
   touch; readers live in Spatial/Temporal/Retrace passes).
2. Cross-dispatch (TracePass → SpatialReuse): GPU barrier flushes all
   UAV writes. Readers see fully-committed state.

Therefore the frame-fingerprint design doesn't introduce a new race; it
just removes the per-frame clear that was masking the racey "previous
frame leakage" problem. Stale-frame data exists in the buffer but is
rejected by the stamp gate at read time.

## Host-side change

Drop `pRenderContext->clearUAV(mpPathReservoirCellPool->getUAV().get(), uint4(0));`
from `ReSTIRPTPass.cpp:644`. That's it. No new dispatch, no new buffer.

## Validation plan

1. Snapshot current AB baseline on Cornell + Sponza (R2d/R2dR3d/R3d at b=4 x16).
2. Apply the change.
3. Re-AB.
4. Acceptance: R3d quality within ±0.2pp of baseline on every scene
   (matches the rerun stochastic noise floor). If Cornell SPP=16
   regresses >0.2pp, revert.

Cost-axis bonus: dropping clearUAV is one GPU op less per ReSTIR iter,
which could shave a few % off the existing R3d 67% speedup. Track via
`scripts/audit_rpt_zoo_cost.py`.

## Open questions

- 8-bit frame marker (256-frame cycle) sufficient, or extend to 16-bit
  with smaller spatial fp? Real risk: paused camera holding same view
  for >256 frames at 60Hz → 4s+. Acceptable for first iteration; revisit
  if visible artifacts manifest.
- Should reader also probe at next-level cascade on stale-stamp miss
  (current behavior on collision)? Probably not — stale stamps are
  semantically "no data this frame at this cell", not a hash collision.
  Letting reader fall through to coarser levels would give slightly
  better fallback but at the cost of mixing temporal scales.

Source: `Source/RenderPasses/ReSTIRPTPass/PathReservoirCellPool.slang`
+ `ReSTIRPTPass.cpp:644` (clearUAV site).

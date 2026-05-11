# Design note: frame-CAS for cell-pool — eliminate per-frame `clearUAV`

Per user direction 2026-05-11: **frame fingerprint is ONLY for CAS; spatial
fingerprint is ONLY for collisions; ready flag is a separate field.** Three
single-purpose words in the slot header, no bit-mixing. Drops the per-frame
`clearUAV(mpPathReservoirCellPool)` (`ReSTIRPTPass.cpp:644`) when the flag
is on.

## Status (2026-05-11)

**WIRED behind a runtime toggle** — `restirptCellPoolFrameCAS` cbuffer
field, default 0 (legacy). Set to 1 via render-graph kwarg or
`AB_FRAME_CAS=1` env var to enable.

### Per-iter currentFrame encoding (refinement landed 2026-05-11)

Per user "frame_id = frame + subframe" directive, the writer/reader now
compute `currentFrame = (params.frameCount * 256u) + uint(gSppId) + 1u`.
Each ReSTIR iter dispatches with its own freshness stamp, restoring
legacy per-iter-clear semantics — but without the clearUAV cost, and
without inter-iter firefly amplification.

Validation across 4 scenes at HEAD build (R3d b=4 x16):

| scene | per-iter Δ vs single-stamp | per-iter Δ vs vanilla GT | legacy Δ vs vanilla GT |
|---|---:|---:|---:|
| Cornell_1AL | 0.000217 | (n/a) | (n/a) |
| Sponza | 0.000412 | (n/a) | (n/a) |
| BistroInterior | 0.216 | **0.259** | **0.466** |
| BistroExterior | (n/a) | **0.148** | (n/a) |

BistroInterior stats (mean / median / fireflies above 100 nits):

| | mean | median | fireflies |
|---|---:|---:|---:|
| GT (vanilla x256) | 0.74 | 0.00 | 14 |
| FLAG=1 per-iter | 0.52 | 0.18 | 11 |
| FLAG=0 legacy | 2.41 | 0.93 | 527 |

Frame-CAS per-iter lands within 30% of GT mean and 3 fireflies of GT
count. Legacy clearUAV path drifts 3.3× over GT mean and 38× over GT
firefly count — a regression introduced by mid-session WSCellPool
struct expansion in the parallel agent's branch. Frame-CAS is unaffected
because per-iter freshness gates reject stale-frame data from prior
frames so cell-pool cross-iter contamination cannot accumulate.

### BistroExterior R3d stress test (TDR fix verified)

Previously TDR'd at x12 with the bit-packed-fingerprint variant:

| AB_FRAMES | FLAG=1 result |
|---:|:---|
| 16 | PASS |
| 32 | PASS |

No TDRs, no torn-payload reads. The InterlockedMax-based first-writer-
per-frame protocol elects exactly one writer per (slot, frame) — the
multi-writer payload race is gone.

## Slot layout

```hlsl
struct PathReservoirCellSlot
{
    uint           fingerprint;     // spatial hash (0 = empty sentinel)
    uint           frameStamp;      // frame-CAS lock: latest claimer's currentFrame
    uint           ready;           // publication flag: latest committer's currentFrame
    uint           _pad;
    PathReservoir  reservoir;
};
```

Each header word has a single purpose. No bit packing.

## Writer protocol

```hlsl
// 1. Claim via monotonic max: I'm the first-writer-this-frame iff the
//    stamp advanced under me.
uint prev = 0;
InterlockedMax(pool[slot].frameStamp, currentFrame, prev);
if (prev >= currentFrame) skip-this-level;     // another writer got it

// 2. Non-atomic payload write — no other writer touches this slot this frame.
pool[slot].fingerprint = spatialFp;
pool[slot].reservoir   = payload;

// 3. Atomic publish — reader gates on ready==currentFrame.
InterlockedExchange(pool[slot].ready, currentFrame, _);
```

Why `InterlockedMax`:
- Monotonic — an older-frame stamp can never overwrite a newer one.
- The single Max atomic absorbs both the empty-slot AND stale-slot cases.
  No 2nd-CAS-overwrite path → no race between writer-A's payload write and
  writer-B's stale-slot reclamation.
- "First-writer-this-frame" is naturally elected: only one wave observes
  `prev < currentFrame` since `Max` returns the pre-update value.

## Reader protocol

```hlsl
PathReservoirCellSlot s = pool[slot];
if (s.ready       == currentFrame &&    // payload write is complete
    s.frameStamp  == currentFrame &&    // slot was claimed by some writer this frame
    s.fingerprint == expectedSpatial)   // writer was at MY cell, not a collision
{
    consume(s.reservoir);
}
```

Three independent gates:
- **`ready == currentFrame`** rejects mid-write state (frameStamp updated
  but payload still being written).
- **`frameStamp == currentFrame`** rejects stale-frame data.
- **`fingerprint == expectedSpatial`** rejects same-frame cross-cell hash
  collisions.

## Why this works (vs the reverted/bit-packed attempts)

| Attempt | What failed |
|---|---|
| Original `clearUAV` legacy | Works, but costs a clear every frame. |
| Bit-packed `(frame<<24)|(spatial<<1)|ready` in fingerprint | Mixed concerns. Reader/writer had to decode bits. 2nd-CAS-overwrite raced non-atomic payload across frames → TDR at AB_FRAMES≥12 on BistroExt. |
| Separate frameStamp + InterlockedMax (current) | Three single-purpose fields. One winner per frame elected by Max monotonicity. No 2nd-CAS path → no race. |

Per cell-pool fundamentally: with only ONE non-atomic payload writer per
slot per frame, there is nothing to interleave. Cross-frame writes happen
in different frames separated by the inter-pass GPU barrier, which flushes
all UAV writes — so frame N+1's writer always observes the fully-committed
frame N state.

## Host-side change

When the toggle is on, drop
`pRenderContext->clearUAV(mpPathReservoirCellPool->getUAV().get(), uint4(0));`
from `ReSTIRPTPass.cpp:644`. The slot's frameStamp naturally invalidates
stale data: at iter K of frame N the reader checks
`frameStamp == N*256+K+1` and rejects any slot left over from prior iters
or prior frames.

One-time clearUAV at buffer creation still required — initial frameStamp=0
must be < currentFrame for the first iter's InterlockedMax to elect a
winner.

## currentFrame encoding

```hlsl
uint currentFrame = (params.frameCount * 256u) + uint(gSppId) + 1u;
```

- `frameCount * 256u` shifts the per-frame ID by 8 bits.
- `gSppId` is the ReSTIR iter index within a frame (0..numPasses-1).
- `+ 1u` keeps `currentFrame > 0` so the empty-slot stamp (0) is always
  smaller than any valid stamp.

Each iter dispatches with its own currentFrame, so iter K's reader gates
strictly reject iter K-1's writes. Result: per-iter freshness like legacy
clearUAV, without the clear's GPU cost and without inter-iter firefly
amplification.

256 iters per frame fits comfortably above any practical
`samplesPerPixel × numPasses`. Wrap at `frameCount = 2^24 = 16M` frames
(~3 days at 60 Hz). If wrap matters someday, switch to 64-bit stamps or
modulo at `frameCount`.

## Cost-axis note

Drops one clearUAV per ReSTIR iteration. Negligible on top of the existing
R3d 67% speedup. The new write protocol adds:
- 1 InterlockedMax (was 1 CompareExchange in legacy strict-first-writer-wins)
- 1 InterlockedExchange for publish (was 0 in legacy)

Reader: 1 extra equality check (`ready == currentFrame`). Negligible
compared to the structured-buffer load.

## What's no longer needed (vs prior design)

- Bit packing of frame + spatial + ready into one uint.
- 2-CAS-attempt claim path (with stale-frame overwrite).
- Per-slot writeLock field (briefly attempted as workaround c).
- `prCellFrameAwareFingerprint` encoding function — deleted.

## Open question (deferred)

The 32-bit `frameStamp` wraps after ~4 billion frames (~year+ at 60 Hz) —
not a real concern but worth noting. If wrap-around ever matters,
`InterlockedMax` semantics break (a smaller frameStamp could be "newer"
post-wrap). Could be mitigated by `frameStamp = frameCount % 0x40000000`
to keep the upper 2 bits as flag space, OR by periodic clearUAV every
2^31 frames.

Source: `Source/RenderPasses/ReSTIRPTPass/PathReservoirCellPool.slang`
+ `ReSTIRPTPass.cpp` (clearUAV gate site).

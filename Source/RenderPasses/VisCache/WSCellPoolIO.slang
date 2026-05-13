/***************************************************************************
 * WSCellPoolIO.slang
 *
 * §9.4 World-space ReSTIR DI — cell-pool buffer + load/insert helpers.
 *
 * Pool keyed by the same WSCellAddress as the single-slot reservoir
 * (gWSReservoirs). Lives in its own buffer so the existing read/write
 * paths to the single-slot reservoir keep working unchanged.
 *
 * Insert policy (RTXDI-tile semantics):
 *   - Cell located via fp-keyed double-hash probe (mirrors vhfFindSlot).
 *   - Within a cell, every writer picks a uniform random slot in [0, N)
 *     and overwrites it — last-writer-wins per slot. Slots are recycled,
 *     not filled-then-overflowed. ReSTIR is sample-loss-tolerant; the
 *     reader's K-RIS resamples the survivors against pHat_reader.
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.WSReservoir;
import RenderPasses.VisCache.WSReservoirIO;
import RenderPasses.VisCache.WSCellPool;
import Utils.Sampling.SampleGenerator;

// Bound at root by PathTracer.cpp (var["gWSCellPools"], var["gWSCellPoolSlotBuf"]).
// Split-buffer layout:
//   gWSCellPools     — header (fingerprint, count) per cell, capacity entries
//   gWSCellPoolSlotBuf — flat slot array, capacity * WS_CELL_POOL_N entries
// Slot at cell `c`, index `i` lives at gWSCellPoolSlotBuf[c * WS_CELL_POOL_N + i].
// This splits the nested-array-in-struct that DXC rejects at N≥256.
RWStructuredBuffer<WSCellPool>     gWSCellPools;
RWStructuredBuffer<WSCellPoolSlot> gWSCellPoolSlotBuf;

uint wsSlotIndex(uint cell, uint slotIdx) { return cell * WS_CELL_POOL_N + slotIdx; }

// Slot packed-field helpers (mAndFrame = (M << 16) | (frame & 0xFFFFu)).
uint slotGetM(WSCellPoolSlot s)         { return s.mAndFrame >> 16; }
uint slotGetFrame(WSCellPoolSlot s)     { return s.mAndFrame & 0xFFFFu; }
uint slotPackMFrame(uint M, uint frame) { return (min(M, 0xFFFFu) << 16) | (frame & 0xFFFFu); }
uint slotCurrentFrame()                 { return gFrameCount & 0xFFFFu; }
uint slotAge(uint slotFrame)            { return (slotCurrentFrame() - slotFrame) & 0xFFFFu; }

bool wsCellPoolEnabled() { return gWSEnable != 0u && gWSCellPoolEnable != 0u && gWSCellPoolCapacity > 0u && gWSCellPoolFootprintPx > 0u; }

/// Pool addressing mode (gWSPoolAddrMode):
///   0 = 3D world cell (default — open-addressed hash table with double-hash
///       probing on collision via `wsCellPoolFindSlot`; concentrates per-3D-
///       region; persists across frames so an animated camera's pool warms up).
///   1 = 2D screen tile (RTXDI-style — direct array map; tiles never collide
///       within typical capacity, the probe converges at step 0;
///       concentrates per-screen-region for the current frame only).
///
/// The two modes are **functionally equivalent** up to addressing: same
/// `WSCellPool` struct, same Bayer-prepass fill, same RIS-at-insert math
/// (`pHat × V / sourcePdf` weight), same N=128 per-slot reservoir, same
/// reader-side RIS resample. The only physical difference is collision
/// behaviour:
///   - 3D-cell: distinct world cells may hash to the same primary slot;
///     `wsCellPoolFindSlot` probes along an fp-derived odd-step sequence
///     (kMaxProbe=8) to find a slot whose fingerprint matches or is empty;
///   - 2D-tile: direct map sized for `numTilesX × numTilesY` exactly
///     (tiles never collide → probe is a no-op).
///
/// **Tuning equivalence**: when `gWSPoolTileSize` ≈ projected screen-space
/// footprint of the prepass WS cell at `gWSCellLevel`, the two modes
/// concentrate similar M-candidate density per region — just keyed
/// differently. Pick tile size to match cell footprint for apples-to-apples
/// A/B comparison.

// 3D-cell addressing: hash by (posA, faceN). Level is either fixed
// (gWSCellLevel) or footprint-derived (gWSCellPoolFootprintPx > 0).
//
// `gWSCellPoolFootprintPx` is interpreted as **screen-space SIDE LENGTH
// in pixels** (matching gWSPoolTileSize's 2D-tile semantics — they're
// equivalent when these two params agree on side-length, e.g. 16 = 16-px
// tile = 16-px-side cell ≈ 256 px² catchment). Square it before passing
// to vhfLevelForFootprint, which expects an AREA input (it sqrt's
// internally to recover side length, then inverts the geometric ladder
// to find the level whose cell side matches that pixel count at the
// primary hit's depth).
//
// Jitter: jitterQuantize is called with seed = 0xC5u ^ uint(level), so when
// gJitterFilter or gJitterCell is non-zero, both writers and readers of the
// same cell agree on the jittered cell-coordinate (jitterCell, hard
// boundary shift) or get independent per-position jitter (jitterFilter,
// soft boundary). Same call path as the single-slot reservoir's wsQuantizePosA.
WSCellAddress wsResolveCellPoolAddr(float3 posA, float3 faceN)
{
    // Pool always uses analytical entry-level from primary-hit pixel
    // footprint. gWSCellPoolFootprintPx == 0 means "P3d disabled" — caller
    // must check wsCellPoolEnabled() before calling this; here we guard
    // against zero just to keep the math finite.
    float sidePx = max(float(gWSCellPoolFootprintPx), 1.f);
    int lvl = vhfLevelForFootprint(posA, sidePx * sidePx);
    lvl = clamp(lvl, 0, int(gNumLevels) - 1);
    float cellSize = max(vhfPosASize(lvl), 1e-6f);
    int3 q = jitterQuantize(posA, cellSize, 0xC5u ^ uint(lvl));
    uint nb = (gWSNormalAddr != 0u) ? wsNormalBin(faceN) : 0u;
    WSCellAddress a;
    a.slot        = wsAddressHash(q, nb) & (gWSCellPoolCapacity - 1u);
    a.fingerprint = wsFingerprintHash(q, nb);
    return a;
}

// 2D-tile addressing: tileIdx = (pixel/tileSize) flattened to a slot.
// Fingerprint is a fixed sentinel (tiles never collide — direct slot map),
// matched at the reader so the empty-slot test (`fingerprint == 0`) still works.
WSCellAddress wsResolveTilePoolAddr(uint2 pixel)
{
    uint tileSize = max(gWSPoolTileSize, 1u);
    uint tx = pixel.x / tileSize;
    uint ty = pixel.y / tileSize;
    uint numTilesX = max((gWSFrameDimX + tileSize - 1u) / tileSize, 1u);
    WSCellAddress a;
    a.slot        = (ty * numTilesX + tx) & (gWSCellPoolCapacity - 1u);
    a.fingerprint = 0xA11E1234u;  // arbitrary non-zero sentinel; tiles never collide
    return a;
}

// Mode-dispatched insert/read addressing. Callers pass both posA/faceN AND
// pixel; the resolver picks based on `gWSPoolAddrMode`.
WSCellAddress wsResolvePoolAddr(float3 posA, float3 faceN, uint2 pixel)
{
    if (gWSPoolAddrMode == 1u) return wsResolveTilePoolAddr(pixel);
    return wsResolveCellPoolAddr(posA, faceN);
}

// Double-hash probe finder, mirrors vhfFindSlot for the cell-pool table.
// Steps along an odd-step sequence keyed by `fp` to find a slot whose
// fingerprint matches `fp` (hit), or — when `allowInsert` — an empty slot
// the caller may claim. Returns `found = false` if probe budget exhausted.
//
// kMaxProbe budget hard-coded to 8 to match vhfFindSlot; the loop counter
// uses a literal so Slang can unroll across both probe tables uniformly.
//
// kMaxProbe matches the VHF table's budget so contention behaviour is
// uniform across both tables.
//
// Pressure-scaled eviction (writer path only, `allowInsert=true`):
// at probe step `i >= kEvictStartStep` an existing entry is evictable
// if its last-insert frame is older than `kEvictAgeBase << (i - kEvictStartStep)`
// frames. Shallow probes (i < 3) tolerate established entries; deep
// probes (i = 3 → age 1, i = 4 → age 2, i = 5 → age 4, ...) progressively
// allow eviction of stale entries. Mirrors `vhfFindSlot`'s graduated
// pressure but uses `frameLastInsert` as the staleness signal instead
// of an accumulated sample count + decay pass.
static const uint kPoolEvictStartStep = 9999u;  // DIAGNOSTIC: disabled — bisect regression source
static const uint kPoolEvictAgeBase   = 1u;  // frames

uint wsCellPoolFindSlot(uint addr0, uint fp, bool allowInsert, out bool found)
{
    uint h2 = fp | 1u;
    [unroll] for (uint i = 0u; i < 8u; ++i)
    {
        uint slot = (addr0 + i * h2) & (gWSCellPoolCapacity - 1u);
        uint efp  = gWSCellPools[slot].fingerprint;
        if (efp == fp)  { found = true;        return slot; }
        if (efp == 0u)  { found = allowInsert; return slot; }
    }
    found = false;
    return addr0 & (gWSCellPoolCapacity - 1u);
}

// Reader-side: locate the pool entry for `addr` via the probe. Returns the
// buffer slot index + the entry's `count` so the caller can index slot data
// directly (`gWSCellPools[slot].field[i]`). Avoids a 12 KB struct copy that
// would exhaust DXC validation limits at N=1024.
bool wsLookupCellPool(WSCellAddress addr, out uint slot, out uint count)
{
    slot  = 0u;
    count = 0u;
    if (!wsCellPoolEnabled()) return false;
    bool found;
    uint s = wsCellPoolFindSlot(addr.slot, addr.fingerprint, false, found);
    if (!found) return false;
    if (gWSCellPools[s].fingerprint != addr.fingerprint) return false;
    slot  = s;
    // The insert path's `InterlockedAdd` lets count grow past N (each writer
    // beyond N still bumps the counter but writes to a random in-range slot).
    // Cap here so the reader's slot pick stays within [0, N).
    count = min(gWSCellPools[s].count, WS_CELL_POOL_N);
    return count > 0u;
}

void wsCellPoolInsert<S : ISampleGenerator>(WSCellAddress addr, uint lightTypeIndex, uint payload, float sourcePdf, float pHat, inout S sg)
{
    if (!wsCellPoolEnabled()) return;
    if (sourcePdf <= 0.f || pHat <= 0.f) return;
    bool found;
    uint slot = wsCellPoolFindSlot(addr.slot, addr.fingerprint, true, found);
    if (!found) return;

    // AoS insert at N=1024 — never materialise the whole WSCellPool struct
    // (would be 12 KB, exceeds DXIL per-thread limits). The header
    // (fingerprint, count) is read/written via small per-field accesses;
    // slot data lives in WSCellPoolSlot[N] inside the buffer, so a single
    // `slots[writeSlot] = makeSlot(...)` compiles to one bufferStore that
    // covers the whole 12-B slot contiguously. Within-slot coherence
    // (lightTypeIndex/payload/sourcePdf from the same writer) is preserved
    // — this is the load-bearing property that the legacy whole-struct
    // copy gave; AoS gives it without the 12 KB local-memory cost.
    uint efp = gWSCellPools[slot].fingerprint;
    if (efp != addr.fingerprint)
    {
        gWSCellPools[slot].fingerprint = addr.fingerprint;
        gWSCellPools[slot].count       = 0u;
        // No cell-level slot zero-init needed — each slot carries its own
        // `frameStamp` field set at write time. Reader filters `frameStamp
        // == currentFrame` so stale slots from previous occupants (or even
        // previous frames of the same cell) auto-reject.
    }

    // === Mode-gated slot replacement ===
    // gWSCellPoolMode:
    //   0 (P3d)   — raw-pdf-proposal slots, age-pressure replacement
    //   1 (PR3d)  — ReGIR-at-tile: each slot is a reservoir-sampled survivor
    //                  with M-count (high 16 bits of mAndFrame), reader weighs
    //                  by × M; M-cap=20 prevents firefly amplification.
    //
    //   PR3d vs canonical ReGIR (Boksansky+Wyman+Bikker+Lefebvre 2021):
    //     - This impl: uniform-weight reservoir sample (accept prob 1/newM).
    //       Frame-stamp reader filter (`slotGetFrame == currentFrame`) makes
    //       this within-frame RIS — slots stale to prior frames are skipped.
    //     - Canonical ReGIR uses luminance-weighted target (`pHat/sourcePdf`)
    //       so high-radiance candidates dominate the slot. TODO: weight-accept.
    //     - Canonical ReGIR runs a DEDICATED fill compute pass with M_fill=8-32
    //       candidates per slot in one frame. We accumulate across pixels in
    //       the main pass; same effective M when many pixels hit a slot.
    // Both modes share probe, fingerprint claim, and the single uint4 slot
    // store — only the writeSlot pick and the M-packing differ.
    uint writeSlot;
    uint outM;

    if (gWSCellPoolMode == 0u)
    {
        // P3d: K=4 age-pressure probe, pick oldest slot. M stays 0.
        const uint kAgeProbeK = 4u;
        writeSlot              = uint(sampleNext1D(sg) * float(WS_CELL_POOL_N)) % WS_CELL_POOL_N;
        WSCellPoolSlot first   = gWSCellPoolSlotBuf[wsSlotIndex(slot, writeSlot)];
        uint bestAge           = slotAge(slotGetFrame(first));
        [unroll] for (uint k = 1u; k < kAgeProbeK; ++k)
        {
            uint cand               = uint(sampleNext1D(sg) * float(WS_CELL_POOL_N)) % WS_CELL_POOL_N;
            WSCellPoolSlot candSlot = gWSCellPoolSlotBuf[wsSlotIndex(slot, cand)];
            uint candAge            = slotAge(slotGetFrame(candSlot));
            if (candAge > bestAge) { bestAge = candAge; writeSlot = cand; }
        }
        outM = 0u;
    }
    else
    {
        // PR3d: reservoir sample replacement on the writer stream.
        // - Random single slot pick.
        // - Read existing M, increment with classic ReSTIR M-cap=20.
        // - Replace candidate fields with prob 1/M' (uniform reservoir over writer stream).
        // - Always update mAndFrame (new frame + new M), even if candidate kept.
        const uint kMCap        = 20u;
        writeSlot               = uint(sampleNext1D(sg) * float(WS_CELL_POOL_N)) % WS_CELL_POOL_N;
        WSCellPoolSlot existing = gWSCellPoolSlotBuf[wsSlotIndex(slot, writeSlot)];
        uint oldM               = slotGetM(existing);
        uint newM               = min(oldM + 1u, kMCap);
        outM                    = newM;

        if (sampleNext1D(sg) >= 1.0f / float(newM))
        {
            // Keep existing candidate fields — just bump mAndFrame (4-byte sub-field write).
            gWSCellPoolSlotBuf[wsSlotIndex(slot, writeSlot)].mAndFrame =
                slotPackMFrame(newM, slotCurrentFrame());
            if (gWSCellPools[slot].count <= writeSlot)
                gWSCellPools[slot].count = writeSlot + 1u;
            return;
        }
        // else: fall through — replace whole slot with new writer's data.
    }

    WSCellPoolSlot s;
    s.lightTypeIndex = lightTypeIndex;
    s.payload        = payload;
    s.sourcePdf      = sourcePdf;
    s.mAndFrame      = slotPackMFrame(outM, slotCurrentFrame());
    gWSCellPoolSlotBuf[wsSlotIndex(slot, writeSlot)] = s;  // single uint4 store
    if (gWSCellPools[slot].count <= writeSlot)
        gWSCellPools[slot].count = writeSlot + 1u;
}

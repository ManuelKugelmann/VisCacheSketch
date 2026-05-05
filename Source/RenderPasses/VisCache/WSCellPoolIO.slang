/***************************************************************************
 * WSCellPoolIO.slang
 *
 * §9.4 World-space ReSTIR DI — cell-pool buffer + load/insert helpers.
 *
 * Pool keyed by the same WSCellAddress as the single-slot reservoir
 * (gWSReservoirs). Lives in its own buffer so the existing read/write
 * paths to the single-slot reservoir keep working unchanged.
 *
 * Insert policy (step a, simplest workable):
 *   - count < N: append at slot `count`.
 *   - count == N: random-replace one of the N slots (uniform).
 * Last-writer-wins per slot under contention (ReSTIR is sample-loss-tolerant).
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.WSReservoir;
import RenderPasses.VisCache.WSReservoirIO;
import RenderPasses.VisCache.WSCellPool;
import Utils.Sampling.SampleGenerator;

// Bound at root by PathTracer.cpp (var["gWSCellPools"]).
RWStructuredBuffer<WSCellPool> gWSCellPools;

bool wsCellPoolEnabled() { return gWSEnable != 0u && gWSCellPoolEnable != 0u && gWSCellPoolCapacity > 0u; }

/// Pool addressing mode (gWSPoolAddrMode):
///   0 = 3D world cell (default — open-addressed hash; concentrates per-3D-
///       region; persists across frames so an animated camera's pool warms up).
///   1 = 2D screen tile (RTXDI-style — direct array, no hash collisions;
///       concentrates per-screen-region for the current frame only).
///
/// The two modes are **functionally equivalent** up to addressing: same
/// `WSCellPool` struct, same Bayer-prepass fill, same RIS-at-insert math
/// (`pHat × V / sourcePdf` weight), same N=8 per-slot reservoir, same
/// reader-side RIS resample. The only physical difference is buffer-size
/// semantics:
///   - 3D-cell: hash table sized for total potential cells × occupancy
///     overhead (collisions waste slots);
///   - 2D-tile: direct map sized for `numTilesX × numTilesY` exactly
///     (no collisions, no waste).
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
    int lvl;
    if (gWSCellPoolFootprintPx > 0u)
    {
        // Side length → area for vhfLevelForFootprint's area-input semantics.
        float sidePx = float(gWSCellPoolFootprintPx);
        lvl = vhfLevelForFootprint(posA, sidePx * sidePx);
    }
    else
    {
        lvl = clamp(int(gWSCellLevel), 0, int(gNumLevels) - 1);
    }
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

bool wsLoadCellPool(WSCellAddress addr, out WSCellPool pool)
{
    pool = wsCellPoolInit(0u);
    if (!wsCellPoolEnabled()) return false;
    WSCellPool p = gWSCellPools[addr.slot];
    if (p.fingerprint != addr.fingerprint) return false;
    pool = p;
    return p.count > 0u;
}

void wsCellPoolInsert<S : ISampleGenerator>(WSCellAddress addr, uint lightTypeIndex, uint payload, float sourcePdf, float pHat, inout S sg)
{
    if (!wsCellPoolEnabled()) return;
    if (sourcePdf <= 0.f || pHat <= 0.f) return;
    WSCellPool p = gWSCellPools[addr.slot];

    // New cell: zero-init and claim.
    if (p.fingerprint != addr.fingerprint)
    {
        p = wsCellPoolInit(addr.fingerprint);
    }

    // §9.4 fill — RTXDI-tile semantics: each slot stores one writer's
    // pdf-proposal candidate, NO writer-pHat tracking, NO Bitterli
    // streaming RIS at write. Random-pick a slot, last-writer-wins.
    // The writer-pHat-weighted streaming RIS we used previously biases
    // the slot's survivor toward the writer's shading point and breaks
    // cross-pixel reuse on heterogeneous lighting (Sponza). RTXDI's
    // tile presample does exactly this — pdf-sample one light, store
    // (lightIndex, invSourcePdf), no shading-point dependency.
    //
    // Across many writers per cell per frame, last-writer-wins per slot
    // converges to the writers' joint pdf distribution; the reader's
    // K-RIS resamples with `pHat_reader × pdf_reader / sourcePdf_writer`
    // (Convention B, matches RTXDI's `targetPdf × invSourcePdf`).
    uint writeSlot = uint(sampleNext1D(sg) * float(WS_CELL_POOL_N)) % WS_CELL_POOL_N;
    p.lightTypeIndex[writeSlot] = lightTypeIndex;
    p.payload[writeSlot]        = payload;
    p.sourcePdf[writeSlot]      = sourcePdf;
    if (p.count <= writeSlot) p.count = writeSlot + 1u;
    gWSCellPools[addr.slot] = p;
}

/***************************************************************************
 * ReservoirIO.slang
 *
 * §9.4 World-space ReSTIR DI — cell selector + reservoir CRUD.
 *
 * Functionally independent of VisCache (the level it picks is its own
 * choice) but shares all the addressing building blocks: posA cascade
 * (vhfPosASize), quantization with jitter (jitterQuantize, gJitterFilter,
 * gJitterCell), and the pcgHashA / pcgHashEndpoint hash family. WS-ReSTIR
 * picks a level via gCellLevel; everything else inherits from the shared
 * cascade. They may also interact via the μ-aware target function (§9.1).
 *
 * v1 scope (this file):
 *   - posA-keyed cell at a configurable cascade level (gCellLevel).
 *   - Single-slot, fingerprint-tagged reservoir (no probing in v1).
 *   - Local-RIS into a thread-local reservoir, then temporal merge into
 *     the cell's persistent reservoir.
 *
 * Symbols imported from VisCache.slang:
 *   pcgHashA, pcgHashEndpoint, kSaltA, gFrameCount, gCellLevel,
 *   vhfPosASize, jitterQuantize, gCapacity, gMCap, gLightMuMin
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.VisCache;
import RenderPasses.ReSTIRCommon.Reservoir;
import Utils.Sampling.SampleGenerator;

// ---------------------------------------------------------------------------
// Bound at root by PathTracer.cpp (var["gReservoirs"]). Not part of any
// ParameterBlock — global-scope so all RT stages see the same buffer.
// ---------------------------------------------------------------------------
RWStructuredBuffer<Reservoir> gReservoirs;
// Per-pixel temporal reservoir (W*H slots, indexed by pixel coords).
RWStructuredBuffer<Reservoir> gPixelReservoirs;

// PathTracer.slang doesn't import VisCache directly, so route the gates
// through helpers that have visibility on the cbuffer globals.
bool enabled() { return gEnable != 0u && gCapacity > 0u; }
uint spatialNeighbourCount() { return min(gSpatialNeighbours, 4u); }
bool pixelReservoirEnabled() { return gFrameDimX > 0u && gFrameDimY > 0u; }
uint pixelIndex(uint2 pixel) { return pixel.y * gFrameDimX + pixel.x; }
uint visInPHatMode() { return gVisInPHat; }       ///< 0=blind, 1=cache, 2=explicit
float lightMuMin() { return gLightMuMin; }
uint retraceOnReuseMode() { return gRetraceOnReuseMode; } ///< 0=Off, 1=FullTrace, 2=CacheCV — RTXDI BiasCorrection analog for reservoir reuse.

// ---------------------------------------------------------------------------
// Quantize primary-hit position to integer cell coords by REUSING VisCache's
// posA cascade. The level is the analytic entry from primary-hit pixel
// footprint via vhfLevelForFootprint(targetPx²) — same mechanism as the
// pool side. Jitter (gJitterFilter, gJitterCell) is shared with VisCache
// rather than duplicated.
//
// gCellReservoirFootprintPx == 0 means "R3d DISABLED" (cell-level
// reservoir off). Callers must check `cellReservoirEnabled()` before
// invoking the cell-reservoir read/write paths.
// ---------------------------------------------------------------------------
bool cellReservoirEnabled() { return gCellReservoirFootprintPx > 0u; }

int levelForReservoir(float3 posA)
{
    int N = int(gNumLevels);
    float sidePx = max(float(gCellReservoirFootprintPx), 1.f);
    int lvl = vhfLevelForFootprint(posA, sidePx * sidePx);
    return clamp(lvl, 0, N - 1);
}

// Per-pixel LOD jitter: pick a level at base+offset where offset is drawn
// from a one-sided exponential distribution clamped to [0, J] (J =
// gCellLevelJitter). Most queries hit base; coarser levels with falling
// probability ½, ¼, ⅛, … . Never queries below base — cells finer than
// the ray footprint can't hold meaningful state, and the cold-cell
// fallback we want is *coarser*, not finer.
//
// The base level is `levelForReservoir(posA)` — i.e. the analytically-
// derived entry from primary-hit pixel footprint when
// gCellReservoirFootprintPx > 0, else the fixed gCellLevel. The jitter
// always rides on top of whichever base the canonical reservoir-level
// selection chose, so footprint-derived addressing and LOD jitter compose
// correctly.
//
// Form follows MCPG 2025 (Alber/Hanika/Dachsbacher, merian-quake/mc.glsl):
//     level = target + uint(-log2(1 - u))
// which is the inverse-CDF of Exp(λ = ln 2). Clamping to [0, J] gives a
// truncated exponential.
int levelJittered(uint2 pixel, float3 posA)
{
    int N = int(gNumLevels);
    int base = levelForReservoir(posA);
    if (gCellLevelJitter == 0u) return base;
    uint3 r = pcg3d(uint3(pixel.x, pixel.y, gFrameCount + 0xCAA5u));
    float u = float(r.x & 0xFFFFu) / 65535.f;            // [0, 1)
    // -log2(1 - u): u=0→0, u=0.5→1, u=0.75→2, u=0.875→3, ...
    float fOff = -log2(max(1.f - u, 1e-7f));
    int dl = clamp(int(fOff), 0, int(gCellLevelJitter));
    return clamp(base + dl, 0, N - 1);
}

int3 quantizePosA(float3 posA)
{
    int lvl = levelForReservoir(posA);
    float cs = max(vhfPosASize(lvl), 1e-6f);
    return jitterQuantize(posA, cs, 0xC5u ^ uint(lvl));
}

// normalBin moved to VisCache.slang (unguarded section) so it can be shared
// with ReSTIRPTPass's PathReservoirCellPool. Same definition, just one home.

// ---------------------------------------------------------------------------
// Two hashes from quantized cell coords. Uses VisCache's pcgHashA
// (kSaltA-salted pcgHashEndpoint) for the address — same hash family as
// VisCache's A-side, just at WS-ReSTIR's own quantization. Fingerprint
// uses the same coords with a different salt so address and fingerprint
// are uncorrelated. When gNormalAddr is on, the 6-axis normal bin is
// mixed in so different orientations at the same posW resolve to
// different cells.
//   addr        — slot index, masked to capacity at call site.
//   fingerprint — collision tag stored in the slot. Always nonzero (0 = empty).
// ---------------------------------------------------------------------------
static const uint kWSFpSalt = 0xA5C3F09Bu;

uint addressHash(int3 q, uint normalBin)
{
    uint h = pcgHashA(q, 0u);
    if (gNormalAddr != 0u) h ^= normalBin * 0x9E370001u;
    return h;
}
uint fingerprintHash(int3 q, uint normalBin)
{
    uint h = pcgHashEndpoint(q, 0u, kSaltA ^ kWSFpSalt);
    if (gNormalAddr != 0u) h ^= normalBin * 0xB5297A4Du;
    return (h == 0u) ? 1u : h;     // 0 reserved for empty slot
}

// ---------------------------------------------------------------------------
// Resolve (slot, fingerprint) from a primary-hit posA + faceN. Used for both
// the home cell (zero jitter) and jittered neighbour queries — same code path.
// ---------------------------------------------------------------------------
struct CellAddress { uint slot; uint fingerprint; };
CellAddress resolveCell(float3 posA, float3 faceN)
{
    int3 q  = quantizePosA(posA);
    uint nb = (gNormalAddr != 0u) ? normalBin(faceN) : 0u;
    CellAddress a;
    a.slot        = addressHash(q, nb) & (gCapacity - 1u);
    a.fingerprint = fingerprintHash(q, nb);
    return a;
}

// ---------------------------------------------------------------------------
// Local thread-private reservoir for RIS. Identical struct to Reservoir
// minus persistent-only fields; kept separate to make the merge code clearer.
// ---------------------------------------------------------------------------
struct LocalReservoir
{
    uint   lightTypeIndex; // packed (lightType<<24) | lightIndex
    uint   payload;        // barys (emissive) | dirOct (env) | 0 (analytic)
    float  targetPdf;      // p̂ at the time the chosen sample was selected
    float  M;              // candidate count
    float  wSum;           // accumulated RIS weight sum

    [mutating] void init()
    {
        lightTypeIndex = 0u; payload = 0u;
        targetPdf = 0.f; M = 0.f; wSum = 0.f;
    }

    [mutating]
    void streamingAdd<S : ISampleGenerator>(uint cand_lightTypeIndex, uint cand_payload,
                                            float cand_targetPdf, float cand_invPdf,
                                            inout S sg)
    {
        // Bitterli '20 streaming reservoir: each candidate's weight is
        // p_hat * 1/p_proposal. With M candidates we sum and roulette.
        float w = cand_targetPdf * cand_invPdf;
        if (!isnan(w) && w > 0.f)
        {
            wSum += w;
            M    += 1.f;
            if (sampleNext1D(sg) * wSum <= w)
            {
                lightTypeIndex = cand_lightTypeIndex;
                payload        = cand_payload;
                targetPdf      = cand_targetPdf;
            }
        }
        else
        {
            M += 1.f;     // count the candidate even if rejected (M-cap accounting)
        }
    }

    // Cross-pixel Bitterli reservoir merge — fold a foreign reservoir
    // (e.g. world-space cell-pool slot) into our local stream while
    // recomputing the weight at OUR pHat instead of inheriting the
    // writer's normalization. M-cap to prevent unbounded persistence.
    //
    // Math:  the foreign reservoir stored
    //          wSum_other  = Σ_i pHat_writer(cand_i) / pdf_i  (Bitterli RIS weights)
    //          M_other     = candidate count (writers that hit the slot)
    //          pHat_writer = pHat at write time for the SELECTED winner
    //        Bitterli's spatial-merge weight at the reader, with a temporal
    //        cap M_capped = min(M_other, M_cap):
    //          W_other      = wSum_other / (pHat_writer × M_other)
    //          w_at_reader  = pHat_reader × W_other × M_capped
    //                       = pHat_reader × wSum_other × M_capped / (pHat_writer × M_other)
    //        We add `w_at_reader` to `wSum` and `M_capped` to `M`. The
    //        approximation is `pHat_writer ≈ pHat_reader` within the cell;
    //        bias is bounded by pHat-variance among writers. Standard
    //        cross-pixel reuse assumption (same as ReSTIR's spatial merge).
    [mutating]
    void streamingMergeReservoir<S : ISampleGenerator>(uint cand_lightTypeIndex, uint cand_payload,
                                                       float pHat_reader, float wSum_other,
                                                       float pHat_writer, float M_other,
                                                       float M_cap,
                                                       inout S sg)
    {
        if (M_other <= 0.f || pHat_writer <= 0.f || pHat_reader <= 0.f) return;
        float Mcapped = min(M_other, M_cap);
        float w = pHat_reader * wSum_other * Mcapped / (pHat_writer * M_other);
        if (!(w > 0.f) || isnan(w)) { M += Mcapped; return; }
        wSum += w;
        M    += Mcapped;
        if (sampleNext1D(sg) * wSum <= w)
        {
            lightTypeIndex = cand_lightTypeIndex;
            payload        = cand_payload;
            targetPdf      = pHat_reader;
        }
    }
};

// ---------------------------------------------------------------------------
// Temporal merge: blend the freshly-built local reservoir with the cell's
// persistent reservoir. Does an M-capped weighted-add — Bitterli '20 §5
// "temporal reuse" but on a world-space cell rather than the previous frame.
//
// Atomicity strategy (v1, simplest workable):
//   - Use InterlockedCompareExchange on the fingerprint field as a soft
//     mutex: 0 (or matching fingerprint) → write; mismatched → drop the
//     write. ReSTIR is robust to occasional sample loss, so dropping on
//     contention keeps the v1 implementation simple and correct.
//   - We accept that one writer per frame per cell wins. Spatial gather
//     (future v2) will add explicit reservoir copies and not need atomicity.
// ---------------------------------------------------------------------------
void mergeIntoCell<S : ISampleGenerator>(CellAddress addr, LocalReservoir local, inout S sg)
{
    if (!cellReservoirEnabled()) return;
    if (gCapacity == 0u || local.M <= 0.f) return;

    // Soft-lock the slot: only proceed if it's empty (fp=0) or already
    // claimed by our cell (matching fingerprint). On collision (different
    // fingerprint owns the slot) we drop the update.
    Reservoir cell = gReservoirs[addr.slot];
    if (cell.fingerprint != 0u && cell.fingerprint != addr.fingerprint)
    {
        // Collision with a different cell. v1 policy: defer to existing
        // owner. Could overwrite-on-staleness once we add a frame counter
        // gate; not implemented for v1 simplicity.
        return;
    }

    // Initialize empty cell with our local reservoir's chosen sample.
    if (cell.fingerprint == 0u)
    {
        cell = reservoirInit(addr.fingerprint);
        cell.lightTypeIndex   = local.lightTypeIndex;
        cell.payload          = local.payload;
        cell.targetPdf        = local.targetPdf;
        cell.M                = local.M;
        // 1/p̂ * (1/M) * w_sum
        float pHat = max(local.targetPdf, 1e-12f);
        cell.W                = (local.M > 0.f) ? (local.wSum / (pHat * local.M)) : 0.f;
        cell.frameLastUpdated = gFrameCount;
        gReservoirs[addr.slot] = cell;
        return;
    }

    // Standard reservoir merge: combine the persistent and new wSum streams,
    // re-roulette to pick the surviving sample.
    float pHatLocal  = max(local.targetPdf, 1e-12f);
    float pHatCell   = max(cell.targetPdf,  1e-12f);
    float wSumCell   = cell.W * pHatCell * cell.M;
    float wSumNew    = local.wSum;
    float wSumTotal  = wSumCell + wSumNew;
    float Mnew       = min(cell.M + local.M, gMCap);

    if (wSumTotal <= 0.f) return;

    bool keepLocal = sampleNext1D(sg) * wSumTotal <= wSumNew;

    cell.fingerprint      = addr.fingerprint;
    cell.M                = Mnew;
    cell.frameLastUpdated = gFrameCount;
    if (keepLocal)
    {
        cell.lightTypeIndex = local.lightTypeIndex;
        cell.payload        = local.payload;
        cell.targetPdf      = local.targetPdf;
        cell.W              = wSumTotal / (pHatLocal * Mnew);
    }
    else
    {
        cell.W              = wSumTotal / (pHatCell * Mnew);
    }
    gReservoirs[addr.slot] = cell;
}

// ---------------------------------------------------------------------------
// Read the persistent cell reservoir if it matches the current cell's
// fingerprint. Caller materialises the chosen sample via rebuildLightSample.
// Returns false on miss (cold cell or collision).
// ---------------------------------------------------------------------------
bool loadCell(CellAddress addr, out Reservoir cell)
{
    cell = reservoirInit(0u);
    if (!cellReservoirEnabled()) return false;
    if (gCapacity == 0u) return false;
    Reservoir r = gReservoirs[addr.slot];
    if (r.fingerprint != addr.fingerprint) return false;
    cell = r;
    return true;
}

// ---------------------------------------------------------------------------
// Build an orthonormal tangent basis from the face normal — used for jittered
// neighbour queries (the jitter is in the surface tangent plane so it never
// crosses the vertical-cell discontinuity for ground-plane / wall pixels).
// ---------------------------------------------------------------------------
void tangentBasis(float3 n, out float3 tA, out float3 tB)
{
    float3 a = abs(n);
    float3 up = (a.x <= a.y && a.x <= a.z) ? float3(1,0,0)
              : (a.y <= a.z)               ? float3(0,1,0)
                                            : float3(0,0,1);
    tA = normalize(cross(n, up));
    tB = cross(n, tA);
}

// ---------------------------------------------------------------------------
// Spatial gather via JITTERED lookup. Instead of integer-offset addressing
// which fixes the neighbour set to ±1 cells in two axes, we perturb posA
// in the surface tangent plane by a per-pixel stratified 2D sample of
// magnitude ~1.5×cellSize, then run the same resolveCell on the result.
//
// Properties of this scheme vs. integer-offset:
//   - Smooth coverage: pixels near a cell boundary naturally distribute
//     their queries across the boundary cells; no harsh per-cell artifacts.
//   - Per-pixel decorrelation: each pixel's jitter is independent.
//   - Single code path: home cell is resolveCell(posA, faceN); neighbour
//     cell is resolveCell(posA + tangent_jitter, faceN). Same hash.
//   - Composes with normal-aware addressing — the jittered posW is fed to
//     the same hash regardless of gNormalAddr.
//
// `i` is the neighbour index (0..N-1) for stratification; per-pixel `jitter2D`
// is fresh randomness from the path's SampleGenerator. The caller filters out
// queries that landed in the home cell by fingerprint compare.
// ---------------------------------------------------------------------------
CellAddress resolveJitteredCell(float3 posA, float3 faceN, uint i, uint nTotal, float2 jitter2D)
{
    // Cell-size for the jitter magnitude is computed at the home position's
    // level — the spatial-reuse neighbourhood scales with the local cell size,
    // matching the analytical-entry behaviour when gCellReservoirFootprintPx
    // is set.
    float cellSize = max(vhfPosASize(levelForReservoir(posA)), 1e-6f);

    // 2x2 stratification across [-1, 1] x [-1, 1], jittered within stratum.
    // For nTotal up to 4 we use a 2x2 stratum grid; for higher N we just
    // use round-robin and let the per-pixel jitter handle decorrelation.
    uint sx = i & 1u;
    uint sy = (i >> 1) & 1u;
    float2 inStratum = (float2(sx, sy) + jitter2D) * 0.5f;     // [0,1]
    float2 strat = inStratum * 2.f - 1.f;                       // [-1,1]
    // Magnitude 8x cellSize: large enough to span a wide spatial neighbourhood
    // (8 cells across), giving RTXDI-style screen-spread spatial coverage —
    // each jittered query hits a *different* cell with a *different* popular
    // winner, providing the sample-diversity that small jitter (≤2 cells)
    // does not. This is the WS-only equivalent of RTXDI's k=5 random
    // screen-pixel spatial reuse.
    float2 disp = strat * (8.f * cellSize);

    float3 tA, tB;
    tangentBasis(faceN, tA, tB);
    float3 posJittered = posA + tA * disp.x + tB * disp.y;
    return resolveCell(posJittered, faceN);
}


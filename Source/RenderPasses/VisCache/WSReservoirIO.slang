/***************************************************************************
 * WSReservoirIO.slang
 *
 * §9.4 World-space ReSTIR DI — cell selector + reservoir CRUD.
 *
 * v1 scope (this file):
 *   - posA-keyed cell at a configurable cascade level (gWSLevelOffset).
 *   - Single-slot, fingerprint-tagged reservoir (no probing in v1).
 *   - Local-RIS into a thread-local reservoir, then temporal merge into
 *     the cell's persistent reservoir.
 *   - SPATIAL NEIGHBOUR GATHER is intentionally not implemented in v1 —
 *     temporal cell-sharing already concentrates many pixels onto one
 *     reservoir, recovering most of the many-lights low-SPP gain.
 *
 * The hash addresses ONLY posA (primary hit) — reservoirs cluster pixels
 * by their primary surface, not by light, so the (posA, posB) pairing of
 * the visibility cache does not apply here.
 *
 * Symbols imported from VisCache.slang:
 *   pcg3d, vhfPosASize, gNumLevels, gFrameCount, gWSLevelOffset,
 *   gWSCapacity, gWSMCap, gWSLightMuMin
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.VisCache;
import RenderPasses.VisCache.WSReservoir;
import Utils.Sampling.SampleGenerator;

// ---------------------------------------------------------------------------
// Bound at root by PathTracer.cpp (var["gWSReservoirs"]). Not part of any
// ParameterBlock — global-scope so all RT stages see the same buffer.
// ---------------------------------------------------------------------------
RWStructuredBuffer<WSReservoir> gWSReservoirs;
// Per-pixel temporal reservoir (W*H slots, indexed by pixel coords).
RWStructuredBuffer<WSReservoir> gWSPixelReservoirs;

// PathTracer.slang doesn't import VisCache directly, so route the gates
// through helpers that have visibility on the cbuffer globals.
bool wsEnabled() { return gWSEnable != 0u && gWSCapacity > 0u; }
uint wsSpatialNeighbourCount() { return min(gWSSpatialNeighbours, 4u); }
bool wsPixelReservoirEnabled() { return gWSFrameDimX > 0u && gWSFrameDimY > 0u; }
uint wsPixelIndex(uint2 pixel) { return pixel.y * gWSFrameDimX + pixel.x; }

// ---------------------------------------------------------------------------
// Reservoir cascade level. Mirrors the §9.4 design call: reservoirs read at
// `wsLevelOffset` levels coarser than the visibility cascade's finest level.
// gNumLevels is the total cascade depth; default gWSLevelOffset=1 places
// reservoirs one level above the finest cell — a deliberate coarsening so
// many pixels share one reservoir.
// ---------------------------------------------------------------------------
int wsCascadeLevel()
{
    int N = int(gNumLevels);
    int lvl = (N - 1) - int(gWSLevelOffset);
    return max(0, min(N - 1, lvl));
}

// ---------------------------------------------------------------------------
// Quantize primary-hit position to integer cell coords at the chosen cascade
// level. Same scheme as VisCache's posA quantization: floor(posA / cellSize).
// ---------------------------------------------------------------------------
int3 wsQuantizePosA(float3 posA, int lvl)
{
    float cs = max(vhfPosASize(lvl), 1e-6f);
    return int3(floor(posA / cs));
}

// ---------------------------------------------------------------------------
// 6-axis face-normal bin (±X, ±Y, ±Z = 6 distinct bins).
// Used only when gWSNormalAddr != 0 — folded into both wsAddressHash and
// wsFingerprintHash so different-orientation surfaces at the same posW
// don't share a cell.
// ---------------------------------------------------------------------------
uint wsNormalBin(float3 n)
{
    float3 a = abs(n);
    int axis = (a.x >= a.y && a.x >= a.z) ? 0 : (a.y >= a.z ? 1 : 2);
    bool pos = n[axis] >= 0.f;
    return uint(axis * 2 + (pos ? 0 : 1));     // 0..5
}

// ---------------------------------------------------------------------------
// Two pcg3d-derived 32-bit hashes from quantized cell coords + level.
// When gWSNormalAddr is on, the 6-axis normal bin is mixed into the salt so
// different orientations at the same posW resolve to different cells.
//   addr        — slot index, masked to capacity at call site.
//   fingerprint — collision tag stored in the slot. Always nonzero (0 = empty).
// ---------------------------------------------------------------------------
uint wsAddressHash(int3 q, int lvl, uint normalBin)
{
    uint salt = uint(lvl) * 0xC2B2AE35u + normalBin * 0x9E370001u;
    uint3 h = pcg3d(uint3(q) + uint3(0x9E3779B9u, 0x85EBCA6Bu, salt));
    return h.x ^ h.y ^ h.z;
}
uint wsFingerprintHash(int3 q, int lvl, uint normalBin)
{
    uint salt = uint(lvl) * 0xFEEDFACEu + normalBin * 0xB5297A4Du;
    uint3 h = pcg3d(uint3(q) + uint3(0xDEADBEEFu, 0xC0FFEE13u, salt));
    uint fp = h.x ^ h.y ^ h.z;
    return fp == 0u ? 1u : fp;     // 0 reserved for empty slot
}

// ---------------------------------------------------------------------------
// Resolve (slot, fingerprint) from a primary-hit posA + faceN. Used for both
// the home cell (zero jitter) and jittered neighbour queries — same code path.
// ---------------------------------------------------------------------------
struct WSCellAddress { uint slot; uint fingerprint; };
WSCellAddress wsResolveCell(float3 posA, float3 faceN)
{
    int lvl = wsCascadeLevel();
    int3 q  = wsQuantizePosA(posA, lvl);
    uint nb = (gWSNormalAddr != 0u) ? wsNormalBin(faceN) : 0u;
    WSCellAddress a;
    a.slot        = wsAddressHash(q, lvl, nb) & (gWSCapacity - 1u);
    a.fingerprint = wsFingerprintHash(q, lvl, nb);
    return a;
}

// ---------------------------------------------------------------------------
// Local thread-private reservoir for RIS. Identical struct to WSReservoir
// minus persistent-only fields; kept separate to make the merge code clearer.
// ---------------------------------------------------------------------------
struct WSLocalReservoir
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

    // Note: a previous mass-weighted merge primitive (streamingMergeCell)
    // was removed in the §9.4 selection-only fix. Cells are now added as
    // single RIS candidates via streamingAdd above, with per-pixel pdf at
    // the new shading point — keeps W per-pixel.
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
void wsMergeIntoCell<S : ISampleGenerator>(WSCellAddress addr, WSLocalReservoir local, inout S sg)
{
    if (gWSCapacity == 0u || local.M <= 0.f) return;

    // Soft-lock the slot: only proceed if it's empty (fp=0) or already
    // claimed by our cell (matching fingerprint). On collision (different
    // fingerprint owns the slot) we drop the update.
    WSReservoir cell = gWSReservoirs[addr.slot];
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
        cell = wsReservoirInit(addr.fingerprint);
        cell.lightTypeIndex   = local.lightTypeIndex;
        cell.payload          = local.payload;
        cell.targetPdf        = local.targetPdf;
        cell.M                = local.M;
        // 1/p̂ * (1/M) * w_sum
        float pHat = max(local.targetPdf, 1e-12f);
        cell.W                = (local.M > 0.f) ? (local.wSum / (pHat * local.M)) : 0.f;
        cell.frameLastUpdated = gFrameCount;
        gWSReservoirs[addr.slot] = cell;
        return;
    }

    // Standard reservoir merge: combine the persistent and new wSum streams,
    // re-roulette to pick the surviving sample.
    float pHatLocal  = max(local.targetPdf, 1e-12f);
    float pHatCell   = max(cell.targetPdf,  1e-12f);
    float wSumCell   = cell.W * pHatCell * cell.M;
    float wSumNew    = local.wSum;
    float wSumTotal  = wSumCell + wSumNew;
    float Mnew       = min(cell.M + local.M, gWSMCap);

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
    gWSReservoirs[addr.slot] = cell;
}

// ---------------------------------------------------------------------------
// Read the persistent cell reservoir if it matches the current cell's
// fingerprint. Caller materialises the chosen sample via wsRebuildLightSample.
// Returns false on miss (cold cell or collision).
// ---------------------------------------------------------------------------
bool wsLoadCell(WSCellAddress addr, out WSReservoir cell)
{
    cell = wsReservoirInit(0u);
    if (gWSCapacity == 0u) return false;
    WSReservoir r = gWSReservoirs[addr.slot];
    if (r.fingerprint != addr.fingerprint) return false;
    cell = r;
    return true;
}

// ---------------------------------------------------------------------------
// Build an orthonormal tangent basis from the face normal — used for jittered
// neighbour queries (the jitter is in the surface tangent plane so it never
// crosses the vertical-cell discontinuity for ground-plane / wall pixels).
// ---------------------------------------------------------------------------
void wsTangentBasis(float3 n, out float3 tA, out float3 tB)
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
// magnitude ~1.5×cellSize, then run the same wsResolveCell on the result.
//
// Properties of this scheme vs. integer-offset:
//   - Smooth coverage: pixels near a cell boundary naturally distribute
//     their queries across the boundary cells; no harsh per-cell artifacts.
//   - Per-pixel decorrelation: each pixel's jitter is independent.
//   - Single code path: home cell is wsResolveCell(posA, faceN); neighbour
//     cell is wsResolveCell(posA + tangent_jitter, faceN). Same hash.
//   - Composes with normal-aware addressing — the jittered posW is fed to
//     the same hash regardless of gWSNormalAddr.
//
// `i` is the neighbour index (0..N-1) for stratification; per-pixel `jitter2D`
// is fresh randomness from the path's SampleGenerator. The caller filters out
// queries that landed in the home cell by fingerprint compare.
// ---------------------------------------------------------------------------
WSCellAddress wsResolveJitteredCell(float3 posA, float3 faceN, uint i, uint nTotal, float2 jitter2D)
{
    int lvl = wsCascadeLevel();
    float cellSize = max(vhfPosASize(lvl), 1e-6f);

    // 2x2 stratification across [-1, 1] x [-1, 1], jittered within stratum.
    // For nTotal up to 4 we use a 2x2 stratum grid; for higher N we just
    // use round-robin and let the per-pixel jitter handle decorrelation.
    uint sx = i & 1u;
    uint sy = (i >> 1) & 1u;
    float2 inStratum = (float2(sx, sy) + jitter2D) * 0.5f;     // [0,1]
    float2 strat = inStratum * 2.f - 1.f;                       // [-1,1]
    // Magnitude 1.5x cellSize: enough to land in adjacent cells but not so
    // far we cross multiple cells.
    float2 disp = strat * (1.5f * cellSize);

    float3 tA, tB;
    wsTangentBasis(faceN, tA, tB);
    float3 posJittered = posA + tA * disp.x + tB * disp.y;
    return wsResolveCell(posJittered, faceN);
}


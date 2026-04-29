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

// PathTracer.slang doesn't import VisCache directly, so route the gates
// through helpers that have visibility on the cbuffer globals.
bool wsEnabled() { return gWSEnable != 0u && gWSCapacity > 0u; }
uint wsSpatialNeighbourCount() { return min(gWSSpatialNeighbours, 4u); }

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
// Two pcg3d-derived 32-bit hashes from the same integer coords:
//   addr        — slot index, masked to capacity at call site.
//   fingerprint — collision tag stored in the slot. Always nonzero (0 = empty).
// Salts differentiate the two hashes from each other and from the visibility
// cache's address/fingerprint hashes (ensures independence).
// ---------------------------------------------------------------------------
uint wsAddressHash(int3 q, int lvl)
{
    uint3 h = pcg3d(uint3(q) + uint3(0x9E3779B9u, 0x85EBCA6Bu, uint(lvl) * 0xC2B2AE35u));
    return h.x ^ h.y ^ h.z;
}
uint wsFingerprintHash(int3 q, int lvl)
{
    uint3 h = pcg3d(uint3(q) + uint3(0xDEADBEEFu, 0xC0FFEE13u, uint(lvl) * 0xFEEDFACEu));
    uint fp = h.x ^ h.y ^ h.z;
    return fp == 0u ? 1u : fp;     // 0 reserved for empty slot
}

// ---------------------------------------------------------------------------
// Resolve (slot, fingerprint) from a primary-hit posA. Single call site.
// ---------------------------------------------------------------------------
struct WSCellAddress { uint slot; uint fingerprint; };
WSCellAddress wsResolveCell(float3 posA)
{
    int lvl = wsCascadeLevel();
    int3 q = wsQuantizePosA(posA, lvl);
    WSCellAddress a;
    a.slot        = wsAddressHash(q, lvl) & (gWSCapacity - 1u);
    a.fingerprint = wsFingerprintHash(q, lvl);
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

    // Merge an already-aggregated reservoir (from a WS cell) into the local
    // stream: weight contribution = p̂_at_new_surface * (cell.W * cell.M),
    // sample mass = cell.M (capped on the way in by caller).
    [mutating]
    void streamingMergeCell<S : ISampleGenerator>(uint cand_lightTypeIndex, uint cand_payload,
                                                  float cand_pHatAtNew, float cellW, float cellM,
                                                  inout S sg)
    {
        float w = cand_pHatAtNew * cellW * cellM;
        if (!isnan(w) && w > 0.f)
        {
            wSum += w;
            M    += cellM;
            if (sampleNext1D(sg) * wSum <= w)
            {
                lightTypeIndex = cand_lightTypeIndex;
                payload        = cand_payload;
                targetPdf      = cand_pHatAtNew;
            }
        }
        else
        {
            M += cellM;
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
// Persist a finished local reservoir as the new cell content. Used after the
// read+merge path: the local already contains (fresh + home + neighbours),
// so we overwrite the cell rather than re-merge (would double-count).
// Soft-collision protection: only write if the slot is empty or claimed by
// the same fingerprint. M is capped on the way out.
// ---------------------------------------------------------------------------
void wsWriteCellFromLocal(WSCellAddress addr, WSLocalReservoir local)
{
    if (gWSCapacity == 0u || local.M <= 0.f) return;

    WSReservoir existing = gWSReservoirs[addr.slot];
    if (existing.fingerprint != 0u && existing.fingerprint != addr.fingerprint) return;

    WSReservoir cell = wsReservoirInit(addr.fingerprint);
    cell.lightTypeIndex   = local.lightTypeIndex;
    cell.payload          = local.payload;
    cell.targetPdf        = local.targetPdf;
    cell.M                = min(local.M, gWSMCap);
    float pHat = max(local.targetPdf, 1e-12f);
    cell.W                = (local.M > 0.f) ? (local.wSum / (pHat * local.M)) : 0.f;
    cell.frameLastUpdated = gFrameCount;
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
// Spatial gather: enumerate up to 4 neighbour cells in the same cascade
// level, offset by ±1 in two axes (chosen jittered by the sample generator
// so per-pixel gather patterns decorrelate). The four directional offsets
// span the cell's 4 face-adjacent neighbours; we pick 0..gWSSpatialNeighbours
// of them.
//
// Returns the (slot, fingerprint) for the i-th neighbour cell. The caller
// is responsible for loading and validating the slot like the home cell.
// ---------------------------------------------------------------------------
WSCellAddress wsResolveNeighbourCell(float3 posA, uint i, uint axisJitter)
{
    int lvl = wsCascadeLevel();
    int3 q = wsQuantizePosA(posA, lvl);
    // 4 face neighbours along x/y/z, with the unused axis chosen by the
    // jitter to spread coverage. Pattern: ±x, ±y, ±z, alternating.
    static const int3 kOffsets[6] = {
        int3( 1, 0, 0), int3(-1, 0, 0),
        int3( 0, 1, 0), int3( 0,-1, 0),
        int3( 0, 0, 1), int3( 0, 0,-1),
    };
    int3 off = kOffsets[(i + axisJitter) % 6u];
    int3 qN = q + off;
    WSCellAddress a;
    a.slot        = wsAddressHash(qN, lvl) & (gWSCapacity - 1u);
    a.fingerprint = wsFingerprintHash(qN, lvl);
    return a;
}


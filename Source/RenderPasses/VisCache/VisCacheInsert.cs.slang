/***************************************************************************
 * VisCacheInsert.cs.slang
 *
 * Batched insert pass — called once per frame to flush deferred inserts.
 * SM 6.5: WaveMatch coalesces threads targeting the same L0 cell into
 * a single InterlockedAdd (~16x reduction in atomics at L0).
 *
 * Also used as a standalone insert from within the path tracer shading
 * pass via the vhfInsertImmediate() inline function below.
 ***************************************************************************/

import VisCache;

// Structured buffer of pending (posA, posB, V) triples from the shading pass.
// Filled by path tracer, consumed here.
struct PendingInsert
{
    float3 posA;
    float3 posB;
    float  V;
    uint   _pad;
};

StructuredBuffer<PendingInsert>  gPendingInserts;
RWStructuredBuffer<uint>         gPendingCount;   // [0] = count
cbuffer InsertCB { float3 gCamPos; uint _p; }

[numthreads(64, 1, 1)]
void csInsert(uint3 tid : SV_DispatchThreadID)
{
    uint count = gPendingCount[0];
    if (tid.x >= count) return;

    PendingInsert ins = gPendingInserts[tid.x];

    // Distance-gated LOD range
    int lo, hi;
    vhfDistLOD(ins.posA, gCamPos, lo, hi);

    for (int lvl = lo; lvl <= hi; lvl++)
    {
        int3 qa = jitterQuantize(ins.posA, kCellA[lvl], 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(ins.posB, kCellB[lvl], 0xBBu ^ uint(lvl));

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));

        // SM 6.5 WaveMatch: identify lanes targeting the same cell
        // and let only the first lane in each group perform the atomic.
        // This reduces atomic contention ~16x at L0 where many pixels
        // share the same 10m cell.
        uint4 match = WaveMatch(addr);
        if (WaveMultiPrefixCountBits(true, match) == 0u)
        {
            // Count visible and total samples across matching lanes
            uint visSum   = WaveMultiPrefixCountBits(ins.V > 0.5f, match)
                          + (ins.V > 0.5f ? 1u : 0u);
            uint totalSum = countbits(match.x) + countbits(match.y)
                          + countbits(match.z) + countbits(match.w);

            int slot = vhfFindSlot(addr, fp, /*allowInsert=*/true);
            if (slot >= 0)
            {
                if (gVHFTable[slot].fingerprint == 0u)
                    gVHFTable[slot].fingerprint = fp;

                uint delta = (visSum << 16u) | totalSum;
                uint prev;
                InterlockedAdd(gVHFTable[slot].packed, delta, prev);

                // Inline overflow decay (see VisCache.slang §8)
                uint cur = prev + delta;
                if ((cur & 0xFFFFu) > 0xE000u)
                {
                    uint sub = ((cur >> 19u) << 16u) | ((cur & 0xFFFFu) >> 3u);
                    InterlockedAdd(gVHFTable[slot].packed, -sub);
                }
            }
        }
    }
}

/***************************************************************************
 * VisCacheInsert.cs.slang
 *
 * Batched insert pass — called once per frame to flush deferred inserts.
 * SM 6.5: WaveMatch coalesces threads targeting the same cell into
 * a single InterlockedAdd (~16x reduction in atomics at the coarsest level).
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
[numthreads(64, 1, 1)]
void csInsert(uint3 tid : SV_DispatchThreadID)
{
    uint count = gPendingCount[0];
    if (tid.x >= count) return;

    PendingInsert ins = gPendingInserts[tid.x];

    // Full N-level cascade with maturity gate + WaveMatch coalescing.
    for (int lvl = 0; lvl < int(gNumLevels); lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa, qb;
        vhfQuantizePair(ins.posA, ins.posB, cs, uint(lvl), qa, qb);

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));

        // Maturity gate before WaveMatch — all lanes need to agree on skip.
        if (vhfIsMature(addr, fp)) continue;

        // SM 6.5 WaveMatch: identify lanes targeting the same cell
        // and let only the first lane in each group perform the atomic.
        // This reduces atomic contention ~16x at coarse levels where
        // many pixels share the same cell.
        uint4 match = WaveMatch(addr);
        if (WaveMultiPrefixCountBits(true, match) == 0u)
        {
            // Count visible and total samples across matching lanes
            uint visSum   = WaveMultiPrefixCountBits(ins.V > 0.5f, match)
                          + (ins.V > 0.5f ? 1u : 0u);
            uint totalSum = countbits(match.x) + countbits(match.y)
                          + countbits(match.z) + countbits(match.w);

            // Re-find slot with insert allowed (may need to allocate)
            int wslot = vhfFindSlot(addr, fp, /*allowInsert=*/true);
            if (wslot >= 0)
            {
                uint origFp;
                InterlockedCompareExchange(gVHFTable[wslot].fingerprint, 0u, fp, origFp);
                if (origFp != 0u && origFp != fp) continue;

                uint delta = (visSum << 16u) | totalSum;
                uint prev;
                InterlockedAdd(gVHFTable[wslot].packed, delta, prev);
                vhfOverflowDecay(wslot, prev + delta);
            }
        }
    }
}

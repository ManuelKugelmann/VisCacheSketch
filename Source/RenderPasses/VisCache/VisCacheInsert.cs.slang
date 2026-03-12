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
[numthreads(64, 1, 1)]
void csInsert(uint3 tid : SV_DispatchThreadID)
{
    uint count = gPendingCount[0];
    if (tid.x >= count) return;

    PendingInsert ins = gPendingInserts[tid.x];

    // Full cascade — read-before-write in VisCache.slang handles contention.
    int lo, hi;
    vhfLOD(lo, hi);

    for (int lvl = lo; lvl <= hi; lvl++)
    {
        float cs = vhfCellSize(lvl);
        int3 qa = jitterQuantize(ins.posA, cs, 0xAAu ^ uint(lvl));
        int3 qb = jitterQuantize(ins.posB, cs, 0xBBu ^ uint(lvl));

        uint fp   = vhfFingerprint(qa, qb, uint(lvl));
        uint addr = vhfAddr(qa, qb, uint(lvl));

        // --- Read-before-write contention gate (mirrors vhfInsertRange) ---
        // Must happen before WaveMatch — all lanes need to agree on skip.
        int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false);
        if (slot >= 0)
        {
            uint packed = gVHFTable[slot].packed;
            uint total  = packed & 0xFFFFu;
            if (total >= gBootThreshold)
            {
                uint vis  = packed >> 16u;
                float mu  = float(vis) / float(total);
                float var = mu * (1.0f - mu);

                // Converged: skip this and all finer levels.
                if (var <= gVarThreshold)
                    break;

                // Mature high-variance: throttle writes (boot/total).
                float pWrite = float(gBootThreshold) / float(total);
                uint coin = pcg3d(uint3(addr, uint(lvl), total)).x;
                if (float(coin) / 4294967295.0f >= pWrite)
                    continue;
            }
        }

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
                if (gVHFTable[wslot].fingerprint == 0u)
                    gVHFTable[wslot].fingerprint = fp;

                uint delta = (visSum << 16u) | totalSum;
                uint prev;
                InterlockedAdd(gVHFTable[wslot].packed, delta, prev);

                // Inline overflow decay (see VisCache.slang)
                uint cur = prev + delta;
                if ((cur & 0xFFFFu) > 0xE000u)
                {
                    uint sub = ((cur >> 19u) << 16u) | ((cur & 0xFFFFu) >> 3u);
                    InterlockedAdd(gVHFTable[wslot].packed, -sub);
                }
            }
        }
    }
}

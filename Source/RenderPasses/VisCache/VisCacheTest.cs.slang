/***************************************************************************
 * VisCacheTest.cs.slang — Synthetic hash table round-trip test.
 *
 * Two entry points, dispatched sequentially by the host:
 *
 *   csTestInsert: writes synthetic entries at known (qa, qb) pairs
 *                 derived from pixel coordinates (no scene data needed).
 *
 *   csTestVerify: reads back those entries and writes per-pixel results
 *                 to a diagnostic texture. Green=found, Red=miss.
 *
 * This isolates hash addressing, fingerprinting, atomics, and eviction
 * from scene geometry, BVH, ray tracing, and renderer dispatch patterns.
 *
 * Test modes (gTestMode):
 *   0: identity — qa = pixel, qb = pixel + offset. 1 entry per pixel.
 *   1: shared coarse cell — all pixels in a 16x16 block share qa.
 *      Tests atomic contention (many threads → same slot).
 *   2: sequential slots — qa = (tid, 0, 0), qb = (0, 0, 0).
 *      Tests probe chain behavior with dense sequential addresses.
 *   3: read-after-write in same dispatch — insert then immediately lookup.
 *      Tests within-dispatch visibility of writes.
 ***************************************************************************/

import RenderPasses.VisCache.VisCache;

RWTexture2D<float4> gTestOutput;   ///< Result: R=found, G=probeSteps/8, B=total/255, A=1

cbuffer TestCB
{
    uint2 gFrameDim;
    uint  gTestMode;
    uint  gTestSeed;     ///< Varies per frame to detect temporal instability
};

// Synthetic key pair from pixel coordinate
void getTestPair(uint2 pixel, out int3 qa, out int3 qb)
{
    if (gTestMode == 1u)
    {
        // Shared coarse cell: 16x16 pixel blocks share the same qa
        qa = int3(pixel.x >> 4u, pixel.y >> 4u, 0);
        qb = int3(pixel.x >> 4u, pixel.y >> 4u, 1);
    }
    else if (gTestMode == 2u)
    {
        // Sequential: unique qa per thread, constant qb
        uint tid = pixel.y * gFrameDim.x + pixel.x;
        qa = int3(int(tid), 0, 0);
        qb = int3(0, 0, 0);
    }
    else
    {
        // Identity: unique pair per pixel
        qa = int3(int(pixel.x), int(pixel.y), 0);
        qb = int3(int(pixel.x) + 100, int(pixel.y) + 100, int(gTestSeed));
    }
}

// -----------------------------------------------------------------------
// Pass 1: Insert synthetic entries
// -----------------------------------------------------------------------
[numthreads(16, 16, 1)]
void csTestInsert(uint3 tid : SV_DispatchThreadID)
{
    uint2 pixel = tid.xy;
    if (any(pixel >= gFrameDim)) return;

    int3 qa, qb;
    getTestPair(pixel, qa, qb);

    uint fp   = vhfFingerprint(qa, qb, 0u);
    uint addr = vhfAddr(qa, qb, 0u);

    uint _ps;
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/true, _ps);
    if (slot < 0) return;  // Table full

    // Claim slot
    uint origFp;
    InterlockedCompareExchange(gVHFTable[slot].fingerprint, 0u, fp, origFp);
    if (origFp == 0u || origFp == fp)
    {
        // Empty or match — add one sample (visible)
        InterlockedAdd(gVHFTable[slot].packed, (1u << 16u) | 1u);
    }
    // Don't evict in the test — we want to see if entries survive
}

// -----------------------------------------------------------------------
// Pass 2: Verify — lookup each pixel's entry and report result
// -----------------------------------------------------------------------
[numthreads(16, 16, 1)]
void csTestVerify(uint3 tid : SV_DispatchThreadID)
{
    uint2 pixel = tid.xy;
    if (any(pixel >= gFrameDim)) return;

    int3 qa, qb;
    getTestPair(pixel, qa, qb);

    uint fp   = vhfFingerprint(qa, qb, 0u);
    uint addr = vhfAddr(qa, qb, 0u);

    uint probeSteps;
    int slot = vhfFindSlot(addr, fp, /*allowInsert=*/false, probeSteps);

    if (slot < 0)
    {
        // MISS — entry not found (red)
        gTestOutput[pixel] = float4(1.f, 0.f, 0.f, 1.f);
        return;
    }

    uint packed = gVHFTable[slot].packed;
    uint total  = packed & 0xFFFFu;
    uint vis    = packed >> 16u;

    if (total == 0u)
    {
        // Slot found but empty packed (yellow — fingerprint present, data missing)
        gTestOutput[pixel] = float4(1.f, 1.f, 0.f, 1.f);
        return;
    }

    // HIT — entry found with data (green, brightness = sample count)
    gTestOutput[pixel] = float4(
        0.f,                                           // R: 0 = no error
        0.5f + 0.5f * float(probeSteps) / 8.f,       // G: green + probe depth
        saturate(float(total) / 255.f),               // B: sample count
        1.f
    );
}

// -----------------------------------------------------------------------
// Pass 3: Insert + immediate lookup in same dispatch (mode 3)
// Tests within-dispatch write visibility
// -----------------------------------------------------------------------
[numthreads(16, 16, 1)]
void csTestInsertAndVerify(uint3 tid : SV_DispatchThreadID)
{
    uint2 pixel = tid.xy;
    if (any(pixel >= gFrameDim)) return;

    int3 qa, qb;
    getTestPair(pixel, qa, qb);

    uint fp   = vhfFingerprint(qa, qb, 0u);
    uint addr = vhfAddr(qa, qb, 0u);

    // Insert
    uint _ps;
    int wslot = vhfFindSlot(addr, fp, /*allowInsert=*/true, _ps);
    if (wslot >= 0)
    {
        uint origFp;
        InterlockedCompareExchange(gVHFTable[wslot].fingerprint, 0u, fp, origFp);
        if (origFp == 0u || origFp == fp)
            InterlockedAdd(gVHFTable[wslot].packed, (1u << 16u) | 1u);
    }

    // Immediate lookup (same thread, same dispatch)
    uint probeSteps;
    int rslot = vhfFindSlot(addr, fp, /*allowInsert=*/false, probeSteps);

    if (rslot < 0)
    {
        gTestOutput[pixel] = float4(1.f, 0.f, 0.f, 1.f);  // Red: miss after insert (BAD)
        return;
    }

    uint total = gVHFTable[rslot].packed & 0xFFFFu;
    gTestOutput[pixel] = float4(
        0.f,
        0.5f + 0.5f * float(probeSteps) / 8.f,
        saturate(float(total) / 255.f),
        1.f
    );
}

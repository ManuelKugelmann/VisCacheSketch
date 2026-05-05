/***************************************************************************
 * WSReservoirBoilingFilter.cs.slang
 *
 * §9.4 RTXDI BoilingFilter port — workgroup-shared statistical outlier
 * rejection on per-pixel reservoirs. Algorithm adapted from
 * Falcor/.../rtxdi/ResamplingFunctions.hlsli:1001 (RTXDI source untouched
 * per "leave original as is" directive).
 *
 * What it does:
 *   At the start of frame N+1, sweep the per-pixel reservoir buffer that
 *   PathTracer raygen wrote in frame N. For each 16×16 tile, compute the
 *   mean of nonzero W values, then empty any reservoir whose W exceeds
 *   `mean × multiplier`. This prevents single-pixel outliers from
 *   propagating outward through next-frame temporal+spatial reuse —
 *   the visual "boiling" artifact RTXDI's filter is named after.
 *
 *   multiplier = 10/strength - 9
 *   strength = 0.2 (RTXDI default) → multiplier = 41 → tolerates up to
 *   41× the local average before treating a reservoir as a firefly.
 *
 * Pattern: structurally identical to VisCacheDecay.cs.slang — frame-start
 * maintenance compute pass, dispatched from VisCache::execute(),
 * operates in-place on a persistent buffer that next frame reads.
 ***************************************************************************/

import RenderPasses.VisCache.WSReservoir;

RWStructuredBuffer<WSReservoir> gWSPixelReservoirs;

cbuffer WSBoilingFilterCB
{
    uint2 gFrameDim;        ///< (W, H) for bounds clamp on partial tiles
    float gFilterStrength;  ///< (0..1] — RTXDI default 0.2 → 41× threshold
};

static const uint kGroupSize = 16u;
static const uint kThreadsPerGroup = kGroupSize * kGroupSize;
// Wave-aggregate slots: one float/uint per wave. 32-lane waves → 8 slots
// for a 256-thread group; 16-lane waves → 16 slots. Use the upper bound.
groupshared float s_weights[(kThreadsPerGroup + 15) / 16];
groupshared uint  s_counts [(kThreadsPerGroup + 15) / 16];

[numthreads(kGroupSize, kGroupSize, 1)]
void csBoilingFilter(uint3 dtid : SV_DispatchThreadID, uint3 gid : SV_GroupThreadID)
{
    bool inBounds = all(dtid.xy < gFrameDim);
    uint pIdx = dtid.y * gFrameDim.x + dtid.x;

    WSReservoir r;
    bool hasWeight = false;
    float w = 0.f;
    if (inBounds)
    {
        r = gWSPixelReservoirs[pIdx];
        // A reservoir contributes to the mean if it carries non-trivial
        // weight: M > 0 AND W > 0. fingerprint=0 means uninitialized.
        hasWeight = (r.fingerprint != 0u) && (r.M > 0.f) && (r.W > 0.f);
        w = hasWeight ? r.W : 0.f;
    }

    // (1) Wave-level reduction.
    float waveSum = WaveActiveSum(w);
    uint  waveCnt = WaveActiveCountBits(hasWeight);

    uint linearIdx = gid.x + gid.y * kGroupSize;
    uint laneCount = WaveGetLaneCount();
    uint waveIdx   = linearIdx / laneCount;

    if (WaveIsFirstLane())
    {
        s_weights[waveIdx] = waveSum;
        s_counts [waveIdx] = waveCnt;
    }
    GroupMemoryBarrierWithGroupSync();

    // (2) Group-level reduction across waves — one wave does the second pass.
    uint waveSlots = (kThreadsPerGroup + laneCount - 1u) / laneCount;
    if (linearIdx < waveSlots)
    {
        float ws = s_weights[linearIdx];
        uint  wc = s_counts [linearIdx];
        ws = WaveActiveSum(ws);
        wc = WaveActiveSum(wc);
        if (linearIdx == 0u)
        {
            s_weights[0] = (wc > 0u) ? (ws / float(wc)) : 0.f;
        }
    }
    GroupMemoryBarrierWithGroupSync();

    // (3) Per-pixel threshold. Empty outliers so next frame's temporal +
    // spatial reuse can't propagate them. We don't zero the fingerprint —
    // that would mark the slot uninitialized; wsReservoirInit(0) leaves
    // fingerprint=0 which is also "empty", and the reuse path checks W=0/M=0
    // either way. Use the existing initializer for consistency.
    if (!inBounds || !hasWeight) return;
    float avgW = s_weights[0];
    if (avgW <= 0.f) return;
    float multiplier = 10.f / max(gFilterStrength, 1e-6f) - 9.f;
    if (r.W > avgW * multiplier)
    {
        gWSPixelReservoirs[pIdx] = wsReservoirInit(0u);
    }
}

/***************************************************************************
 * ReservoirBoilingFilter.cs.slang  —  DISABLED 2026-05-05
 *
 * §9.4 RTXDI BoilingFilter port (workgroup-shared statistical outlier
 * rejection on per-pixel reservoirs). Algorithm copied from
 * Falcor/.../rtxdi/ResamplingFunctions.hlsli:1001 per "leave original as is"
 * directive.
 *
 * STATUS: BLOCK-COMMENTED. Dispatch fires, build is clean, smoke passes,
 * but shader writes to gPixelReservoirs do not reach the buffer:
 *   - Host-side clearUAV() on the same buffer at the same dispatch site
 *     moves the metric (Sponza_x4 6.49 → 6.39, −0.10pp). Buffer mutation
 *     from the host works.
 *   - Shader-side writes (full RTXDI algorithm, minimal unconditional
 *     clear, sanity strength=1.0) all give 6.47–6.49 (within noise).
 *     Writes never land.
 *   - Suspected root cause: locally-redeclared `RWStructuredBuffer` global
 *     here vs the working module-imported `gVHFTable` pattern in
 *     VisCacheDecay.cs.slang. Slang reflection / Falcor binding may treat
 *     the two paths differently.
 *
 * Why disabled rather than left "almost working":
 *   A silent no-op filter is a *worse* failure mode than no filter at all
 *   — it presents as a safety net that could hide future algorithm
 *   regressions (firefly leaks, biased reservoir merges) by giving the
 *   illusion of outlier rejection that never actually runs. Per directive
 *   2026-05-05: "safety net might hide algorithm failures".
 *
 * Future fix path (the "separable-include" approach):
 *   Move the `RWStructuredBuffer<Reservoir> gPixelReservoirs;`
 *   declaration out of ReservoirIO.slang into its own tiny
 *   `PixelReservoirBuffer.slang` includable module. Have both
 *   ReservoirIO and a fixed BoilingFilter import THAT module
 *   (mirroring the VisCacheDecay → VisCache.slang `gVHFTable` pattern).
 *   That eliminates the locally-redeclared-global suspect and gives one
 *   canonical declaration site to bind against.
 *
 * Until then: this file is wrapped in `#if 0 ... #endif`, no entry point
 * is exported, and VisCache.cpp does not create or dispatch it.
 ***************************************************************************/

// ╔══════════════════════════════════════════════════════════════════════╗
// ║                                                                        ║
// ║   ████████  DISABLED 2026-05-05 — see header for diagnosis  ████████   ║
// ║                                                                        ║
// ║   The body below is wrapped in `#if 0 ... #endif`. Slang sees no       ║
// ║   entry point. VisCache.cpp does not create or dispatch this pass.     ║
// ║                                                                        ║
// ╚══════════════════════════════════════════════════════════════════════╝
#if 0  // DISABLED — see header.

import RenderPasses.ReSTIRCommon.Reservoir;

RWStructuredBuffer<Reservoir> gPixelReservoirs;

cbuffer BoilingFilterCB
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

    Reservoir r;
    bool hasWeight = false;
    float w = 0.f;
    if (inBounds)
    {
        r = gPixelReservoirs[pIdx];
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
    // spatial reuse can't propagate them.
    if (!inBounds || !hasWeight) return;
    float avgW = s_weights[0];
    if (avgW <= 0.f) return;
    float multiplier = 10.f / max(gFilterStrength, 1e-6f) - 9.f;
    if (r.W > avgW * multiplier)
    {
        gPixelReservoirs[pIdx] = reservoirInit(0u);
    }
}

#endif  // DISABLED — see header.
// ╚═════════════════ end disabled block: BoilingFilter shader ═════════════╝

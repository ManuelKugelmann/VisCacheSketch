/***************************************************************************
 * VisHashDecay.cs.slang
 *
 * Background decay pass — traverses 1/N of the table per frame.
 * Needed only for animated scenes with moving lights/geometry.
 * For single-frame or static rendering: set decayPeriod = 0.
 *
 * Half-life is controlled by DECAY_PERIOD (frames):
 *   Fast action scenes:        15 frames
 *   Architectural walkthrough: 300 frames
 *
 * The PI controller in VisHashFilter.cpp auto-tunes decayPeriod based
 * on smoothed load pressure (eviction/insert ratio).
 * Quality knobs (gVarThreshold, gPMin) are never auto-tuned.
 ***************************************************************************/

import VisHashFilter;

cbuffer DecayCB
{
    uint gDecayOffset;   // Which slice of the table to process this frame
    uint gDecayStride;   // = tableCapacity / decayPeriod
    float gDecayFactor;  // 0.875 = subtract 1/8 of both counters
}

[numthreads(64, 1, 1)]
void csDecay(uint3 tid : SV_DispatchThreadID)
{
    uint slot = gDecayOffset + tid.x;
    if (slot >= gTableCapacity) return;

    VHFEntry e = gVHFTable[slot];
    if (e.packed == 0u) return;

    uint total = e.packed & 0xFFFFu;
    uint vis   = e.packed >> 16u;

    // Subtract 1/8 of both counters (integer shift, mean preserved ~0.003%)
    uint decayVis   = vis   >> 3u;
    uint decayTotal = total >> 3u;

    if (decayTotal == 0u)
    {
        // Total would underflow — clear the entry entirely
        gVHFTable[slot].fingerprint = 0u;
        gVHFTable[slot].packed      = 0u;
    }
    else
    {
        uint sub = (decayVis << 16u) | decayTotal;
        InterlockedAdd(gVHFTable[slot].packed, -sub);
    }
}

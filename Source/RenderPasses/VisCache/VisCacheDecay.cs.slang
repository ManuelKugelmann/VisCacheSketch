/***************************************************************************
 * VisCacheDecay.cs.slang
 *
 * Background decay compute pass — processes 1/decayPeriod of the hash
 * table per frame, so the full table is swept once every decayPeriod frames.
 *
 * Why decay is needed:
 *   In animated scenes (moving geometry, changing lights), cached visibility
 *   can become stale. Without decay, the cache remembers outdated visibility
 *   indefinitely, causing shadow lag or ghost shadows.
 *
 *   Decay solves this by periodically shrinking both counters (vis and total)
 *   by a fraction (1/8 with kDecayShift=3). This has two effects:
 *     1. Old samples are gradually forgotten, letting new samples dominate
 *     2. Mature entries become immature again, triggering revalidation
 *        (the maturity gate in vhfInsert reopens, accepting new writes)
 *
 * How decay preserves the mean:
 *   Both counters are multiplied by the same factor (7/8), so the ratio
 *   vis/total (the mean) is preserved to within rounding error (~0.003%).
 *   The entry effectively "forgets" its oldest 1/8 of history while
 *   retaining the current visibility estimate.
 *
 * Decay strength vs. scene dynamics:
 *   Fast action scenes:        decayPeriod = 15 frames (aggressive)
 *   Architectural walkthrough: decayPeriod = 300 frames (gentle)
 *   Static rendering:          decayPeriod = 0 (disabled)
 *
 * The PI controller in VisCache.cpp auto-tunes decayPeriod based on
 * smoothed eviction/insert ratio (load pressure). When the table is
 * under pressure (high eviction rate), decay speeds up to free stale
 * entries. Quality parameters (varThreshold, pMin) are never auto-tuned.
 ***************************************************************************/

import VisCache;

/// Per-frame decay parameters, set by VisCache::runDecayPass().
/// gDecayOffset: starting slot index for this frame's slice.
/// gDecayStride: number of slots to process (= tableCapacity / decayPeriod).
cbuffer DecayCB
{
    uint gDecayOffset;   ///< First slot to process this frame
    uint gDecayStride;   ///< Number of slots in this frame's slice
};

[numthreads(64, 1, 1)]
void csDecay(uint3 tid : SV_DispatchThreadID)
{
    uint slot = gDecayOffset + tid.x;
    if (slot >= gTableCapacity) return;  // Bounds check — last slice may be partial

    VHFEntry e = gVHFTable[slot];
    if (e.packed == 0u) return;  // Empty slot — nothing to decay

    uint total = e.packed & 0xFFFFu;
    uint vis   = e.packed >> 16u;

    // Compute decay amounts: subtract 1/(1<<kDecayShift) of each counter.
    // kDecayShift=3 → keep 7/8, forget 1/8 per decay sweep.
    // Both counters are decayed by the same fraction, preserving the mean.
    uint decayVis   = vis   >> kDecayShift;
    uint decayTotal = total >> kDecayShift;

    if (decayTotal == 0u)
    {
        // Total would underflow to zero — clear the entry entirely.
        // This reclaims the slot for new entries (fingerprint = 0 means empty).
        // Clearing fingerprint non-atomically is safe here because:
        //   - The slot has total <= (1<<kDecayShift)-1 samples (very few)
        //   - Concurrent readers see packed=0 and bail out
        //   - Concurrent writers re-check fingerprint via CAS
        gVHFTable[slot].fingerprint = 0u;
        gVHFTable[slot].packed      = 0u;
    }
    else
    {
        // Subtract decay amounts atomically. Using InterlockedAdd(-sub)
        // instead of direct write because concurrent inserts may be adding
        // to this slot simultaneously.
        uint sub = (decayVis << 16u) | decayTotal;
        InterlockedAdd(gVHFTable[slot].packed, -sub);
    }
}

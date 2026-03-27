/***************************************************************************
 * VisCacheDiagnostics.slang
 *
 * Per-pixel diagnostic output for VisCache heatmap visualization.
 *
 * Per-frame outputs (cleared each frame by host):
 *   gVCFrameMeanVarMatSamplesRaw      (RGBA32Float) — R=variance*4, G=maturity, B=mean, A=samplesRaw
 *   gVCFrameLevelProbesSamplesCold    (RGBA32Float) — R=level, G=probeSteps, B=samples, A=coldmiss
 *   gVCFrameHashAHashBHashABRays      (RGBA32Float) — R=posAHash, G=posBHash, B=combinedHash, A=raysTraced
 *
 * Accumulated outputs (persistent across frames):
 *   gVCAccumMeanVarMatCount           (RGBA32Float) — R=variance*4, G=maturity, B=mean, A=sampleCount
 *   gVCAccumRaysNoiseErrorCold        (RGBA32Float) — R=raysTraced, G=renderNoise, B=renderError, A=coldmiss
 *   gVCAccumSaved     (R32Uint)     — per-pixel count of saved rays
 *   gVCAccumTotal     (R32Uint)     — per-pixel count of total queries
 *
 * Usage:
 *   Import this file in any pass that calls vhfGate/vhfCommit and bind
 *   the textures from dictionary keys listed above.
 *   Call vcWriteDiag() after the gate/commit sequence.
 ***************************************************************************/

#pragma once

import RenderPasses.VisCache.VisCache;

// --- Per-frame snapshot outputs (overwritten each frame) ---
RWTexture2D<float4> gVCFrameMeanVarMatSamplesRaw;          ///< R=variance*4, G=maturity, B=mean, A=samplesRaw
RWTexture2D<float4> gVCFrameLevelProbesSamplesCold;        ///< R=level, G=probeSteps, B=sampleCount, A=coldmiss
RWTexture2D<float4> gVCFrameHashAHashBHashABRays;          ///< R=posAHash, G=posBHash, B=combinedHash, A=raysTraced

// --- Accumulated outputs (persistent, NOT cleared per frame) ---
RWTexture2D<float4> gVCAccumMeanVarMatCount;               ///< R=variance*4, G=maturity, B=mean, A=count (online mean bookkeeping)
RWTexture2D<float4> gVCAccumRaysNoiseErrorCold;            ///< R=raysTraced, G=renderNoise(TBD), B=renderError(TBD), A=coldmiss
RWTexture2D<uint>   gVCAccumSaved;                         ///< Internal: per-pixel saved ray count
RWTexture2D<uint>   gVCAccumTotal;                         ///< Internal: per-pixel total query count

/// Write per-pixel diagnostics after a vhfGate/vhfCommit sequence.
/// @param pixel       Screen-space pixel coordinate.
/// @param g           Gate result from vhfGate() or vhfGateDeterministic().
/// @param traced      True if a shadow ray was actually traced.
/// @param V           Ground-truth visibility (only valid when traced=true).
void vcWriteDiag(uint2 pixel, VHFGateResult g, bool traced, float V,
                  float3 posA, float3 posB)
{
    bool noEntry = (g.level < 0);
    float diagVar = noEntry ? 0.f : g.var;
    float coldmiss = noEntry ? 1.f : 0.f;

    // --- Per-frame snapshots: bounce 0 only ---
    // Detect first bounce via hash texture (cleared to 0, nonzero after first write).
    bool firstBounce = (gVCFrameHashAHashBHashABRays[pixel].r == 0.f
                     && gVCFrameHashAHashBHashABRays[pixel].g == 0.f);
    if (firstBounce)
    {
        gVCFrameMeanVarMatSamplesRaw[pixel] = float4(
            noEntry ? 0.f : saturate(diagVar * 4.f),                      // R: variance [0,0.25]→[0,1]
            noEntry ? 0.f : saturate(float(g.N) / float(gBootThreshold)), // G: maturity [0,1]
            noEntry ? 0.f : g.mu,                                          // B: cached mu [0,1]
            noEntry ? 0.f : float(g.N)                                     // A: raw sample count
        );

        gVCFrameLevelProbesSamplesCold[pixel] = float4(
            noEntry ? 0.f : float(g.level + 1) / max(float(gNumLevels), 1.f),  // R: LOD level
            noEntry ? 0.f : saturate(float(g.probeSteps) / float(kMaxProbe)),   // G: probe steps
            noEntry ? 0.f : saturate(float(g.N) / float(gBootThreshold * 8u)),  // B: sample count
            coldmiss                                                             // A: cold miss
        );

        // Same functions as rendering — pcgHashA/B/Dist at level 0, no extra salt.
        uint posAHash = pcgHashA(g.qa, 0u);
        uint posBHash = pcgHashB(g.qb, 0u);
        uint combinedHash = posAHash ^ posBHash ^ pcgHashDist(0u);
        gVCFrameHashAHashBHashABRays[pixel] = float4(
            float(posAHash & 0xFFFFu) / 65535.f,                    // R: posA cell hash
            float(posBHash & 0xFFFFu) / 65535.f,                    // G: posB cell hash
            float(combinedHash & 0xFFFFu) / 65535.f,                // B: combined = vhfAddr at lvl 0
            traced ? 1.f : 0.f                                       // A: ray traced this frame
        );
    }

    // --- Accumulated outputs (persistent across frames) ---

    // Online mean: R=variance, G=maturity, B=mean, A=count.
    if (!noEntry)
    {
        float4 prev = gVCAccumMeanVarMatCount[pixel];
        float count = prev.a + 1.f;
        float alpha = 1.f / count;
        gVCAccumMeanVarMatCount[pixel] = float4(
            lerp(prev.r, saturate(diagVar * 4.f), alpha),
            lerp(prev.g, saturate(float(g.N) / float(gBootThreshold)), alpha),
            lerp(prev.b, g.mu, alpha),
            count
        );
    }

    // Ray counters + derived metrics
    uint saved = gVCAccumSaved[pixel] + (traced ? 0u : 1u);
    uint total = gVCAccumTotal[pixel] + 1u;
    gVCAccumSaved[pixel] = saved;
    gVCAccumTotal[pixel] = total;

    float accumRaysTracedRatio = float(total - saved) / float(total);
    float hitCount = gVCAccumMeanVarMatCount[pixel].a;
    float accumColdmissRate = 1.f - hitCount / max(float(total), 1.f);

    // Read previous accum values for G/B channels (renderNoise/renderError filled by host, preserved here)
    float4 prevAccum = gVCAccumRaysNoiseErrorCold[pixel];
    gVCAccumRaysNoiseErrorCold[pixel] = float4(
        accumRaysTracedRatio,       // R: accumulated ray traced ratio [0,1]
        prevAccum.g,                // G: renderNoise (filled by compute pass, preserved)
        prevAccum.b,                // B: renderError (filled by post-process, preserved)
        accumColdmissRate           // A: accumulated cold miss rate [0,1]
    );
}

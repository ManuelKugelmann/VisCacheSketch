/***************************************************************************
 * VisCacheDiagnostics.slang
 *
 * Per-pixel diagnostic output for VisCache heatmap visualization.
 *
 * Per-frame outputs (cleared each frame by host):
 *   gVCVarMaturityMu    (RGBA32Float) — R=var*4, G=maturity, B=mu, A=coldmiss
 *   gVCVarMaturityLevel (RGBA32Float) — R=probeSteps, G=sampleCount, B=level, A=unused
 *
 * Accumulated outputs (persistent across frames):
 *   gVCDiag           (RGBA32Float) — R=var*4, G=maturity, B=mu, A=sampleCount
 *   gVCAccumSaved     (R32Uint)     — per-pixel count of saved rays
 *   gVCAccumTotal     (R32Uint)     — per-pixel count of total queries
 *   gVCRaySavedRatio  (R32Float)    — ray traced ratio [0,1]
 *   gVCNoise          (R32Float)    — noise estimate (variance EMA)
 *
 * Usage:
 *   Import this file in any pass that calls vhfGate/vhfCommit and bind
 *   the textures from dictionary keys listed above.
 *   Call vcWriteDiag() after the gate/commit sequence.
 ***************************************************************************/

#pragma once

import RenderPasses.VisCache.VisCache;

// --- Per-frame outputs (cleared each frame) ---
RWTexture2D<float4> gVCDiag;              ///< Accumulated average: R=var*4, G=maturity, B=mu, A=sampleCount
RWTexture2D<float4> gVCVarMaturityLevel;  ///< R=probeSteps, G=sampleCount, B=level, A=unused
RWTexture2D<float4> gVCVarMaturityMu;     ///< R=var*4, G=maturity, B=mu, A=coldmiss

// --- Accumulated outputs (persistent, NOT cleared per frame) ---
RWTexture2D<uint>   gVCAccumSaved;     ///< Per-pixel saved ray count
RWTexture2D<uint>   gVCAccumTotal;     ///< Per-pixel total query count
RWTexture2D<float>  gVCRaySavedRatio;  ///< ray traced ratio: (total-saved)/total [0,1]
RWTexture2D<float>  gVCNoise;          ///< Per-pixel noise EMA (variance)

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

    // --- Snapshot composites (overwritten each frame — last stochastic sample) ---
    // Cold misses: var/maturity/mu stay at cleared 0, but A=coldmiss is always written.
    gVCVarMaturityMu[pixel] = float4(
        noEntry ? 0.f : saturate(diagVar * 4.f),                    // R: variance [0,0.25]→[0,1]
        noEntry ? 0.f : saturate(float(g.N) / float(gBootThreshold)), // G: maturity [0,1]
        noEntry ? 0.f : g.mu,                                        // B: cached mu [0,1]
        coldmiss                                                      // A: cold miss indicator
    );

    if (!noEntry)
    {
        gVCVarMaturityLevel[pixel] = float4(
            saturate(float(g.probeSteps) / float(kMaxProbe)),       // R: probe steps [0,maxProbe]→[0,1]
            saturate(float(g.N) / float(gBootThreshold * 8u)),      // G: sample count [0,8*boot]→[0,1]
            float(g.level + 1) / max(float(gNumLevels), 1.f),      // B: LOD level [0,N]→[0,1]
            1.f
        );
    }

    // --- Accumulated simple average (cleared by host between warmup and capture) ---
    // Same channel layout as snapshot: R=var, G=maturity, B=mu.
    // A = valid sample count. Cold misses excluded.
    if (!noEntry)
    {
        float4 prev = gVCDiag[pixel];
        float count = prev.a + 1.f;
        float alpha = 1.f / count;
        gVCDiag[pixel] = float4(
            lerp(prev.r, saturate(diagVar * 4.f), alpha),
            lerp(prev.g, saturate(float(g.N) / float(gBootThreshold)), alpha),
            lerp(prev.b, g.mu, alpha),
            count
        );
    }

    // --- Accumulate ray savings ratio (persistent across frames) ---
    uint saved = gVCAccumSaved[pixel] + (traced ? 0u : 1u);
    uint total = gVCAccumTotal[pixel] + 1u;
    gVCAccumSaved[pixel] = saved;
    gVCAccumTotal[pixel] = total;
    gVCRaySavedRatio[pixel] = float(total - saved) / float(total);

    // --- Noise estimate: EMA of cache variance ---
    {
        float ema = 1.f / float(min(total, 256u));
        float oldNoise = gVCNoise[pixel];
        gVCNoise[pixel] = lerp(oldNoise, g.var, ema);
    }
}

/***************************************************************************
 * VisCacheDiagnostics.slang
 *
 * Per-pixel diagnostic output for VisCache heatmap visualization.
 *
 * Per-frame outputs (cleared each frame, written by downstream passes):
 *   gVCDiag           (RGBA32Float) — R=cachedMu, G=variance, B=level, A=raySaved
 *   gVCDiagError      (R32Float)    — |mu - V| prediction error (only when traced)
 *   gVCVarMaturityLevel  (RGBA32Float) — pre-normalized RGB: R=var, G=maturity, B=level
 *   gVCVarMaturityMu (RGBA32Float) — pre-normalized RGB: R=var, G=maturity, B=mu
 *
 * Accumulated outputs (persistent across frames):
 *   gVCAccumSaved     (R32Uint)     — per-pixel count of saved rays
 *   gVCAccumTotal     (R32Uint)     — per-pixel count of total queries
 *   gVCRaySavedRatio  (R32Float)    — saved/total ratio [0,1]
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
RWTexture2D<float4> gVCDiag;           ///< R=mu, G=var, B=level+1 (0=miss), A=raySaved
RWTexture2D<float>  gVCDiagError;      ///< |mu - V| prediction error
RWTexture2D<float4> gVCVarMaturityLevel;  ///< Pre-normalized RGB (R=var, G=maturity, B=level)
RWTexture2D<float4> gVCVarMaturityMu; ///< Pre-normalized RGB (R=var, G=maturity, B=mu)

// --- Accumulated outputs (persistent, NOT cleared per frame) ---
RWTexture2D<uint>   gVCAccumSaved;     ///< Per-pixel saved ray count
RWTexture2D<uint>   gVCAccumTotal;     ///< Per-pixel total query count
RWTexture2D<float>  gVCRaySavedRatio;  ///< saved/total [0,1]
RWTexture2D<float>  gVCNoise;          ///< Per-pixel noise EMA (variance)

/// Write per-pixel diagnostics after a vhfGate/vhfCommit sequence.
/// @param pixel       Screen-space pixel coordinate.
/// @param g           Gate result from vhfGate() or vhfGateDeterministic().
/// @param traced      True if a shadow ray was actually traced.
/// @param V           Ground-truth visibility (only valid when traced=true).
void vcWriteDiag(uint2 pixel, VHFGateResult g, bool traced, float V)
{
    gVCDiag[pixel] = float4(
        g.mu,                           // R: cached mean visibility [0,1]
        g.var,                          // G: Bernoulli variance [0,0.25]
        float(g.level + 1),             // B: LOD level+1 (0=miss, 1=L0, 2=L1, ...)
        traced ? 0.f : 1.f             // A: 1=ray saved, 0=ray traced
    );

    gVCDiagError[pixel] = traced ? abs(g.mu - V) : 0.f;

    // Composite heatmap: 3 diagnostics in one RGB image, pre-normalized to [0,1].
    gVCVarMaturityLevel[pixel] = float4(
        saturate(g.var * 4.f),                              // R: variance / 0.25
        saturate(float(g.N) / float(gBootThreshold)),       // G: maturity
        float(g.level + 1) / float(gNumLevels),             // B: LOD level
        1.f
    );

    // Composite 2: same R,G but B = mu instead of level.
    gVCVarMaturityMu[pixel] = float4(
        saturate(g.var * 4.f),
        saturate(float(g.N) / float(gBootThreshold)),
        g.mu,                                                // B: cached mu
        1.f
    );

    // --- Accumulate ray savings ratio (persistent across frames) ---
    // No atomics needed: each pixel is processed by exactly one thread,
    // and dispatches from different passes are serialized.
    uint saved = gVCAccumSaved[pixel] + (traced ? 0u : 1u);
    uint total = gVCAccumTotal[pixel] + 1u;
    gVCAccumSaved[pixel] = saved;
    gVCAccumTotal[pixel] = total;
    gVCRaySavedRatio[pixel] = float(saved) / float(total);

    // --- Noise estimate: EMA of cache variance ---
    // Variance mu*(1-mu) measures shadow boundary uncertainty per pixel.
    // EMA smooths across frames (alpha = 1/total, Welford-like convergence).
    float alpha = 1.f / float(min(total, 256u));  // cap alpha to avoid slow start
    float oldNoise = gVCNoise[pixel];
    gVCNoise[pixel] = lerp(oldNoise, g.var, alpha);
}

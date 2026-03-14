/***************************************************************************
 * VisCacheDiagnostics.slang
 *
 * Per-pixel diagnostic output for VisCache heatmap visualization.
 *
 * Provides three RWTexture2D outputs:
 *   gVCDiag          (RGBA32Float) — R=cachedMu, G=variance, B=level, A=raySaved
 *   gVCDiagError     (R32Float)    — |mu - V| prediction error (only when traced)
 *   gVCDiagComposite (RGBA32Float) — pre-normalized RGB: R=mu, G=level/N, B=N/boot
 *
 * Usage:
 *   Import this file in any pass that calls vhfGate/vhfCommit and bind
 *   the textures from dictionary keys "vhfDiag", "vhfDiagError", "vhfDiagComposite".
 *   Call vcWriteDiag() after the gate/commit sequence.
 *
 *   Downstream visualization: connect VisCache outputs to ColorMapPass.
 *   ColorMapPass channel selector picks R/G/B/A for different heatmaps.
 ***************************************************************************/

#pragma once

import RenderPasses.VisCache.VisCache;

RWTexture2D<float4> gVCDiag;          ///< R=mu, G=var, B=level+1 (0=miss), A=raySaved
RWTexture2D<float>  gVCDiagError;    ///< |mu - V| prediction error
RWTexture2D<float4> gVCDiagComposite; ///< Pre-normalized RGB composite (R=mu, G=level, B=N)

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
    //   R = cached mu           (already [0,1])
    //   G = LOD level           (level+1 / numLevels, 0=miss → black)
    //   B = sample count        (N / bootThreshold, saturates at 1.0)
    gVCDiagComposite[pixel] = float4(
        g.mu,
        float(g.level + 1) / float(gNumLevels),
        saturate(float(g.N) / float(gBootThreshold)),
        1.f
    );
}

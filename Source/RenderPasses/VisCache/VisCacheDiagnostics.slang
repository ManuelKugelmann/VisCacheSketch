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
void vcWriteDiag(uint2 pixel, VHFGateResult g, bool traced, float V,
                  float3 posA, float3 posB)
{
    gVCDiagError[pixel] = traced ? abs(g.mu - V) : 0.f;

    // Show exactly what the algorithm sees — the gate result from vhfLookup.
    // No extra lookups. Three visual states:
    //   black (0,0,0)     = no write (no NEE, background, specular)
    //   mid-grey (0.3)    = true miss (no hash entry at all)
    //   colored            = entry exists — uses real mu/var/level/N data
    //                        (including immature entries below bootThreshold)
    bool noEntry = (g.level < 0);
    float grey = noEntry ? 0.3f : 0.f;
    float diagVar = noEntry ? 0.f : g.var;

    // --- gVCDiag: R=qa hash, G=qb hash — actual quantized keys used by the cache ---
    {
        float cs = vhfCellSize(0);
        int3 qa, qb;
        vhfQuantizePair(posA, posB, cs, 0u, qa, qb);

        uint3 hA = pcg3d(uint3(qa));
        uint3 hB = pcg3d(uint3(qb));

        gVCDiag[pixel] = float4(float(hA.x & 0xFFu) / 255.f,   // R: qa hash
                                 float(hB.x & 0xFFu) / 255.f,   // G: qb hash
                                 noEntry ? 0.f : 1.f,            // B: cold miss (0=miss, 1=data)
                                 1.f);
    }

    // Cold miss indicator: A=0 means true cold miss (no hash entry), A=1 means data exists.
    float coldMissAlpha = noEntry ? 0.f : 1.f;

    // --- Snapshot composites (overwritten each frame — last stochastic sample) ---
    // VarMaturityMu: R=variance, G=maturity, B=mu — cache quality snapshot
    gVCVarMaturityMu[pixel] = float4(
        saturate(diagVar * 4.f) + grey,                             // R: variance [0,0.25]→[0,1]
        saturate(float(g.N) / float(gBootThreshold)) + grey,       // G: maturity [0,1]
        g.mu + grey,                                                // B: cached mu [0,1]
        coldMissAlpha                                                // A: 0=cold miss, 1=has data
    );

    // VarMaturityLevel: R=probeSteps, G=sampleCount, B=level — hash health snapshot
    gVCVarMaturityLevel[pixel] = float4(
        saturate(float(g.probeSteps) / float(kMaxProbe)) + grey,   // R: probe steps [0,maxProbe]→[0,1]
        saturate(float(g.N) / float(gBootThreshold * 8u)) + grey,  // G: sample count [0,8*boot]→[0,1]
        float(g.level + 1) / max(float(gNumLevels), 1.f) + grey,  // B: LOD level [0,N]→[0,1]
        coldMissAlpha                                                // A: 0=cold miss, 1=has data
    );

    // --- Accumulated EMA (persists across frames) ---
    // Same channel layout as snapshot: R=var, G=maturity, B=mu.
    // A channel = valid sample count (cold misses NOT counted).
    // Only updates when the gate found an actual entry — cold misses
    // are excluded to avoid diluting shadows with default mu values.
    {
        float4 prev = gVCDiag[pixel];

        if (!noEntry)
        {
            float validCount = prev.a + 1.f;
            float alpha = (gDiagAccumWindow > 0u)
                ? 2.f / (float(gDiagAccumWindow) + 1.f)
                : 1.f / validCount;
            gVCDiag[pixel] = float4(
                lerp(prev.r, saturate(diagVar * 4.f), alpha),   // R: avg variance
                lerp(prev.g, saturate(float(g.N) / float(gBootThreshold)), alpha), // G: avg maturity
                lerp(prev.b, g.mu, alpha),                       // B: avg mu (no grey offset)
                validCount
            );
        }
        // Cold miss: don't update EMA, don't increment count.
        // The pixel retains its previous accumulated value.
    }

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

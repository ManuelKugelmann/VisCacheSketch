/***************************************************************************
 * VisCacheDiagPass.cs.slang — Per-pixel diagnostic compute pass.
 *
 * Runs AFTER downstream renderers have populated the hash table.
 * Reads the G-Buffer (surface positions) and queries the hash table
 * to produce per-pixel heatmaps of cache state.
 *
 * For each pixel with a valid surface hit, queries vhfLookup() using the
 * surface position and a probe direction derived from the surface normal.
 * This shows cache coverage, convergence, and LOD distribution without
 * needing the actual shadow ray endpoints (which are only known inside
 * the RT shader).
 ***************************************************************************/

import RenderPasses.VisCache.VisCache;

// G-Buffer input
Texture2D<float4> gWorldPos;     ///< Surface world position (xyz) + hit flag (w > 0)

// Diagnostic outputs (same textures as VisCacheDiagnostics.slang)
RWTexture2D<float4> gVCDiag;           ///< R=mu, G=var, B=level+1, A=raySaved
RWTexture2D<float>  gVCDiagError;      ///< Unused in deferred pass (no ground truth V)
RWTexture2D<float4> gVCVarMaturityLevel;  ///< var/maturity/level heatmap (R=var, G=maturity, B=level)
RWTexture2D<float4> gVCVarMaturityMu; ///< var/maturity/mu heatmap (R=var, G=maturity, B=mu)
RWTexture2D<uint>   gVCAccumSaved;     ///< Per-pixel saved ray count (not used here)
RWTexture2D<uint>   gVCAccumTotal;     ///< Per-pixel total query count (not used here)
RWTexture2D<float>  gVCRaySavedRatio;  ///< saved/total ratio
RWTexture2D<float>  gVCNoise;          ///< Cache variance at this pixel

cbuffer DiagCB
{
    uint2 gFrameDim;
    uint  gFrameCount;
};

[numthreads(16, 16, 1)]
void csDiag(uint3 tid : SV_DispatchThreadID)
{
    uint2 pixel = tid.xy;
    if (any(pixel >= gFrameDim)) return;

    float4 posW = gWorldPos[pixel];

    // No surface hit — write zeros
    if (posW.w == 0.f)
    {
        gVCDiag[pixel]           = float4(0.f);
        gVCDiagError[pixel]      = 0.f;
        gVCVarMaturityLevel[pixel]  = float4(0.f, 0.f, 0.f, 1.f);
        gVCVarMaturityMu[pixel] = float4(0.f, 0.f, 0.f, 1.f);
        gVCRaySavedRatio[pixel]  = 0.f;
        gVCNoise[pixel]          = 0.f;
        return;
    }

    // Probe direction: offset upward from surface position. This isn't the
    // actual shadow ray direction, but shows whether the cache has entries
    // near this surface point at each LOD level. The upward probe catches
    // overhead/environment lighting which is the most common case.
    float3 probeB = posW.xyz + float3(0.f, gCellACoarse, 0.f);
    VHFResult r = vhfLookup(posW.xyz, probeB);

    // Write per-pixel diagnostics from the lookup result.
    float raySavedEst = r.valid ? clamp(1.f - r.var / max(gVarThreshold, 0.01f), 0.f, 1.f) : 0.f;

    gVCDiag[pixel] = float4(
        r.mu,
        r.var,
        float(r.level + 1),
        raySavedEst
    );

    gVCDiagError[pixel] = 0.f;  // No ground truth V available in deferred pass

    gVCVarMaturityLevel[pixel] = float4(
        saturate(r.var * 4.f),                              // R: variance / 0.25
        r.valid ? saturate(float(r.N) / float(gBootThreshold)) : 0.f,  // G: maturity
        float(r.level + 1) / float(gNumLevels),             // B: LOD level
        1.f
    );

    gVCVarMaturityMu[pixel] = float4(
        saturate(r.var * 4.f),
        r.valid ? saturate(float(r.N) / float(gBootThreshold)) : 0.f,
        r.mu,                                                // B: cached mu
        1.f
    );

    gVCRaySavedRatio[pixel] = raySavedEst;
    gVCNoise[pixel]         = r.var;
}

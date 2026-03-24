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
import RenderPasses.VisCache.VisCacheDiagnostics; // Diagnostic texture declarations + vcWriteDiag

// G-Buffer input
Texture2D<float4> gWorldPos;     ///< Surface world position (xyz) + hit flag (w > 0)

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
        gVCAccumMeanVarMatCount[pixel]           = float4(0.f);
        gVCFrameLevelProbesSamplesCold[pixel]  = float4(0.f);
        gVCFrameMeanVarMatSamplesRaw[pixel] = float4(0.f, 0.f, 0.f, 0.f);
        gVCAccumRaysNoiseErrorCold[pixel] = float4(0.f, 0.f, 0.f, 1.f);  // A=1 = coldmiss (no surface)
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

    gVCAccumMeanVarMatCount[pixel] = float4(
        r.mu,
        r.var,
        float(r.level + 1),
        raySavedEst
    );

    gVCFrameLevelProbesSamplesCold[pixel] = float4(
        float(r.level + 1) / float(gNumLevels),             // R: LOD level
        0.f,                                                  // G: probe steps (not available in standalone query)
        r.valid ? saturate(float(r.N) / float(gBootThreshold * 8u)) : 0.f,  // B: samples (normalized)
        r.valid ? 0.f : 1.f                                   // A: coldmiss
    );

    gVCFrameMeanVarMatSamplesRaw[pixel] = float4(
        saturate(r.var * 4.f),
        r.valid ? saturate(float(r.N) / float(gBootThreshold)) : 0.f,
        r.mu,                                                // B: cached mu
        float(r.N)                                            // A: raw sample count
    );

    float4 prevAccumRNEC = gVCAccumRaysNoiseErrorCold[pixel];
    gVCAccumRaysNoiseErrorCold[pixel] = float4(
        raySavedEst,                // R: ray traced ratio
        prevAccumRNEC.g,            // G: renderNoise (preserved)
        prevAccumRNEC.b,            // B: renderError (preserved)
        r.valid ? 0.f : 1.f        // A: coldmiss
    );
}

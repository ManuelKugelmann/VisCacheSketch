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
 *   gVCAccumRaysSplitNeeReval         (RGBA32Float) — R=raysTraced_NEE, G=raysTraced_Reval, B+A reserved
 *   gVCAccumSaved          (R32Uint) — per-pixel count of saved rays (rolled up)
 *   gVCAccumTotal          (R32Uint) — per-pixel count of total queries (rolled up)
 *   gVCAccumSavedNEE       (R32Uint) — per-pixel saved-NEE-ray count
 *   gVCAccumTotalNEE       (R32Uint) — per-pixel total NEE queries
 *   gVCAccumSavedReval     (R32Uint) — per-pixel saved-revalidation-ray count
 *   gVCAccumTotalReval     (R32Uint) — per-pixel total revalidation queries
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
RWTexture2D<uint>   gVCAccumSaved;                         ///< Internal: per-pixel saved ray count (rolled up across call sites)
RWTexture2D<uint>   gVCAccumTotal;                         ///< Internal: per-pixel total query count (rolled up across call sites)

// Per-call-site counters: separate the cost of NEE shadow rays from the cost
// of temporal/spatial reservoir reuse-revalidation rays. Both pairs are
// always bumped alongside the rolled-up pair above — readers can pick the
// channel they need without breaking the existing single-counter consumers.
RWTexture2D<uint>   gVCAccumSavedNEE;
RWTexture2D<uint>   gVCAccumTotalNEE;
RWTexture2D<uint>   gVCAccumSavedReval;
RWTexture2D<uint>   gVCAccumTotalReval;
RWTexture2D<float4> gVCAccumRaysSplitNeeReval;             ///< R=NEE_ratio, G=Reval_ratio, B+A reserved

// Call-site tags for vcWriteDiag / vcDiagCountRay.
// Slang exports `static const` symbols across `import` boundaries but NOT
// `#define`s — keep these as constants so importers see them.
static const uint VC_RAY_SITE_NEE   = 0u;
static const uint VC_RAY_SITE_REVAL = 1u;

/// Write per-pixel diagnostics after a vhfGate/vhfCommit sequence.
/// @param pixel       Screen-space pixel coordinate.
/// @param g           Gate result from vhfGate() or vhfGateDeterministic().
/// @param traced      True if a shadow ray was actually traced.
/// @param V           Ground-truth visibility (only valid when traced=true).
/// @param callSite    VC_RAY_SITE_* — tags the bump for the split counters.
void vcWriteDiag(uint2 pixel, VHFGateResult g, bool traced, float V,
                  float3 posA, float3 posB, uint callSite = VC_RAY_SITE_NEE)
{
    // noEntry = no mature/trusted entry was found at the lookup level. The
    // queried cell coords (g.qa/qb) and level (g.level) ARE always set —
    // diag visualization can show what was queried even on cold misses.
    bool noEntry = !g.valid_data;
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

        // Raw cascade level (not normalized). Postprocess rescales to the
        // frame's observed [min, max] range so small variations are visible
        // even when all pixels land in a narrow band of levels (typical with
        // strided cascade where only ~32 discrete level values get used).
        float levelRaw = noEntry ? -1.f : float(g.level);
        gVCFrameLevelProbesSamplesCold[pixel] = float4(
            levelRaw,                                                                 // R: LOD level (raw; postprocess normalizes)
            noEntry ? 0.f : saturate(float(g.probeSteps) / float(kMaxProbe * uint(g.level + 1))),   // G: avg probe steps per level
            noEntry ? 0.f : saturate(float(g.N) / float(gBootThreshold * 8u)),  // B: sample count
            coldmiss                                                             // A: cold miss
        );

        // Hash vis at the queried level (g.level reflects the lookup's
        // entry level even when no entry was found, so visualization shows
        // the cell SIZE that was queried, not a coarse-fallback).
        uint diagLvl = uint(max(g.level, 0));
        uint posAHash = pcgHashA(g.qa, diagLvl);
        uint posBHash = pcgHashB(g.qb, diagLvl);
        uint combinedHash = posAHash ^ posBHash ^ pcgHashDist(diagLvl);
        gVCFrameHashAHashBHashABRays[pixel] = float4(
            float(posAHash & 0xFFFFu) / 65535.f,                    // R: posA cell hash
            float(posBHash & 0xFFFFu) / 65535.f,                    // G: posB cell hash
            float(combinedHash & 0xFFFFu) / 65535.f,                // B: combined hash at selected lvl
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

    // Ray counters + derived metrics (rolled-up + per-call-site).
    uint saved = gVCAccumSaved[pixel] + (traced ? 0u : 1u);
    uint total = gVCAccumTotal[pixel] + 1u;
    gVCAccumSaved[pixel] = saved;
    gVCAccumTotal[pixel] = total;

    uint savedNEE   = gVCAccumSavedNEE[pixel];
    uint totalNEE   = gVCAccumTotalNEE[pixel];
    uint savedReval = gVCAccumSavedReval[pixel];
    uint totalReval = gVCAccumTotalReval[pixel];
    if (callSite == VC_RAY_SITE_REVAL)
    {
        savedReval += traced ? 0u : 1u;
        totalReval += 1u;
        gVCAccumSavedReval[pixel] = savedReval;
        gVCAccumTotalReval[pixel] = totalReval;
    }
    else // VC_RAY_SITE_NEE (default for cache-NEE bounce-0 path)
    {
        savedNEE += traced ? 0u : 1u;
        totalNEE += 1u;
        gVCAccumSavedNEE[pixel] = savedNEE;
        gVCAccumTotalNEE[pixel] = totalNEE;
    }

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

    // Split per-call-site ratios. Pixels with zero queries on a site report
    // 0 (not-traced); postprocess can mask on totals to avoid skewing means.
    float ratioNEE   = (totalNEE   > 0u) ? float(totalNEE   - savedNEE)   / float(totalNEE)   : 0.f;
    float ratioReval = (totalReval > 0u) ? float(totalReval - savedReval) / float(totalReval) : 0.f;
    gVCAccumRaysSplitNeeReval[pixel] = float4(ratioNEE, ratioReval, 0.f, 0.f);
}

/// Lightweight ray-counter bump for V-tests that do NOT go through the
/// vhfGate/vhfCommit cache path — used by the WS-ReSTIR pipeline whose
/// K-RIS winner V-test and (mode=1 FullTrace) retrace-on-reuse sites
/// fire `vq.traceVisibilityRay` directly. Bumps the rolled-up counters
/// plus the per-call-site counters keyed on `callSite`. Mode=2 (CacheCV)
/// paths go through `evalRevalidationCV` → `vcWriteDiag`, so they are
/// counted there, not here (would double-count).
void vcDiagCountRay(uint2 pixel, bool traced, uint callSite = VC_RAY_SITE_NEE)
{
    uint saved = gVCAccumSaved[pixel] + (traced ? 0u : 1u);
    uint total = gVCAccumTotal[pixel] + 1u;
    gVCAccumSaved[pixel] = saved;
    gVCAccumTotal[pixel] = total;

    uint savedNEE   = gVCAccumSavedNEE[pixel];
    uint totalNEE   = gVCAccumTotalNEE[pixel];
    uint savedReval = gVCAccumSavedReval[pixel];
    uint totalReval = gVCAccumTotalReval[pixel];
    if (callSite == VC_RAY_SITE_REVAL)
    {
        savedReval += traced ? 0u : 1u;
        totalReval += 1u;
        gVCAccumSavedReval[pixel] = savedReval;
        gVCAccumTotalReval[pixel] = totalReval;
    }
    else
    {
        savedNEE += traced ? 0u : 1u;
        totalNEE += 1u;
        gVCAccumSavedNEE[pixel] = savedNEE;
        gVCAccumTotalNEE[pixel] = totalNEE;
    }

    float ratio = float(total - saved) / float(total);
    float4 prev = gVCAccumRaysNoiseErrorCold[pixel];
    gVCAccumRaysNoiseErrorCold[pixel] = float4(ratio, prev.g, prev.b, prev.a);

    float ratioNEE   = (totalNEE   > 0u) ? float(totalNEE   - savedNEE)   / float(totalNEE)   : 0.f;
    float ratioReval = (totalReval > 0u) ? float(totalReval - savedReval) / float(totalReval) : 0.f;
    gVCAccumRaysSplitNeeReval[pixel] = float4(ratioNEE, ratioReval, 0.f, 0.f);
}

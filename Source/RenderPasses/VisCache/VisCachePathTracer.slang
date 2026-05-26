/***************************************************************************
 * VisCachePathTracer.slang — VisCache wrapper for Falcor PathTracer.
 *
 * SceneRayQuery<UseAlphaTest> (compile-time param).
 * posA = ray.origin, posB = ray.origin + ray.dir * ray.tMax.
 *
 * Import this from PathTracer only. Self-guards with #if USE_VISCACHE.
 ***************************************************************************/

#pragma once

#if USE_VISCACHE

import RenderPasses.VisCache.VisCache;
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif
import Scene.RaytracingInline;
import Utils.Sampling.SampleGenerator;

/// VisCache-private sample generator: independent of the main PathTracer stream.
/// Mirrors PathTracer's seed structure (frameCount * spp + sampleIdx) so each
/// (frame, sample) pair gets a unique coin flip; large offset avoids RNG overlap.
SampleGenerator vcCreateSG(uint2 pixel, uint sampleIdx)
{
    return SampleGenerator(pixel, gFrameCount * gSpp + sampleIdx + 0x7C000000u);
}

// callSite: VC_RAY_SITE_* tag (see VisCacheDiagnostics.slang). Default
// VC_RAY_SITE_NEE matches the historical behaviour for all NEE shadow rays;
// pass VC_RAY_SITE_PROPOSAL for V-aware target-pdf cache reads and
// VC_RAY_SITE_RECONNECT for PT reconnection-shift V tests.
float vcVisibility_Ray<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg, uint2 pixel, uint sampleIdx,
    float3 normalA = float3(0.f), uint callSite = 0u)
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    // PROPOSAL site: candidate selection — pure cached mu, no trace, no
    // correction. Bias is absorbed by the K-RIS unbiasing structure as long
    // as a base probability stays positive for every candidate. Per user
    // 2026-05-26: "candidate selection can use a very relaxed quality and
    // no correction at all".
    if (callSite == 2u /* VC_RAY_SITE_PROPOSAL */)
    {
        VHFResult r = vhfLookup(posA, posB, normalA, callSite);
#ifdef VISCACHE_DIAGNOSTICS
        vcDiagCountRay(pixel, false, callSite);  // never traced
#endif
        return r.mu;  // raw cached mean (0.5 fallback when no entry)
    }
    SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA, vhfBayerWarmup(pixel), callSite);

    float result;
    bool traced;
    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        result = vhfCommit(posA, posB, V, g, normalA);
        traced = true;
    }
    else
    {
        result = g.visWeight;
        traced = false;
    }
    // Counter-only bump (no per-pixel diagnostic texture writes — those
    // are reserved for the Diag wrapper). Lets visInPHat=1 / reconnect /
    // any other cache-routed visibility query land in the right per-mode
    // ray-savings column.
#ifdef VISCACHE_DIAGNOSTICS
    vcDiagCountRay(pixel, traced, callSite);
#endif
    return result;
}

#ifdef VISCACHE_DIAGNOSTICS
float vcVisibility_Ray_Diag<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg, uint2 pixel, uint sampleIdx,
    float3 normalA = float3(0.f), uint callSite = 0u)
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    // PROPOSAL site: see non-Diag variant. Diag wrapper mirrors the early-
    // exit but still emits the diag-write so the per-pixel plate columns
    // pick up "trusted, not traced" for these cells.
    if (callSite == 2u /* VC_RAY_SITE_PROPOSAL */)
    {
        VHFResult r = vhfLookup(posA, posB, normalA, callSite);
        VHFGateResult g;
        g.shouldTrace = false; g.visWeight = r.mu; g.mu = r.mu; g.invP = 0.f;
        g.var = r.var; g.level = r.level; g.valid_data = r.valid;
        g.N = r.N; g.probeSteps = r.probeSteps; g.qa = r.qa; g.qb = r.qb;
        vcWriteDiag(pixel, g, false, 0.f, posA, posB, callSite);
        return r.mu;
    }
    SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA, vhfBayerWarmup(pixel), callSite);

    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        float w = vhfCommit(posA, posB, V, g, normalA);
        vcWriteDiag(pixel, g, true, V, posA, posB, callSite);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f, posA, posB, callSite);
    return g.visWeight;
}
#endif // VISCACHE_DIAGNOSTICS

#endif // USE_VISCACHE

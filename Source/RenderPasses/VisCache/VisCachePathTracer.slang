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
    float3 normalA = float3(0.f), uint callSite = 0u,
    float contribLuminance = 0.f, uint bounceDepth = 0u)
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    // PROPOSAL + REVAL (callSite=2 / 1) — "lazy" sites with defensive trace.
    // Mostly cached mu, no CV+RRR. Trace a FEW defensive rays for high-
    // contribution candidates whose cached mu is questionable (high var ×
    // low maturity). Probability ∝ doubtfulness × contribLuminance × scale,
    // capped at 10% so trace rate stays low. Per user 2026-05-26: "candidate
    // selection can use a very relaxed quality and no correction at all",
    // and "reval is often not traced (RTXDI default) — be a bit lazy there
    // too, stay below vanilla NEE budget".
    if (callSite == 2u /* PROPOSAL */ || callSite == 1u /* REVAL */)
    {
        SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
        VHFResult r = vhfLookup(posA, posB, normalA, callSite, bounceDepth);
        // doubtfulness ∈ [0,1]: cached mu near 0.5 (high var) + few samples
        // → high doubt. Mature low-var cells trust without trace.
        float maturityFrac = r.valid ? saturate(float(r.N) / max(float(gBootThreshold), 1.f)) : 0.f;
        float doubtfulness = r.var * (1.f - 0.5f * maturityFrac);
        // Trace prob: budget × doubtfulness × normalized contribution.
        // gFireflyBudget reuses the firefly-aware-floor scale (no new knob).
        // Hardcap 0.10 keeps proposal-trace rate ≤ 10% of calls.
        float p_trace = saturate(doubtfulness * contribLuminance / max(gFireflyBudget, 1e-4f));
        p_trace = min(p_trace, 0.10f);
        if (sampleNext1D(vcSG) < p_trace)
        {
            SceneRayQuery<UseAlphaTest> sceneRayQuery;
            float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
            // Insert into cache so subsequent reads benefit from the trace.
            vhfInsert(posA, posB, V, normalA);
#ifdef VISCACHE_DIAGNOSTICS
            vcDiagCountRay(pixel, true, callSite);
#endif
            return V;
        }
#ifdef VISCACHE_DIAGNOSTICS
        vcDiagCountRay(pixel, false, callSite);
#endif
        return r.mu;  // raw cached mean (0.5 fallback when no entry)
    }
    SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA, vhfBayerWarmup(pixel), callSite, bounceDepth);

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
    float3 normalA = float3(0.f), uint callSite = 0u,
    float contribLuminance = 0.f, uint bounceDepth = 0u)
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    // PROPOSAL + REVAL: see non-Diag variant for the defensive-trace policy.
    if (callSite == 2u /* PROPOSAL */ || callSite == 1u /* REVAL */)
    {
        SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
        VHFResult r = vhfLookup(posA, posB, normalA, callSite, bounceDepth);
        float maturityFrac = r.valid ? saturate(float(r.N) / max(float(gBootThreshold), 1.f)) : 0.f;
        float doubtfulness = r.var * (1.f - 0.5f * maturityFrac);
        float p_trace = saturate(doubtfulness * contribLuminance / max(gFireflyBudget, 1e-4f));
        p_trace = min(p_trace, 0.10f);
        VHFGateResult g;
        g.mu = r.mu; g.var = r.var; g.level = r.level; g.valid_data = r.valid;
        g.N = r.N; g.probeSteps = r.probeSteps; g.qa = r.qa; g.qb = r.qb;
        if (sampleNext1D(vcSG) < p_trace)
        {
            SceneRayQuery<UseAlphaTest> sceneRayQuery;
            float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
            vhfInsert(posA, posB, V, normalA);
            g.shouldTrace = true; g.visWeight = 0.f; g.invP = 1.f / max(p_trace, 1e-4f);
            vcWriteDiag(pixel, g, true, V, posA, posB, callSite);
            return V;
        }
        g.shouldTrace = false; g.visWeight = r.mu; g.invP = 0.f;
        vcWriteDiag(pixel, g, false, 0.f, posA, posB, callSite);
        return r.mu;
    }
    SampleGenerator vcSG = vcCreateSG(pixel, sampleIdx);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA, vhfBayerWarmup(pixel), callSite, bounceDepth);

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

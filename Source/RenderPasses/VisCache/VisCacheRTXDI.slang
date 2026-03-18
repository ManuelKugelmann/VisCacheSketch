/***************************************************************************
 * VisCacheRTXDI.slang — VisCache wrapper for RTXDIPass.
 *
 * SceneRayQuery<1> (always alpha-test). Accepts contribution luminance
 * for firefly-aware adaptive pMin.
 * posA = shading point, posB = light position.
 *
 * Uses SampleGenerator for the RR coin flip. The caller (FinalShading.cs.slang)
 * creates the SampleGenerator and imports the module — this file just
 * forward-declares the interface to avoid pulling in the full sampling framework.
 *
 * Import this from RTXDIPass only. Self-guards with #if USE_VISCACHE.
 ***************************************************************************/

#pragma once

#if USE_VISCACHE

import RenderPasses.VisCache.VisCache;
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif
import Scene.RaytracingInline;

/// Accept any sample generator type via Slang generics — avoids hard dependency
/// on SampleGenerator module which may not be available in all RTXDI contexts.
float vcVisibility_InlineRay<S : ISampleGenerator>(
    float3 posA, float3 dir, float distance,
    inout S sg,
    float contribLuminance = 0.f)
{
    float3 posB = vhfAddressPosB(posA, dir, distance);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg), contribLuminance);

    if (g.shouldTrace)
    {
        SceneRayQuery<1> rayQuery;
        const Ray ray = Ray(posA, dir, 0.f, distance);
        float V = rayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        return vhfCommit(posA, posB, V, g);
    }
    return g.visWeight;
}

#ifdef VISCACHE_DIAGNOSTICS
float vcVisibility_InlineRay<S : ISampleGenerator>(
    float3 posA, float3 dir, float distance,
    inout S sg,
    uint2 pixel,
    float contribLuminance = 0.f)
{
    float3 posB = vhfAddressPosB(posA, dir, distance);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg), contribLuminance);

    if (g.shouldTrace)
    {
        SceneRayQuery<1> rayQuery;
        const Ray ray = Ray(posA, dir, 0.f, distance);
        float V = rayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        float w = vhfCommit(posA, posB, V, g);
        vcWriteDiag(pixel, g, true, V, posA, posB);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f, posA, posB);
    return g.visWeight;
}
#endif // VISCACHE_DIAGNOSTICS

#endif // USE_VISCACHE

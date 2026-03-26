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
/// Large offset (0xVC000000) ensures no overlap with main SampleGenerator sequence.
/// This keeps vanilla and VisCache renders deterministically comparable.
SampleGenerator vcCreateSG(uint2 pixel, uint frameCount)
{
    return SampleGenerator(pixel, frameCount + 0x7C000000u);
}

/// Overload without frameCount — uses pixel-only seed (acceptable for RR coin flip).
SampleGenerator vcCreateSG(uint2 pixel)
{
    return SampleGenerator(pixel, 0x7C000000u);
}

float vcVisibility_Ray<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg, uint2 pixel,
    float3 normalA = float3(0.f))
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    SampleGenerator vcSG = vcCreateSG(pixel);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA);

    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        return vhfCommit(posA, posB, V, g, normalA);
    }
    return g.visWeight;
}

#ifdef VISCACHE_DIAGNOSTICS
float vcVisibility_Ray_Diag<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg, uint2 pixel,
    float3 normalA = float3(0.f))
{
    float3 posA = ray.origin;
    float3 posB = vhfAddressPosB(posA, ray.dir, ray.tMax);
    SampleGenerator vcSG = vcCreateSG(pixel);
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(vcSG), 0.f, normalA);

    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        float w = vhfCommit(posA, posB, V, g, normalA);
        vcWriteDiag(pixel, g, true, V, posA, posB);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f, posA, posB);
    return g.visWeight;
}
#endif // VISCACHE_DIAGNOSTICS

#endif // USE_VISCACHE

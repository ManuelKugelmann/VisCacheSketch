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

float vcVisibility_Ray<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg)
{
    float3 posB = ray.origin + ray.dir * ray.tMax;
    VHFGateResult g = vhfGate(ray.origin, posB, sampleNext1D(sg));

    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        return vhfCommit(ray.origin, posB, V, g);
    }
    return g.visWeight;
}

#ifdef VISCACHE_DIAGNOSTICS
float vcVisibility_Ray_Diag<let UseAlphaTest : int>(
    const Ray ray, inout SampleGenerator sg, uint2 pixel)
{
    float3 posB = ray.origin + ray.dir * ray.tMax;
    VHFGateResult g = vhfGate(ray.origin, posB, sampleNext1D(sg));

    if (g.shouldTrace)
    {
        SceneRayQuery<UseAlphaTest> sceneRayQuery;
        float V = sceneRayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        float w = vhfCommit(ray.origin, posB, V, g);
        vcWriteDiag(pixel, g, true, V);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f);
    return g.visWeight;
}
#endif // VISCACHE_DIAGNOSTICS

#endif // USE_VISCACHE

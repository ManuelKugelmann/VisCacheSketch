/***************************************************************************
 * VisCacheTracing.slang
 *
 * High-level entrypoint wrappers for VisCache shadow ray gating.
 * Each wrapper matches a specific pass's tracing convention and returns
 * a fractional visWeight in [0, 1].  All route to the same core
 * vhfGate() + vhfCommit() in VisCache.slang.
 *
 * USAGE: import this file (guarded by #if USE_VISCACHE) instead of
 * writing inline CV+RRR blocks.  The consumer pass diff shrinks to
 * a single function call replacing the original trace call.
 *
 * Wrappers provided:
 *   vcVisibility_InlineRay  — SceneRayQuery<1>, for RTXDIPass
 *   vcVisibility_Ray        — SceneRayQuery<UseAlphaTest>, for PathTracer
 *   vcVisibility_DirDist    — traceShadowRay(o,d,t), for MinimalPathTracer
 *
 * Core signature: just posA, posB (arbitrary endpoints).
 * camPos, thresholds, etc. come from VisCacheParams cbuffer.
 ***************************************************************************/

#pragma once

import RenderPasses.VisCache.VisCache;
import Scene.RaytracingInline;
import Utils.Sampling.SampleGenerator;

// ---------------------------------------------------------------------------
// RTXDIPass entrypoint — SceneRayQuery<1> (always alpha-test).
// Accepts contribution luminance for firefly-aware adaptive pMin.
// posA = ray origin (shading point), posB = light position.
// ---------------------------------------------------------------------------
float vcVisibility_InlineRay(float3 posA, float3 dir, float distance,
                              inout SampleGenerator sg,
                              float contribLuminance = 0.f)
{
    float3 posB = posA + dir * distance;
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

// ---------------------------------------------------------------------------
// PathTracer entrypoint — SceneRayQuery<UseAlphaTest> (compile-time param).
// posA = ray.origin, posB = ray.origin + ray.dir * ray.tMax.
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// MinimalPathTracer entrypoint — traceShadowRay(origin, dir, distance).
// Requires traceShadowRay to be in scope (Falcor scene helper).
// ---------------------------------------------------------------------------
float vcVisibility_DirDist(float3 posA, float3 dir, float distance,
                            inout SampleGenerator sg)
{
    float3 posB = posA + dir * distance;
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(posA, dir, distance) ? 1.f : 0.f;
        return vhfCommit(posA, posB, V, g);
    }
    return g.visWeight;
}

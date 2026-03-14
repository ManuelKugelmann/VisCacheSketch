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
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif
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

// ===========================================================================
// Diagnostic overloads — same as above but write per-pixel heatmap data.
// Pass `pixel` = DispatchRaysIndex().xy (or equivalent).
// Bind all diagnostic textures from dictionary (see VisCacheDiagnostics.slang).
//
// To enable: add VISCACHE_DIAGNOSTICS=1 to the shader DefineList and bind
// the diagnostic textures from the InternalDictionary.
// ===========================================================================
#ifdef VISCACHE_DIAGNOSTICS

/// RTXDIPass diagnostic overload.
float vcVisibility_InlineRay(float3 posA, float3 dir, float distance,
                              inout SampleGenerator sg,
                              uint2 pixel,
                              float contribLuminance = 0.f)
{
    float3 posB = posA + dir * distance;
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg), contribLuminance);

    if (g.shouldTrace)
    {
        SceneRayQuery<1> rayQuery;
        const Ray ray = Ray(posA, dir, 0.f, distance);
        float V = rayQuery.traceVisibilityRay(ray) ? 1.f : 0.f;
        float w = vhfCommit(posA, posB, V, g);
        vcWriteDiag(pixel, g, true, V);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f);
    return g.visWeight;
}

/// PathTracer diagnostic overload.
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

/// MinimalPathTracer diagnostic overload.
float vcVisibility_DirDist(float3 posA, float3 dir, float distance,
                            inout SampleGenerator sg, uint2 pixel)
{
    float3 posB = posA + dir * distance;
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(posA, dir, distance) ? 1.f : 0.f;
        float w = vhfCommit(posA, posB, V, g);
        vcWriteDiag(pixel, g, true, V);
        return w;
    }
    vcWriteDiag(pixel, g, false, 0.f);
    return g.visWeight;
}

#endif // VISCACHE_DIAGNOSTICS

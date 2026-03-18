/***************************************************************************
 * VisCacheMinimalPT.slang — VisCache wrapper for MinimalPathTracer.
 *
 * Uses traceShadowRay(origin, dir, distance) which must be in scope
 * (defined by MinimalPathTracer.rt.slang before this import).
 *
 * Import this from MinimalPathTracer only. Self-guards with #if USE_VISCACHE.
 ***************************************************************************/

#pragma once

#if USE_VISCACHE

import RenderPasses.VisCache.VisCache;
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif
import Utils.Sampling.SampleGenerator;

float vcVisibility_DirDist(float3 posA, float3 dir, float distance,
                            inout SampleGenerator sg)
{
    float3 posB = posA + dir * distance;
    VHFGateResult g = vhfGate(posA, posB, sampleNext1D(sg));

    if (g.shouldTrace)
    {
        float V = traceShadowRay(posA, dir, distance);
        return vhfCommit(posA, posB, V, g);
    }
    return g.visWeight;
}

#ifdef VISCACHE_DIAGNOSTICS
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

#endif // USE_VISCACHE

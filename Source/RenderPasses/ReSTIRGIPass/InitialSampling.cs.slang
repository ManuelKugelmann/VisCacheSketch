/***************************************************************************
 * InitialSampling.cs.slang
 *
 * Initial path trace sampling for ReSTIR GI — Falcor 8.0.
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 → 8.0).
 *
 * For each pixel: load primary hit from vbuffer, trace one secondary
 * bounce, evaluate radiance at the secondary hit, and store in a
 * reservoir + secondary-hit buffer for temporal/spatial reuse.
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Scene.Material.MaterialSystem;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;
import Rendering.Materials.IBSDF;

import RenderPasses.ReSTIRGIPass.ReSTIRGICommon;

// ---------------------------------------------------------------------------
// Buffers
// ---------------------------------------------------------------------------
RWStructuredBuffer<PathReservoir> gReservoirs;
RWStructuredBuffer<SecondaryHit>  gSecondaryHits;
Texture2D<PackedHitInfo>          gVBuffer;

cbuffer PerFrameCB
{
    uint   gFrameCount;
    uint2  gFrameDim;
    float3 gCamPos;
};

// ---------------------------------------------------------------------------
// Trace a secondary indirect bounce from the primary hit.
// Uses inline ray tracing (DXR 1.1 TraceRayInline) via Falcor's scene API.
// ---------------------------------------------------------------------------
void traceSecondaryBounce(const ShadingData sd, inout SampleGenerator sg,
                          out SecondaryHit hit, out float3 bsdfVal, out float pdf)
{
    hit.posW    = float3(0);
    hit.normalW = float3(0, 1, 0);
    hit.Lo      = float3(0);
    hit.invPDF  = 0.0f;
    hit.wi      = float3(0);
    hit._pad    = 0u;
    bsdfVal     = float3(0);
    pdf         = 0.0f;

    // Sample BSDF for secondary direction
    let lod = ExplicitLodTextureSampler(0.0f);
    BSDFSample bsdfSample;
    if (!gScene.materials.getBSDF(sd, lod).sample(sd, sg, bsdfSample, true))
        return;

    if (luminance(bsdfSample.weight) < 1e-7f || bsdfSample.pdf < 1e-7f)
        return;

    bsdfVal = bsdfSample.weight * bsdfSample.pdf; // f * cos / pdf * pdf = f * cos
    pdf     = bsdfSample.pdf;

    // Trace secondary ray
    RayDesc ray;
    ray.Origin    = sd.computeRayOrigin();
    ray.Direction = bsdfSample.wi;
    ray.TMin      = 0.0f;
    ray.TMax      = 1e20f;

    SceneRayQuery<0> rayQuery;
    if (!rayQuery.traceRay(ray, hit2, 0.0f, RAY_FLAG_NONE))
        return; // miss — could add env map contribution here

    // Unpack secondary hit
    TriangleHit triangleHit = hit2.getTriangleHit();
    VertexData v = gScene.getVertexData(triangleHit);
    let mtl = gScene.materials.getMaterialInstance(sd, lod);

    hit.posW    = v.posW;
    hit.normalW = v.faceNormalW;
    hit.wi      = bsdfSample.wi;
    hit.invPDF  = 1.0f / pdf;

    // Evaluate outgoing radiance at secondary hit (emission only for now;
    // multi-bounce would recurse but DQLin uses single-bounce GI).
    float3 emission = gScene.materials.getEmission(triangleHit, v);
    hit.Lo = emission;

    // Direct lighting at secondary hit (one shadow ray for next-event estimation)
    // This follows DQLin's single-bounce approach.
    // For the full implementation, we'd sample a light and trace a shadow ray.
    // The reservoir will carry this radiance through reuse.
}

// ---------------------------------------------------------------------------
// Main kernel
// ---------------------------------------------------------------------------
[numthreads(8, 8, 1)]
void csInitialSampling(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    // Initialize empty reservoir
    PathReservoir reservoir;
    reservoir.reset();

    SecondaryHit emptyHit;
    emptyHit.posW    = float3(0);
    emptyHit.normalW = float3(0, 1, 0);
    emptyHit.Lo      = float3(0);
    emptyHit.invPDF  = 0.0f;
    emptyHit.wi      = float3(0);
    emptyHit._pad    = 0u;

    // Load primary hit from visibility buffer
    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        gReservoirs[pixelIdx]    = reservoir;
        gSecondaryHits[pixelIdx] = emptyHit;
        return;
    }

    // Load shading data at primary hit
    let lod = ExplicitLodTextureSampler(0.0f);
    ShadingData sd = gScene.loadShadingData(hitInfo, pixel, float2(0.5f), lod);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount);

    // Trace secondary bounce
    SecondaryHit secHit;
    float3 bsdfVal;
    float  pdf;
    traceSecondaryBounce(sd, sg, secHit, bsdfVal, pdf);

    if (pdf > 1e-7f && luminance(secHit.Lo) > 0.0f)
    {
        // Reconnection geometry term
        float3 toHit = secHit.posW - sd.posW;
        float  dist  = length(toHit);
        if (dist > 1e-6f)
        {
            float3 dir = toHit / dist;
            float  G   = abs(dot(sd.N, dir)) * abs(dot(secHit.normalW, -dir))
                        / (dist * dist + 1e-6f);

            float pHat = evalTargetPdf(bsdfVal, secHit.Lo, G);
            if (pHat > 0.0f)
            {
                float weight = pHat * secHit.invPDF;
                reservoir.update(secHit, weight, pHat, sg);
            }
        }
    }

    reservoir.finalize();

    gReservoirs[pixelIdx]    = reservoir;
    gSecondaryHits[pixelIdx] = reservoir.isValid() ? reservoir.sample : emptyHit;
}

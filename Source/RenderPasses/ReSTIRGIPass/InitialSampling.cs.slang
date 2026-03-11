/***************************************************************************
 * InitialSampling.cs.slang
 *
 * Initial path trace sampling for ReSTIR GI — Falcor 8.0.
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 → 8.0).
 *
 * For each pixel: load primary hit from vbuffer, trace one secondary
 * bounce, evaluate radiance at the secondary hit (emission + NEE),
 * and store in a reservoir + secondary-hit buffer for temporal/spatial
 * reuse.
 *
 * NEE at the secondary hit follows the DQLin single-bounce GI model:
 * sample one light, trace a shadow ray, accumulate Le + (BSDF * Li * V).
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Scene.Material.MaterialSystem;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;
import Rendering.Materials.IBSDF;
import Rendering.Lights.LightHelpers;

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

// loadSD() is defined in ReSTIRGICommon.slang

// ---------------------------------------------------------------------------
// Trace a secondary indirect bounce from the primary hit.
// Uses Falcor 8.0 inline ray tracing: SceneRayQuery<0>::traceRay()
// returns HitInfo with out float hitT parameter.
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

    if (luminance(bsdfSample.weight) < kLuminanceEps || bsdfSample.pdf < kLuminanceEps)
        return;

    bsdfVal = bsdfSample.weight * bsdfSample.pdf; // f * cos / pdf * pdf = f * cos
    pdf     = bsdfSample.pdf;

    // Trace secondary ray (Falcor 8.0: Ray struct, traceRay returns HitInfo)
    Ray ray = Ray(sd.computeRayOrigin(), bsdfSample.wi, 0.0f, 1e20f);

    SceneRayQuery<0> rayQuery;
    float hitT;
    HitInfo secHitInfo = rayQuery.traceRay(ray, hitT);

    if (!secHitInfo.isValid())
        return; // miss — could add env map contribution here

    // Only handle triangle hits for GI
    if (secHitInfo.getType() != HitType::Triangle)
        return;

    TriangleHit triangleHit = secHitInfo.getTriangleHit();
    VertexData v = gScene.getVertexData(triangleHit);
    uint secMaterialID = gScene.getMaterialID(triangleHit.instanceID);

    hit.posW    = v.posW;
    hit.normalW = v.faceNormalW;
    hit.wi      = bsdfSample.wi;
    hit.invPDF  = 1.0f / pdf;

    // ----- Radiance at secondary hit: emission + NEE (single-bounce GI) -----

    // Prepare shading data at secondary hit for BSDF evaluation
    ShadingData secSD = gScene.materials.prepareShadingData(
        v, secMaterialID, -bsdfSample.wi);

    // 1. Emission from the hit surface
    let secLod = ExplicitLodTextureSampler(0.0f);
    let secBsdf = gScene.materials.getBSDF(secSD, secLod);
    float3 Lo = secBsdf.getProperties(secSD).emission;

    // 2. Next-event estimation: sample one analytic light at the secondary hit.
    //    This is what makes GI useful on non-emissive surfaces.
    //    DQLin's single-bounce model: one shadow ray per initial sample.
    uint lightCount = gScene.getLightCount();
    if (lightCount > 0u)
    {
        // Uniform random light selection
        float lightSel = sampleNext1D(sg);
        uint lightIdx = min(uint(lightSel * float(lightCount)), lightCount - 1u);

        AnalyticLightSample ls;
        if (sampleLight(v.posW, gScene.getLight(lightIdx), sg, ls))
        {
            // Shadow ray from secondary hit to sampled light
            float3 origin = computeRayOrigin(v.posW, v.faceNormalW);
            Ray shadowRay = Ray(origin, ls.dir, 0.0f,
                                ls.distance * (1.0f - kShadowRayOffset));

            SceneRayQuery<0> shadowQuery;
            bool visible = shadowQuery.traceVisibilityRay(shadowRay);

            if (visible)
            {
                // Evaluate BSDF at secondary hit in light direction
                float3 f = secBsdf.eval(secSD, ls.dir, sg);
                // Accumulate: BSDF * Li / lightPdf (uniform: pdf = 1/count)
                Lo += f * ls.Li * float(lightCount);
            }
        }
    }

    hit.Lo = Lo;
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

    // Compute ray direction from camera to primary hit (Falcor 8.0)
    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);

    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);
    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount);

    // Trace secondary bounce
    SecondaryHit secHit;
    float3 bsdfVal;
    float  pdf;
    traceSecondaryBounce(sd, sg, secHit, bsdfVal, pdf);

    if (pdf > kLuminanceEps && luminance(secHit.Lo) > 0.0f)
    {
        // Reconnection geometry term
        float3 toHit = secHit.posW - sd.posW;
        float  dist  = length(toHit);
        if (dist > kDistanceEps)
        {
            float3 dir = toHit / dist;
            float  G   = max(dot(sd.N, dir), 0.0f) * abs(dot(secHit.normalW, -dir))
                        / (dist * dist + kDistanceEps);

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

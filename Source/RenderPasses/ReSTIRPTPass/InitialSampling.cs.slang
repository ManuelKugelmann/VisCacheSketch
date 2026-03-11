/***************************************************************************
 * InitialSampling.cs.slang  (ReSTIR PT — multi-bounce)
 *
 * Traces a full path (up to MAX_BOUNCES), selects a reconnection vertex
 * via reservoir streaming, and stores the path prefix + reconnection data.
 *
 * When MAX_BOUNCES=1, this reduces to single-bounce GI (ReSTIRGIPass).
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

import RenderPasses.ReSTIRPTPass.ReSTIRPTCommon;

RWStructuredBuffer<PathReservoir> gReservoirs;
RWStructuredBuffer<SecondaryHit>  gSecondaryHits;
Texture2D<PackedHitInfo>          gVBuffer;

cbuffer PerFrameCB
{
    uint   gFrameCount;
    uint2  gFrameDim;
    float3 gCamPos;
};

#ifndef MAX_BOUNCES
#define MAX_BOUNCES 4
#endif

// loadSD() is defined in ReSTIRPTCommon.slang

[numthreads(8, 8, 1)]
void csInitialSampling(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    PathReservoir reservoir;
    reservoir.reset();

    SecondaryHit emptyHit;
    emptyHit.posW = float3(0); emptyHit.normalW = float3(0,1,0);
    emptyHit.Lo = float3(0); emptyHit.invPDF = 0.0f;
    emptyHit.wi = float3(0); emptyHit._pad = 0u;

    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        gReservoirs[pixelIdx] = reservoir;
        gSecondaryHits[pixelIdx] = emptyHit;
        return;
    }

    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);

    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);
    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount);

    // Multi-bounce path tracing with reservoir streaming over reconnection candidates.
    // At each bounce, we consider the current vertex as a potential reconnection point.
    float3 prefixThroughput = float3(1.0f);
    float  prefixPdf        = 1.0f;
    ShadingData curSD       = sd;
    float3      curOrigin   = sd.posW;

    for (uint bounce = 0; bounce < MAX_BOUNCES; bounce++)
    {
        let lod = ExplicitLodTextureSampler(0.0f);
        BSDFSample bsdfSample;
        if (!gScene.materials.getBSDF(curSD, lod).sample(curSD, sg, bsdfSample, true))
            break;

        if (luminance(bsdfSample.weight) < kLuminanceEps || bsdfSample.pdf < kLuminanceEps)
            break;

        // Trace ray to next bounce
        Ray ray = Ray(curSD.computeRayOrigin(), bsdfSample.wi, 0.0f, 1e20f);
        SceneRayQuery<0> rayQuery;
        float hitT;
        HitInfo secHitInfo = rayQuery.traceRay(ray, hitT);

        if (!secHitInfo.isValid() || secHitInfo.getType() != HitType::Triangle)
            break;

        TriangleHit tri = secHitInfo.getTriangleHit();
        VertexData v = gScene.getVertexData(tri);
        uint matID = gScene.getMaterialID(tri.instanceID);

        ShadingData nextSD = gScene.materials.prepareShadingData(
            v, matID, -bsdfSample.wi);

        // Update prefix throughput: BSDF * cos (bsdfSample.weight already = f*cos/pdf)
        float3 bounceThroughput = bsdfSample.weight; // f*cos/pdf
        prefixThroughput *= bounceThroughput;
        prefixPdf        *= bsdfSample.pdf;

        // Evaluate radiance at this vertex (emission + one NEE shadow ray)
        let secBsdf = gScene.materials.getBSDF(nextSD, lod);
        float3 Lo = secBsdf.getProperties(nextSD).emission;

        uint lightCount = gScene.getLightCount();
        if (lightCount > 0u)
        {
            float lightSel = sampleNext1D(sg);
            uint lightIdx = min(uint(lightSel * float(lightCount)), lightCount - 1u);
            AnalyticLightSample ls;
            if (sampleLight(v.posW, gScene.getLight(lightIdx), sg, ls))
            {
                Ray shadowRay = Ray(
                    computeRayOrigin(v.posW, v.faceNormalW),
                    ls.dir, 0.0f, ls.distance * (1.0f - kShadowRayOffset));
                SceneRayQuery<0> shadowQuery;
                if (shadowQuery.traceVisibilityRay(shadowRay))
                {
                    float3 f = secBsdf.eval(nextSD, ls.dir, sg);
                    Lo += f * ls.Li * float(lightCount);
                }
            }
        }

        // Consider this vertex as a reconnection candidate
        if (luminance(Lo) > 0.0f)
        {
            SecondaryHit candidate;
            candidate.posW    = v.posW;
            // Orient normal toward reconnection partner (DQLin: setGIInitialSample)
            float3 rcNormal = v.faceNormalW;
            if (dot(rcNormal, sd.posW - v.posW) < 0.0f)
                rcNormal = -rcNormal;
            candidate.normalW = rcNormal;
            candidate.Lo      = Lo;
            candidate.invPDF  = 1.0f / prefixPdf;
            candidate.wi      = bsdfSample.wi;
            candidate._pad    = 0u;

            // Geometry term for reconnection from primary hit to this vertex
            float3 toHit = v.posW - sd.posW;
            float  dist  = length(toHit);
            if (dist > kDistanceEps)
            {
                float3 dir = toHit / dist;
                float  G = max(dot(sd.N, dir), 0.0f) * abs(dot(v.faceNormalW, -dir))
                          / (dist * dist + kDistanceEps);

                float pHat = evalTargetPdf(prefixThroughput, Lo, G);
                if (pHat > 0.0f)
                {
                    float weight = pHat * candidate.invPDF;
                    reservoir.update(candidate, weight, pHat,
                                     prefixThroughput, bounce + 1u, sg);
                }
            }
        }

        // Advance to next bounce
        curSD     = nextSD;
        curOrigin = v.posW;

        // Russian roulette after bounce 2
        if (bounce >= 2)
        {
            float q = max(0.05f, 1.0f - luminance(prefixThroughput));
            if (sampleNext1D(sg) < q) break;
            prefixThroughput /= (1.0f - q);
        }
    }

    reservoir.finalize();

    gReservoirs[pixelIdx] = reservoir;
    gSecondaryHits[pixelIdx] = reservoir.isValid() ? reservoir.sample : emptyHit;
}

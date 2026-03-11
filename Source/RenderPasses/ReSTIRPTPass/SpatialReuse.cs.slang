/***************************************************************************
 * SpatialReuse.cs.slang  (ReSTIR PT — multi-bounce)
 *
 * Same structure as ReSTIRGIPass/SpatialReuse.cs.slang but imports
 * ReSTIRPTCommon (with extended PathReservoir carrying prefix throughput).
 *
 * VisCache modes (independently toggled via defines):
 *   USE_VISCACHE_REVAL=1:    CV+RRR gated V(P,Q) via VisCache hash table (S11.3).
 *   USE_LOCAL_REVAL=1:       CV+RRR via reservoir-local mu (no hash table).
 *   USE_VISCACHE_LIGHTSEL=1: Cached mu in target function (S11.1).
 *   All=0:                   Vanilla ReSTIR PT.
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

import RenderPasses.ReSTIRPTPass.ReSTIRPTCommon;

RWStructuredBuffer<PathReservoir> gReservoirs;
StructuredBuffer<SecondaryHit>    gSecondaryHits;
Texture2D<PackedHitInfo>          gVBuffer;

cbuffer PerFrameCB
{
    uint2  gFrameDim;
    float  gSpatialRadius;
    uint   gFrameCount;
    float3 gCamPos;
};

// loadSD() is defined in ReSTIRPTCommon.slang

float traceVisibilityRay(float3 origin, float3 target)
{
    float3 dir = target - origin;
    float dist = length(dir);
    if (dist < kDistanceEps) return 1.0f;
    dir /= dist;
    Ray ray = Ray(origin, dir, kShadowRayOffset, dist - kShadowRayOffset);
    SceneRayQuery<0> rayQuery;
    return rayQuery.traceVisibilityRay(ray) ? 1.0f : 0.0f;
}

float traceShadowRay(float3 origin, float3 target)
{
    return traceVisibilityRay(origin, target);
}

// Shared CV+RRR logic — same as GI pass, imported from common file.
import RenderPasses.VisCache.RevalidationCommon;

uint2 selectNeighbor(uint2 pixel, uint index, inout SampleGenerator sg)
{
    float angle  = sampleNext1D(sg) * (2.0f * M_PI);
    float radius = sqrt(sampleNext1D(sg)) * gSpatialRadius;
    int2 offset  = int2(cos(angle) * radius, sin(angle) * radius);
    int2 nbr     = clamp(int2(pixel) + offset, int2(0), int2(gFrameDim) - 1);
    return uint2(nbr);
}

float evalTargetAtPixel(ShadingData sd, SecondaryHit neighborSample,
                        float neighborTargetPdf,
                        inout SampleGenerator sg, out float pHatNoVis)
{
    pHatNoVis = 0.0f;
    if (luminance(neighborSample.Lo) < kLuminanceEps) return 0.0f;

    float3 toHit = neighborSample.posW - sd.posW;
    float dist = length(toHit);
    if (dist < kDistanceEps) return 0.0f;

    float3 dir = toHit / dist;
    float cosTheta = dot(sd.N, dir);
    if (cosTheta <= 0.0f) return 0.0f;

    float cosHit = abs(dot(neighborSample.normalW, -dir));
    float G = cosTheta * cosHit / (dist * dist + kDistanceEps);
    float3 bsdf = float3(cosTheta / M_PI);

    pHatNoVis = evalTargetPdf(bsdf, neighborSample.Lo, G);
    if (pHatNoVis < kLuminanceEps) return 0.0f;

    float V = evaluateVisibility(sd.posW, neighborSample.posW,
                                  bsdf, neighborSample.Lo, G,
                                  neighborTargetPdf, pHatNoVis,
                                  gCamPos, sg);
    return pHatNoVis * V;
}

[numthreads(8, 8, 1)]
void csSpatialReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;
    PathReservoir reservoir = gReservoirs[pixelIdx];

    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        gReservoirs[pixelIdx] = reservoir;
        return;
    }

    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);
    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount * 13u + 3u);

    PathReservoir merged;
    merged.reset();

    if (reservoir.isValid())
    {
        float w = reservoir.targetPdf * reservoir.W * reservoir.M;
        merged.M += reservoir.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample = reservoir.sample;
            merged.targetPdf = reservoir.targetPdf;
            merged.prefixThroughput = reservoir.prefixThroughput;
            merged.reconnectDepth = reservoir.reconnectDepth;
        }
    }

    static const uint kNumSpatialNeighbors = NUM_SPATIAL_NEIGHBORS;
    for (uint i = 0; i < kNumSpatialNeighbors; i++)
    {
        uint2 nbrPixel = selectNeighbor(pixel, i, sg);
        uint nbrIdx = nbrPixel.y * gFrameDim.x + nbrPixel.x;

        PathReservoir neighbor = gReservoirs[nbrIdx];
        if (!neighbor.isValid()) continue;

        if (!geometryValid(sd.N, neighbor.sample.normalW, sd.posW,
                           neighbor.sample.posW, kSpatialGeomNormalThresh, kSpatialGeomDepthThresh))
            continue;

        float pHatNoVis;
        float pHatWithVis = evalTargetAtPixel(sd, neighbor.sample, neighbor.targetPdf, sg, pHatNoVis);
        if (pHatWithVis < kLuminanceEps) continue;

        float nbrM = min(neighbor.M, kMaxSpatialM);
        float w = pHatWithVis * neighbor.W * nbrM;

        merged.M += nbrM;
        merged.wSum += w;

        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample = neighbor.sample;
            merged.targetPdf = pHatWithVis;
            merged.prefixThroughput = neighbor.prefixThroughput;
            merged.reconnectDepth = neighbor.reconnectDepth;
        }
    }

    merged.finalize();
    merged.M = min(merged.M, kMaxSpatialM);
    gReservoirs[pixelIdx] = merged;
}

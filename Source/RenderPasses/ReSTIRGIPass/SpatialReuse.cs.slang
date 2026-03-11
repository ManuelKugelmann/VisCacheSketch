/***************************************************************************
 * SpatialReuse.cs.slang
 *
 * Spatial reuse pass for ReSTIR GI — Falcor 8.0 port of DQLin/ReSTIR_PT
 * with VisCache CV+RRR revalidation replacing unconditional V(P,Q) rays.
 *
 * At k=5 spatial neighbors, DQLin traces 5 shadow rays per pixel.
 * With VisCache enabled, evalRevalidationCV() gates these via cached
 * visibility, reducing to ~0.5-1.0 rays/pixel at steady state (S12).
 *
 * Unbiased: E[mu + (V - mu) / p] = E[V] for any cache quality.
 *
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 -> 8.0). Core reservoir
 * streaming, neighbor selection, and Talbot MIS follow the original.
 * Only the visibility evaluation is modified for VisCache integration.
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

import RenderPasses.ReSTIRGIPass.ReSTIRGICommon;

// ---------------------------------------------------------------------------
// Buffers
// ---------------------------------------------------------------------------
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

// loadSD() is defined in ReSTIRGICommon.slang

// ---------------------------------------------------------------------------
// Visibility ray trace — core implementation used by both vanilla and
// VisCache modes. Returns 1.0 if visible, 0.0 if occluded.
// ---------------------------------------------------------------------------
float traceVisibilityRay(float3 origin, float3 target)
{
    float3 dir  = target - origin;
    float  dist = length(dir);
    if (dist < 1e-6f) return 1.0f;
    dir /= dist;

    Ray ray = Ray(origin, dir, 1e-4f, dist - 1e-4f);

    SceneRayQuery<0> rayQuery;
    return rayQuery.traceVisibilityRay(ray) ? 1.0f : 0.0f;
}

// ---------------------------------------------------------------------------
// traceShadowRay — external dependency required by RevalidationCommon.slang
// and ShadingCV.slang. Must be defined BEFORE the import.
// ---------------------------------------------------------------------------
float traceShadowRay(float3 origin, float3 target)
{
    return traceVisibilityRay(origin, target);
}

// Shared CV+RRR logic: VisCache hash table, local reservoir-local, or vanilla.
// RevalidationCommon.slang imports VisCache/ShadingCV when USE_VISCACHE=1,
// declares LocalRevalCB when USE_LOCAL_REVAL=1, and provides
// evaluateVisibility() + evalLocalRevalidation().
import RenderPasses.VisCache.RevalidationCommon;

// ---------------------------------------------------------------------------
// Neighbor selection (screen-space disk, DQLin pattern)
// ---------------------------------------------------------------------------
uint2 selectNeighbor(uint2 pixel, uint index, inout SampleGenerator sg)
{
    float angle  = sampleNext1D(sg) * (2.0f * M_PI);
    float radius = sqrt(sampleNext1D(sg)) * gSpatialRadius;
    int2 offset  = int2(cos(angle) * radius, sin(angle) * radius);
    int2 nbr     = int2(pixel) + offset;
    nbr = clamp(nbr, int2(0), int2(gFrameDim) - 1);
    return uint2(nbr);
}

// ---------------------------------------------------------------------------
// Evaluate target function for a neighbor's sample at this pixel's
// shading point (reconnection-based, with visibility).
// Returns: p_hat * visibility
// ---------------------------------------------------------------------------
float evalTargetAtPixel(ShadingData sd, SecondaryHit neighborSample,
                        float neighborTargetPdf,
                        inout SampleGenerator sg, out float pHatNoVis)
{
    pHatNoVis = 0.0f;
    if (luminance(neighborSample.Lo) < 1e-7f) return 0.0f;

    float3 toHit = neighborSample.posW - sd.posW;
    float  dist  = length(toHit);
    if (dist < 1e-6f) return 0.0f;

    float3 dir      = toHit / dist;
    float  cosTheta = dot(sd.N, dir);
    if (cosTheta <= 0.0f) return 0.0f;  // behind surface

    float cosHit = abs(dot(neighborSample.normalW, -dir));
    float G      = cosTheta * cosHit / (dist * dist + 1e-6f);

    // Approximate BSDF (diffuse for reconnection, consistent with DQLin)
    float3 bsdf = float3(cosTheta / M_PI);

    pHatNoVis = evalTargetPdf(bsdf, neighborSample.Lo, G);
    if (pHatNoVis < 1e-7f) return 0.0f;

    // Visibility — VisCache-gated, local CV+RRR, or unconditional
    // neighborTargetPdf is passed for the local CV+RRR mu estimate.
    float V = evaluateVisibility(sd.posW, neighborSample.posW,
                                  bsdf, neighborSample.Lo, G,
                                  neighborTargetPdf, pHatNoVis,
                                  gCamPos, sg);

    return pHatNoVis * V;
}

// ---------------------------------------------------------------------------
// Talbot MIS weight [Talbot et al. 2005]
// ---------------------------------------------------------------------------
#if USE_MIS
float computeTalbotMISWeight(float targetPdfHere, float M_here,
                              float targetPdfThere, float M_there)
{
    float num   = M_here * targetPdfHere;
    float denom = num + M_there * targetPdfThere;
    return (denom > 0.0f) ? (num / denom) : 0.0f;
}
#endif

// ---------------------------------------------------------------------------
// Main spatial reuse kernel
// ---------------------------------------------------------------------------
[numthreads(8, 8, 1)]
void csSpatialReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    PathReservoir reservoir = gReservoirs[pixelIdx];

    // Load shading data at this pixel
    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        gReservoirs[pixelIdx] = reservoir;
        return;
    }

    // Compute ray direction from camera (Falcor 8.0)
    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);

    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount * 13u + 3u);

    // Build output reservoir by merging current + k spatial neighbors
    PathReservoir merged;
    merged.reset();

    // Stream current pixel's reservoir first
    if (reservoir.isValid())
    {
        float w = reservoir.targetPdf * reservoir.W * reservoir.M;
        merged.M    += reservoir.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample    = reservoir.sample;
            merged.targetPdf = reservoir.targetPdf;
        }
    }

    // Track total neighbor M for MIS denominator
    float totalNeighborM = 0.0f;

    // ---------------------------------------------------------------
    // Spatial reuse loop: k neighbors
    // ---------------------------------------------------------------
    static const uint kNumSpatialNeighbors = NUM_SPATIAL_NEIGHBORS;

    for (uint i = 0; i < kNumSpatialNeighbors; i++)
    {
        // Select neighbor pixel
        uint2 nbrPixel = selectNeighbor(pixel, i, sg);
        uint  nbrIdx   = nbrPixel.y * gFrameDim.x + nbrPixel.x;

        PathReservoir neighbor = gReservoirs[nbrIdx];
        if (!neighbor.isValid()) continue;

        // Geometry validation: reject neighbors with different surfaces
        if (!geometryValid(sd.N, neighbor.sample.normalW, sd.posW, neighbor.sample.posW, 0.5f, 0.2f))
            continue;

        // Evaluate target function for neighbor's sample at this pixel
        // (includes visibility via VisCache or unconditional trace)
        float pHatNoVis;
        float pHatWithVis = evalTargetAtPixel(sd, neighbor.sample, neighbor.targetPdf, sg, pHatNoVis);

        if (pHatWithVis < 1e-7f) continue;

        // Clamp neighbor M for stability
        float nbrM = min(neighbor.M, kMaxSpatialM);

        // Compute weight for reservoir merge
        float w = pHatWithVis * neighbor.W * nbrM;

        merged.M    += nbrM;
        merged.wSum += w;
        totalNeighborM += nbrM;

        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample    = neighbor.sample;
            merged.targetPdf = pHatWithVis;
        }
    }

    merged.finalize();

    // Clamp total M for stability
    merged.M = min(merged.M, kMaxSpatialM);

    gReservoirs[pixelIdx] = merged;
}

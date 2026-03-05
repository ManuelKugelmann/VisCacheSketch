/***************************************************************************
 * SpatialReuse.cs.slang
 *
 * Spatial reuse pass for ReSTIR GI — Falcor 8.0 port of DQLin/ReSTIR_PT
 * with VisCache CV+RRR revalidation replacing unconditional V(P,Q) rays.
 *
 * At k=5 spatial neighbors, DQLin traces 5 shadow rays per pixel.
 * With VisCache enabled, evalRevalidationCV() gates these via cached
 * visibility, reducing to ~0.5–1.0 rays/pixel at steady state (§12).
 *
 * Unbiased: E[mu + (V - mu) / p] = E[V] for any cache quality.
 *
 * TODO: Merge full DQLin spatial reuse logic (neighbor selection,
 *       reservoir streaming, Talbot MIS weights) from the ported
 *       Falcor fork. This file contains the complete skeleton with
 *       VisCache integration points marked.
 ***************************************************************************/

import Scene.Scene;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

// VisCache integration
#if USE_VISCACHE
import RenderPasses.VisHashFilter.VisHashFilter;
import RenderPasses.VisHashFilter.ShadingCV;
#endif

// ---------------------------------------------------------------------------
// Reservoir data structures (match DQLin/ReSTIR_PT)
// ---------------------------------------------------------------------------
struct SecondaryHit
{
    float3 posW;
    float3 normalW;
    float3 Lo;       ///< Outgoing radiance at secondary hit
    float  invPDF;
};

struct PathReservoir
{
    SecondaryHit secondaryHit;
    float  W;        ///< Reservoir weight
    float  M;        ///< Sample count
    bool isValid() { return M > 0.0f && W > 0.0f; }
};

// ---------------------------------------------------------------------------
// Buffers
// ---------------------------------------------------------------------------
RWStructuredBuffer<PathReservoir> gReservoirs;
StructuredBuffer<SecondaryHit>    gSecondaryHits;

cbuffer PerFrameCB
{
    uint2  gFrameDim;
    float  gSpatialRadius;
    uint   gFrameCount;
    float3 gCamPos;
};

// ---------------------------------------------------------------------------
// Neighbor selection (screen-space disk, DQLin pattern)
// ---------------------------------------------------------------------------
uint2 selectNeighbor(uint2 pixel, uint index, inout SampleGenerator sg)
{
    float angle  = sampleNext1D(sg) * 6.28318530f;
    float radius = sqrt(sampleNext1D(sg)) * gSpatialRadius;
    int2 offset  = int2(cos(angle) * radius, sin(angle) * radius);
    int2 nbr     = int2(pixel) + offset;
    nbr = clamp(nbr, int2(0), int2(gFrameDim) - 1);
    return uint2(nbr);
}

// ---------------------------------------------------------------------------
// Visibility evaluation — two paths controlled by USE_VISCACHE
// ---------------------------------------------------------------------------
float evaluateVisibility(float3 P, float3 Q, float3 bsdf, float3 Lo,
                          float G, inout SampleGenerator sg)
{
#if USE_VISCACHE
    // CV+RRR revalidation (§12)
    // Replaces unconditional TraceVisibilityRay with cached + gated trace.
    return evalRevalidationCV(P, Q, bsdf, Lo, G, gCamPos, sg);
#else
    // Original DQLin: unconditional shadow ray
    RayDesc ray;
    ray.Origin    = P;
    ray.Direction = normalize(Q - P);
    ray.TMin      = 1e-4f;
    ray.TMax      = length(Q - P) - 1e-4f;

    // TODO: Use scene's TraceVisibilityRay or traceRayInline (DXR 1.1)
    // This is a placeholder — replace with DQLin's actual trace function.
    return traceShadowRay(P, Q);
#endif
}

// ---------------------------------------------------------------------------
// Main spatial reuse kernel
// ---------------------------------------------------------------------------
[numthreads(8, 8, 1)]
void csSpatialReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    // Load this pixel's reservoir and shading data
    PathReservoir reservoir = gReservoirs[pixelIdx];
    if (!reservoir.isValid()) return;

    // TODO: Load ShadingData from GBuffer / vbuffer at this pixel
    // ShadingData sd = loadShadingData(pixel);
    float3 P = float3(0);  // placeholder — load from GBuffer
    float3 N = float3(0, 1, 0);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount);

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

        float3 Q  = neighbor.secondaryHit.posW;
        float3 Lo = neighbor.secondaryHit.Lo;

        // Geometry term at the reconnection vertex
        float3 toQ   = Q - P;
        float  distPQ = length(toQ);
        if (distPQ < 1e-6f) continue;

        float3 dirPQ = toQ / distPQ;
        float  G     = abs(dot(N, dirPQ))
                      * abs(dot(neighbor.secondaryHit.normalW, -dirPQ))
                      / (distPQ * distPQ + 1e-6f);

        // TODO: Evaluate BSDF at P for direction dirPQ
        // float3 bsdf = evalBSDF(sd, dirPQ);
        float3 bsdf = float3(1.0f);  // placeholder

        float3 C = bsdf * Lo * G;

        // ----- VisCache integration point -----
        // evaluateVisibility() calls evalRevalidationCV() when USE_VISCACHE=1,
        // or unconditional trace when USE_VISCACHE=0.
        float Vest = evaluateVisibility(P, Q, bsdf, Lo, G, sg);

        // Contribution for reservoir update
        float contrib = luminance(C * Vest) * neighbor.secondaryHit.invPDF;

        // TODO: Talbot MIS weight (if USE_MIS)
        // float mis = computeTalbotMIS(reservoir, neighbor, ...);
        // contrib *= mis;

        // Reservoir merge (streaming RIS)
        reservoir.W += contrib;
        reservoir.M += neighbor.M;
        if (sampleNext1D(sg) < contrib / max(reservoir.W, 1e-20f))
        {
            reservoir.secondaryHit = neighbor.secondaryHit;
        }
    }

    // Normalize reservoir weight
    if (reservoir.M > 0.0f)
        reservoir.W /= reservoir.M;

    gReservoirs[pixelIdx] = reservoir;
}

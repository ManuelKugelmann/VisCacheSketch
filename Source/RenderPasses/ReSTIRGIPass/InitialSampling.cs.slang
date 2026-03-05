/***************************************************************************
 * InitialSampling.cs.slang
 *
 * Initial path trace sampling for ReSTIR GI — Falcor 8.0.
 * Traces one secondary ray per pixel and stores the result in a reservoir
 * and secondary-hit buffer for later temporal/spatial reuse.
 *
 * TODO: Port full DQLin/ReSTIR_PT initial sampling logic (Falcor 5.2 → 8.0).
 ***************************************************************************/

import Scene.Scene;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

// Reservoir data structures (shared with SpatialReuse.cs.slang)
struct SecondaryHit
{
    float3 posW;
    float3 normalW;
    float3 Lo;
    float  invPDF;
};

struct PathReservoir
{
    SecondaryHit secondaryHit;
    float W;
    float M;
};

RWStructuredBuffer<PathReservoir> gReservoirs;
RWStructuredBuffer<SecondaryHit>  gSecondaryHits;

cbuffer PerFrameCB
{
    uint   gFrameCount;
    uint2  gFrameDim;
};

[numthreads(8, 8, 1)]
void csInitialSampling(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount);

    // TODO: Load ShadingData from vbuffer and trace secondary ray.
    // For now, initialise an empty reservoir so downstream passes don't read garbage.
    PathReservoir reservoir;
    reservoir.secondaryHit.posW    = float3(0);
    reservoir.secondaryHit.normalW = float3(0, 1, 0);
    reservoir.secondaryHit.Lo      = float3(0);
    reservoir.secondaryHit.invPDF  = 0.0f;
    reservoir.W = 0.0f;
    reservoir.M = 0.0f;

    gReservoirs[pixelIdx]    = reservoir;
    gSecondaryHits[pixelIdx] = reservoir.secondaryHit;
}

/***************************************************************************
 * TemporalReuse.cs.slang
 *
 * Temporal reuse pass for ReSTIR GI — Falcor 8.0.
 * Reprojects previous-frame reservoirs via motion vectors and merges
 * them with current-frame reservoirs using streaming RIS.
 *
 * TODO: Port full DQLin/ReSTIR_PT temporal reuse logic (Falcor 5.2 → 8.0).
 ***************************************************************************/

import Scene.Scene;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

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
    bool isValid() { return M > 0.0f && W > 0.0f; }
};

RWStructuredBuffer<PathReservoir> gReservoirs;
StructuredBuffer<PathReservoir>   gPrevReservoirs;
StructuredBuffer<SecondaryHit>    gSecondaryHits;
Texture2D<float2>                 gMotionVectors;

cbuffer PerFrameCB
{
    uint2 gFrameDim;
};

[numthreads(8, 8, 1)]
void csTemporalReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    PathReservoir current = gReservoirs[pixelIdx];

    // Reproject via motion vectors
    float2 mv = gMotionVectors[pixel].xy;
    int2 prevPixel = int2(pixel) - int2(mv * float2(gFrameDim));
    prevPixel = clamp(prevPixel, int2(0), int2(gFrameDim) - 1);
    uint prevIdx = uint(prevPixel.y) * gFrameDim.x + uint(prevPixel.x);

    PathReservoir prev = gPrevReservoirs[prevIdx];

    // TODO: Full DQLin temporal merge with validity checks, M-cap, etc.
    // Placeholder: simple additive merge
    if (prev.isValid())
    {
        current.W += prev.W;
        current.M += prev.M;
    }

    gReservoirs[pixelIdx] = current;
}

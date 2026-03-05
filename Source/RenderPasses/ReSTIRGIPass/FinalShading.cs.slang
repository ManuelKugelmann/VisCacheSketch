/***************************************************************************
 * FinalShading.cs.slang
 *
 * Final shading pass for ReSTIR GI — Falcor 8.0.
 * Evaluates the selected reservoir sample and writes the indirect
 * illumination result to the output texture.
 *
 * TODO: Port full DQLin/ReSTIR_PT final shading logic (Falcor 5.2 → 8.0).
 ***************************************************************************/

import Utils.Math.MathHelpers;

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

StructuredBuffer<PathReservoir>  gReservoirs;
StructuredBuffer<SecondaryHit>   gSecondaryHits;
RWTexture2D<float4>              gColorOutput;

cbuffer PerFrameCB
{
    uint2 gFrameDim;
};

[numthreads(8, 8, 1)]
void csFinalShading(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    PathReservoir reservoir = gReservoirs[pixelIdx];

    float3 color = float3(0);
    if (reservoir.isValid())
    {
        // TODO: Full DQLin final shading with BSDF evaluation,
        // MIS weight normalisation, and reconnection.
        // Placeholder: output the weighted secondary-hit radiance.
        color = reservoir.secondaryHit.Lo * reservoir.W;
    }

    gColorOutput[pixel] = float4(color, 1.0f);
}

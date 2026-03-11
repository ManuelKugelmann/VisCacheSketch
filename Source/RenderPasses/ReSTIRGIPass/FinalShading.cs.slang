/***************************************************************************
 * FinalShading.cs.slang
 *
 * Final shading pass for ReSTIR GI — Falcor 8.0.
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 → 8.0).
 *
 * Evaluates the selected reservoir sample at the primary hit's shading
 * point: reconnection geometry term, BSDF evaluation, and reservoir
 * weight normalization. Outputs indirect illumination.
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
StructuredBuffer<PathReservoir>  gReservoirs;
StructuredBuffer<SecondaryHit>   gSecondaryHits;
RWTexture2D<float4>              gColorOutput;
Texture2D<PackedHitInfo>         gVBuffer;

cbuffer PerFrameCB
{
    uint2  gFrameDim;
    uint   gFrameCount;
    float3 gCamPos;
};

// loadSD() is defined in ReSTIRGICommon.slang

// ---------------------------------------------------------------------------
// Main kernel
// ---------------------------------------------------------------------------
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
        // Load shading data at primary hit
        HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
        if (hitInfo.isValid())
        {
            // Compute ray direction from camera (Falcor 8.0)
            TriangleHit priTri = hitInfo.getTriangleHit();
            VertexData priVert = gScene.getVertexData(priTri);
            float3 rayDir = normalize(priVert.posW - gCamPos);

            ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

            SecondaryHit selected = reservoir.sample;

            // Reconnection: evaluate BSDF and geometry term at primary hit
            // for the direction toward the selected secondary hit.
            float3 toHit = selected.posW - sd.posW;
            float  dist  = length(toHit);

            if (dist > 1e-6f)
            {
                float3 dir = toHit / dist;
                float  cosTheta = max(dot(sd.N, dir), 0.0f);
                float  cosHit   = abs(dot(selected.normalW, -dir));
                float  G        = cosTheta * cosHit / (dist * dist + 1e-6f);

                // BSDF evaluation at primary hit
                // DQLin uses diffuse approximation for reconnection:
                float3 bsdf = float3(cosTheta / M_PI);

                // Final contribution: BSDF * Lo * G * W
                // W already encodes the 1/(M * targetPdf) * wSum normalization.
                color = bsdf * selected.Lo * G * reservoir.W;

                // Clamp to prevent fireflies from rare high-weight samples
                float lum = luminance(color);
                if (lum > kFireflyClamp)
                    color *= kFireflyClamp / lum;
            }
        }
    }

    gColorOutput[pixel] = float4(color, 1.0f);
}

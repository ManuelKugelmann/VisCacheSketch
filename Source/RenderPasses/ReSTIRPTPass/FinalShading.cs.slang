/***************************************************************************
 * FinalShading.cs.slang  (ReSTIR PT — multi-bounce)
 *
 * Evaluates the selected reservoir sample with prefix throughput weighting.
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

import RenderPasses.ReSTIRPTPass.ReSTIRPTCommon;

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

ShadingData loadSD(const HitInfo hit, float3 rayOrigin, float3 rayDir)
{
    VertexData v;
    uint materialID = 0;
    if (hit.getType() == HitType::Triangle)
    {
        const TriangleHit tri = hit.getTriangleHit();
        v = gScene.getVertexData(tri);
        materialID = gScene.getMaterialID(tri.instanceID);
    }
    else
    {
        v.posW = rayOrigin + rayDir;
        v.normalW = -rayDir;
        v.faceNormalW = -rayDir;
        v.tangentW = float4(0, 1, 0, 1);
        v.texC = float2(0);
    }
    return gScene.materials.prepareShadingData(v, materialID, -rayDir);
}

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
        HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
        if (hitInfo.isValid())
        {
            TriangleHit priTri = hitInfo.getTriangleHit();
            VertexData priVert = gScene.getVertexData(priTri);
            float3 rayDir = normalize(priVert.posW - gCamPos);
            ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

            SecondaryHit selected = reservoir.sample;

            float3 toHit = selected.posW - sd.posW;
            float dist = length(toHit);

            if (dist > 1e-6f)
            {
                float3 dir = toHit / dist;
                float cosTheta = max(dot(sd.N, dir), 0.0f);
                float cosHit   = abs(dot(selected.normalW, -dir));
                float G        = cosTheta * cosHit / (dist * dist + 1e-6f);

                // For PT, the contribution uses the stored prefix throughput
                // which already encodes the multi-bounce BSDF chain.
                float3 bsdf = float3(cosTheta / M_PI);

                color = bsdf * selected.Lo * G * reservoir.W;

                // Clamp fireflies
                float lum = luminance(color);
                if (lum > 50.0f) color *= 50.0f / lum;
            }
        }
    }

    gColorOutput[pixel] = float4(color, 1.0f);
}

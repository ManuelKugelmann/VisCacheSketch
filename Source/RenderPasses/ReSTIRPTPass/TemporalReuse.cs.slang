/***************************************************************************
 * TemporalReuse.cs.slang  (ReSTIR PT — multi-bounce)
 *
 * Same structure as ReSTIRGIPass/TemporalReuse but with extended reservoir.
 ***************************************************************************/

import Scene.Scene;
import Scene.Shading;
import Scene.ShadingData;
import Scene.HitInfo;
import Utils.Math.MathHelpers;
import Utils.Sampling.SampleGenerator;

import RenderPasses.ReSTIRPTPass.ReSTIRPTCommon;

RWStructuredBuffer<PathReservoir> gReservoirs;
StructuredBuffer<PathReservoir>   gPrevReservoirs;
Texture2D<float2>                 gMotionVectors;
Texture2D<PackedHitInfo>          gVBuffer;

cbuffer PerFrameCB
{
    uint2  gFrameDim;
    uint   gFrameCount;
    float3 gCamPos;
};

// loadSD() is defined in ReSTIRPTCommon.slang

float evalTargetAtCurrentPixel(ShadingData sd, SecondaryHit prevSample)
{
    if (luminance(prevSample.Lo) < 1e-7f) return 0.0f;

    float3 toHit = prevSample.posW - sd.posW;
    float dist = length(toHit);
    if (dist < 1e-6f) return 0.0f;

    float3 dir = toHit / dist;
    float cosTheta = abs(dot(sd.N, dir));
    float cosHit   = abs(dot(prevSample.normalW, -dir));
    float G        = cosTheta * cosHit / (dist * dist + 1e-6f);

    float3 bsdf = float3(cosTheta / M_PI);
    return evalTargetPdf(bsdf, prevSample.Lo, G);
}

[numthreads(8, 8, 1)]
void csTemporalReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;
    PathReservoir current = gReservoirs[pixelIdx];

    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        gReservoirs[pixelIdx] = current;
        return;
    }

    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);
    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount * 7u + 1u);

    float2 mv = gMotionVectors[pixel].xy;
    int2 prevPixel = clamp(int2(pixel) - int2(mv * float2(gFrameDim)),
                           int2(0), int2(gFrameDim) - 1);
    uint prevIdx = uint(prevPixel.y) * gFrameDim.x + uint(prevPixel.x);

    PathReservoir prev = gPrevReservoirs[prevIdx];
    if (!prev.isValid())
    {
        gReservoirs[pixelIdx] = current;
        return;
    }

    if (!geometryValid(sd.N, prev.sample.normalW, sd.posW, prev.sample.posW, 0.9f, 0.1f))
    {
        gReservoirs[pixelIdx] = current;
        return;
    }

    prev.M = min(prev.M, kMaxTemporalM);

    float prevTargetAtCurrent = evalTargetAtCurrentPixel(sd, prev.sample);

    PathReservoir merged;
    merged.reset();

    if (current.isValid())
    {
        float w = current.targetPdf * current.W * current.M;
        merged.M += current.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample = current.sample;
            merged.targetPdf = current.targetPdf;
            merged.prefixThroughput = current.prefixThroughput;
            merged.reconnectDepth = current.reconnectDepth;
        }
    }

    {
        float w = prevTargetAtCurrent * prev.W * prev.M;
        merged.M += prev.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample = prev.sample;
            merged.targetPdf = prevTargetAtCurrent;
            merged.prefixThroughput = prev.prefixThroughput;
            merged.reconnectDepth = prev.reconnectDepth;
        }
    }

    merged.finalize();
    gReservoirs[pixelIdx] = merged;
}

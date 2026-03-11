/***************************************************************************
 * TemporalReuse.cs.slang
 *
 * Temporal reuse pass for ReSTIR GI — Falcor 8.0.
 * Ported from DQLin/ReSTIR_PT (Falcor 5.2 → 8.0).
 *
 * Reprojects previous-frame reservoirs via motion vectors, validates
 * geometric similarity, and merges with current-frame reservoirs using
 * streaming RIS with M-capping for temporal stability.
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
StructuredBuffer<PathReservoir>   gPrevReservoirs;
StructuredBuffer<SecondaryHit>    gSecondaryHits;  // bound but unused — kept for DQLin port fidelity
Texture2D<float2>                 gMotionVectors;
Texture2D<PackedHitInfo>          gVBuffer;

cbuffer PerFrameCB
{
    uint2  gFrameDim;
    uint   gFrameCount;
    float3 gCamPos;
};

// loadSD() is defined in ReSTIRGICommon.slang

// ---------------------------------------------------------------------------
// Evaluate the target function for the previous frame's sample at the
// current pixel's shading point (reconnection-based target pdf).
// ---------------------------------------------------------------------------
float evalTargetAtCurrentPixel(ShadingData sd, SecondaryHit prevSample)
{
    if (luminance(prevSample.Lo) < 1e-7f) return 0.0f;

    float3 toHit = prevSample.posW - sd.posW;
    float  dist  = length(toHit);
    if (dist < 1e-6f) return 0.0f;

    float3 dir = toHit / dist;
    float  cosTheta = abs(dot(sd.N, dir));
    float  cosHit   = abs(dot(prevSample.normalW, -dir));
    float  G        = cosTheta * cosHit / (dist * dist + 1e-6f);

    // Approximate BSDF as diffuse (consistent with DQLin's reconnection approach)
    float3 bsdf = float3(cosTheta / M_PI);

    return evalTargetPdf(bsdf, prevSample.Lo, G);
}

// ---------------------------------------------------------------------------
// Main kernel
// ---------------------------------------------------------------------------
[numthreads(8, 8, 1)]
void csTemporalReuse(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gFrameDim)) return;

    uint pixelIdx = pixel.y * gFrameDim.x + pixel.x;

    PathReservoir current = gReservoirs[pixelIdx];

    // Load current pixel's shading data for target function evaluation
    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid())
    {
        // No valid primary hit — keep current reservoir as-is
        gReservoirs[pixelIdx] = current;
        return;
    }

    // Compute ray direction from camera (Falcor 8.0)
    TriangleHit priTri = hitInfo.getTriangleHit();
    VertexData priVert = gScene.getVertexData(priTri);
    float3 rayDir = normalize(priVert.posW - gCamPos);

    ShadingData sd = loadSD(hitInfo, gCamPos, rayDir);

    SampleGenerator sg = SampleGenerator::create(pixel, gFrameCount * 7u + 1u);

    // Reproject via motion vectors
    float2 mv = gMotionVectors[pixel].xy;
    int2 prevPixel = int2(pixel) - int2(mv * float2(gFrameDim));
    prevPixel = clamp(prevPixel, int2(0), int2(gFrameDim) - 1);
    uint prevIdx = uint(prevPixel.y) * gFrameDim.x + uint(prevPixel.x);

    PathReservoir prev = gPrevReservoirs[prevIdx];

    // Skip if previous reservoir is invalid
    if (!prev.isValid())
    {
        gReservoirs[pixelIdx] = current;
        return;
    }

    // Geometry validation: reject if surface changed significantly
    if (!geometryValid(sd.N, prev.sample.normalW, sd.posW, prev.sample.posW, 0.9f, 0.1f))
    {
        // Geometry mismatch — discard temporal history
        gReservoirs[pixelIdx] = current;
        return;
    }

    // M-cap: clamp previous reservoir's M to prevent unbounded history
    prev.M = min(prev.M, kMaxTemporalM);

    // Evaluate target function for previous sample at current pixel
    float prevTargetAtCurrent = evalTargetAtCurrentPixel(sd, prev.sample);

    // Build output reservoir by merging current + previous
    PathReservoir merged;
    merged.reset();

    // Stream current sample
    if (current.isValid())
    {
        float w = current.targetPdf * current.W * current.M;
        merged.M    += current.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample    = current.sample;
            merged.targetPdf = current.targetPdf;
        }
    }

    // Stream previous sample
    {
        float w = prevTargetAtCurrent * prev.W * prev.M;
        merged.M    += prev.M;
        merged.wSum += w;
        if (merged.wSum > 0.0f && sampleNext1D(sg) * merged.wSum < w)
        {
            merged.sample    = prev.sample;
            merged.targetPdf = prevTargetAtCurrent;
        }
    }

    merged.finalize();

    gReservoirs[pixelIdx] = merged;
}

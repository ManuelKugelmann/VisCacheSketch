/***************************************************************************
 # Copyright (c) 2026, ManuelKugelmann/VisCacheSketch.
 #
 # IEmissiveLightSampler implementation that uses RTXDI's pdf-mipmap layout
 # to draw emissive triangles in O(log N). Returns AREA-domain pdf in
 # `ls.pdf` so reservoir reuse across pixels is unbiased under Convention B
 # (`w = pHat × invSourcePdf`).
 *
 # Inlines RTXDI_SamplePdfMipmap (from rtxdi/ResamplingFunctions.hlsli) to
 # avoid pulling the full RTXDI sampling machinery; the algorithm is
 # mathematically identical (hierarchical 4-way mip descent).
 **************************************************************************/
#include "Utils/Math/MathConstants.slangh"

import Scene.Scene;
import Utils.Sampling.SampleGeneratorInterface;
import Rendering.Lights.EmissiveLightSamplerHelpers;
import Rendering.Lights.EmissiveLightSamplerInterface;

#include "rtxdi/RtxdiMath.hlsli"

struct EmissivePdfMipmap
{
    uint                pdfTextureWidth;
    uint                pdfTextureHeight;
    float               invTotalFlux;
    Texture2D<float>    localLightPdf;
};

/** Hierarchical 4-way mipmap sampler — inlined RTXDI_SamplePdfMipmap.
    \param[in,out] sg Sample generator.
    \param[in] tex Pdf texture with full mip chain.
    \param[in] dim Mip-0 dimensions (square pow2).
    \param[out] position Z-curve texel position at mip-0.
    \param[out] pdf Selection probability under the mipmap distribution.
*/
void wsSamplePdfMipmap<S : ISampleGenerator>(
    inout S sg, Texture2D<float> tex, uint2 dim, out uint2 position, out float pdf)
{
    int lastMipLevel = max(0, int(floor(log2(max(dim.x, dim.y)))) - 1);
    position = uint2(0u, 0u);
    pdf = 1.f;
    for (int mipLevel = lastMipLevel; mipLevel >= 0; --mipLevel)
    {
        position *= 2u;
        float4 samples;
        samples.x = max(0.f, tex.Load(int3(position.x + 0, position.y + 0, mipLevel)).x);
        samples.y = max(0.f, tex.Load(int3(position.x + 0, position.y + 1, mipLevel)).x);
        samples.z = max(0.f, tex.Load(int3(position.x + 1, position.y + 0, mipLevel)).x);
        samples.w = max(0.f, tex.Load(int3(position.x + 1, position.y + 1, mipLevel)).x);
        float weightSum = samples.x + samples.y + samples.z + samples.w;
        if (weightSum <= 0.f) { pdf = 0.f; return; }
        samples /= weightSum;
        float r = sampleNext1D(sg);
        if (r < samples.x) { pdf *= samples.x; }
        else { r -= samples.x;
            if (r < samples.y) { position += uint2(0, 1); pdf *= samples.y; }
            else { r -= samples.y;
                if (r < samples.z) { position += uint2(1, 0); pdf *= samples.z; }
                else                { position += uint2(1, 1); pdf *= samples.w; }
            }
        }
    }
}

/** EmissiveLightSampler that samples emissive triangles via a pdf-mipmap.
    Returns SOLID-ANGLE pdf in ls.pdf, matching EmissivePowerSampler's
    convention so vanilla NEE works directly. Reservoir-reuse paths recover
    AREA-domain pdf at the pool-insert site (where they have access to the
    sampled triangle's area + light normal).
*/
struct EmissivePdfMipmapSampler : IEmissiveLightSampler
{
    EmissivePdfMipmap _emissivePdfMipmap;

    bool sampleLight<S : ISampleGenerator>(const float3 posW, const float3 normalW, const bool upperHemisphere, inout S sg, out TriangleLightSample ls)
    {
        ls = {};
        if (gScene.lightCollection.isEmpty()) return false;

        uint2 dim = uint2(_emissivePdfMipmap.pdfTextureWidth, _emissivePdfMipmap.pdfTextureHeight);
        uint2 texelPos;
        float mipPdf;
        wsSamplePdfMipmap(sg, _emissivePdfMipmap.localLightPdf, dim, texelPos, mipPdf);
        if (mipPdf <= 0.f) return false;

        uint triangleIndex = RTXDI_ZCurveToLinearIndex(texelPos);
        if (triangleIndex >= gScene.lightCollection.triangleCount) return false;

        float2 u = sampleNext2D(sg);
        if (!sampleTriangle(posW, triangleIndex, u, ls)) return false;

        // Selection pdf via Power-equivalent flux/totalFlux (matches the
        // mipmap's distribution and avoids descent-pdf accumulation issues
        // with box-filter mipgen). ls.pdf was set to solid-angle pdf by
        // sampleTriangle; multiplying by selection pdf gives joint solid-angle.
        float fluxT = gScene.lightCollection.fluxData[triangleIndex].flux;
        ls.pdf *= fluxT * _emissivePdfMipmap.invTotalFlux;
        return true;
    }

    void skipRandomNumber<S : ISampleGenerator>(inout S sg)
    {
        if (gScene.lightCollection.isEmpty()) return;
        // Mipmap descent consumes 1 random per mip level.
        uint dim = max(_emissivePdfMipmap.pdfTextureWidth, _emissivePdfMipmap.pdfTextureHeight);
        int lastMipLevel = max(0, int(floor(log2(float(dim)))) - 1);
        for (int i = 0; i <= lastMipLevel; ++i) sampleNext1D(sg);
        sampleNext2D(sg);   // triangle barys
    }

    float evalTriangleSelectionPdf(const float3 posW, const float3 normalW, const bool upperHemisphere, const uint triangleIndex)
    {
        if (triangleIndex == LightCollection::kInvalidIndex) return 0.f;
        return gScene.lightCollection.fluxData[triangleIndex].flux * _emissivePdfMipmap.invTotalFlux;
    }

    float evalPdf(const float3 posW, const float3 normalW, const bool upperHemisphere, const TriangleLightHit hit)
    {
        if (hit.triangleIndex == LightCollection::kInvalidIndex) return 0.f;
        float triangleSelectionPdf = evalTriangleSelectionPdf(posW, normalW, upperHemisphere, hit.triangleIndex);
        float trianglePdf = evalTrianglePdf(posW, hit);
        return triangleSelectionPdf * trianglePdf;
    }
};

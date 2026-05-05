/***************************************************************************
 # Copyright (c) 2026, ManuelKugelmann/VisCacheSketch.
 #
 # Reuses RTXDI's pdf-mipmap algorithms (rtxdi/RtxdiMath.hlsli) without
 # modifying them. CPU-side build: read MeshLightTriangle.flux from the
 # ILightCollection and place fluxes in z-curve layout in mip-0; Falcor's
 # generateMips builds the chain. The slang sample path (in
 # EmissivePdfMipmapSampler.slang) traverses the chain hierarchically to
 # produce area-domain pdfs.
 **************************************************************************/
#include "EmissivePdfMipmapSampler.h"
#include "Core/API/RenderContext.h"
#include "Utils/Timing/Profiler.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace Falcor
{
    namespace
    {
        // C++ inline of RTXDI's z-curve helpers (rtxdi/RtxdiMath.hlsli);
        // re-implemented because the .hlsli is HLSL-only and can't be
        // included directly. Layout matches the slang sampler exactly.
        static uint32_t rtxdiIntegerCompact(uint32_t x)
        {
            x = (x & 0x11111111u) | ((x & 0x44444444u) >> 1u);
            x = (x & 0x03030303u) | ((x & 0x30303030u) >> 2u);
            x = (x & 0x000F000Fu) | ((x & 0x0F000F00u) >> 4u);
            x = (x & 0x000000FFu) | ((x & 0x00FF0000u) >> 8u);
            return x;
        }
        struct ZCurvePos { uint32_t x; uint32_t y; };
        static ZCurvePos rtxdiLinearIndexToZCurve(uint32_t i)
        {
            return ZCurvePos{ rtxdiIntegerCompact(i), rtxdiIntegerCompact(i >> 1u) };
        }

        // pdf-mipmap is square pow2 sized so width² ≥ numTriangles.
        // 16k cap matches RTXDI_LinearIndexToZCurve assumptions.
        const uint32_t kMaxPdfMipmapSide = 16384u;

        uint32_t computeSide(uint32_t numTriangles)
        {
            if (numTriangles == 0u) return 1u;
            uint32_t side = 1u;
            while (side * side < numTriangles) side <<= 1u;
            return std::min(side, kMaxPdfMipmapSide);
        }
    }

    EmissivePdfMipmapSampler::EmissivePdfMipmapSampler(
        RenderContext* pRenderContext, ref<ILightCollection> pLightCollection)
        : EmissiveLightSampler(EmissiveLightSamplerType::PdfMipmap, std::move(pLightCollection))
    {
        FALCOR_ASSERT(pRenderContext);
    }

    bool EmissivePdfMipmapSampler::update(RenderContext* pRenderContext, ref<ILightCollection> pLightCollection)
    {
        FALCOR_PROFILE(pRenderContext, "EmissivePdfMipmapSampler::update");

        bool samplerChanged = false;
        if (mpLightCollection != pLightCollection)
        {
            setLightCollection(std::move(pLightCollection));
            mNeedsRebuild = true;
        }
        if (mLightCollectionUpdateFlags != ILightCollection::UpdateFlags::None)
        {
            mNeedsRebuild = true;
            mLightCollectionUpdateFlags = ILightCollection::UpdateFlags::None;
        }

        if (mNeedsRebuild)
        {
            FALCOR_ASSERT(mpLightCollection);
            const auto& triangles = mpLightCollection->getMeshLightTriangles(pRenderContext);
            const uint32_t numTriangles = (uint32_t)triangles.size();
            const uint32_t side = computeSide(numTriangles);

            // (Re)allocate texture if size changed.
            if (!mpLocalLightPdf || mPdfTextureWidth != side)
            {
                const uint32_t mipLevels = Texture::kMaxPossible;
                mpLocalLightPdf = mpDevice->createTexture2D(
                    side, side, ResourceFormat::R32Float, 1u, mipLevels,
                    nullptr,
                    ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess |
                    ResourceBindFlags::RenderTarget);
                mpLocalLightPdf->setName("EmissivePdfMipmapSampler::localLightPdf");
                mPdfTextureWidth = side;
                mPdfTextureHeight = side;
            }

            // Build mip-0 on CPU: place each triangle's flux at its z-curve
            // texel. Out-of-range cells stay zero so the hierarchical sampler
            // can never select them. Also accumulate total flux for Power-
            // style selection pdf computation in the slang sampleLight.
            std::vector<float> mip0(side * side, 0.f);
            double totalFlux = 0.0;
            for (uint32_t i = 0u; i < numTriangles; ++i)
            {
                if (triangles[i].flux <= 0.f) continue;
                totalFlux += triangles[i].flux;
                ZCurvePos zc = rtxdiLinearIndexToZCurve(i);
                if (zc.x < side && zc.y < side)
                {
                    mip0[zc.y * side + zc.x] = triangles[i].flux;
                }
            }
            mInvTotalFlux = (totalFlux > 0.0) ? (float)(1.0 / totalFlux) : 0.f;

            // Upload mip-0; auto-generate the chain for hierarchical sampling.
            pRenderContext->updateSubresourceData(mpLocalLightPdf.get(), 0u, mip0.data());
            mpLocalLightPdf->generateMips(pRenderContext);

            mNeedsRebuild = false;
            samplerChanged = true;
        }
        return samplerChanged;
    }

    void EmissivePdfMipmapSampler::bindShaderData(const ShaderVar& var) const
    {
        FALCOR_ASSERT(var.isValid());
        var["_emissivePdfMipmap"]["pdfTextureWidth"] = mPdfTextureWidth;
        var["_emissivePdfMipmap"]["pdfTextureHeight"] = mPdfTextureHeight;
        var["_emissivePdfMipmap"]["invTotalFlux"] = mInvTotalFlux;
        var["_emissivePdfMipmap"]["localLightPdf"] = mpLocalLightPdf;
    }
}

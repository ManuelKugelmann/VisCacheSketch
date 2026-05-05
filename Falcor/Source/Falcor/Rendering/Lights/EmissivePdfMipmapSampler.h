/***************************************************************************
 # Copyright (c) 2026, ManuelKugelmann/VisCacheSketch.
 #
 # Sampler peer to EmissivePowerSampler that returns AREA-domain pdfs by
 # sampling RTXDI's hierarchical pdf-mipmap structure. The shading-point
 # arguments to sampleLight() are accepted for interface compatibility but
 # the returned `pdf` is position-invariant (area domain) — this enables
 # Convention B reservoir reuse without solid-angle-jacobian fireflies.
 #
 # Contrast with EmissivePowerSampler:
 #   - PowerSampler: alias table → triangle index → barycentric → solid-angle pdf
 #   - PdfMipmapSampler: hierarchical mipmap descent → triangle index → barycentric → AREA pdf
 #
 # Implementation reuses RTXDI's RTXDI_LinearIndexToZCurve layout and
 # RTXDI_SamplePdfMipmap traversal (rtxdi/RtxdiMath.hlsli + ResamplingFunctions.hlsli);
 # the host-side build is a small kernel that fills mip-0 with triangle flux,
 # then Falcor's blit auto-generates the chain.
 **************************************************************************/
#pragma once
#include "EmissiveLightSampler.h"
#include "Core/Macros.h"
#include "Scene/Lights/LightCollection.h"
#include <vector>

namespace Falcor
{
    class RenderContext;
    struct ShaderVar;

    /** Sample emissive triangles via a hierarchical pdf-mipmap (RTXDI parity).
        Returns area-domain pdf — position-invariant, enabling unbiased
        cross-pixel reservoir reuse (Convention B `w = pHat × invSourcePdf`).
    */
    class FALCOR_API EmissivePdfMipmapSampler : public EmissiveLightSampler
    {
    public:
        /** Creates an EmissivePdfMipmapSampler for a given scene.
            \param[in] pRenderContext The render context.
            \param[in] pLightCollection The light collection.
        */
        EmissivePdfMipmapSampler(RenderContext* pRenderContext, ref<ILightCollection> pLightCollection);
        virtual ~EmissivePdfMipmapSampler() = default;

        /** Updates the sampler to the current frame.
            Rebuilds the local-light pdf texture mip chain when the light
            collection has changed. Called once per frame from the host.
            \param[in] pRenderContext The render context.
            \param[in] pLightCollection Updated LightCollection.
            \return True if the sampler was updated.
        */
        virtual bool update(RenderContext* pRenderContext, ref<ILightCollection> pLightCollection) override;

        /** Bind the sampler data to a given shader variable.
            Exposes localLightPdf SRV + texture dim to the slang struct.
            \param[in] var Shader variable.
        */
        virtual void bindShaderData(const ShaderVar& var) const override;

    protected:
        // pdf-mipmap state — analogous to EmissivePowerSampler::AliasTable.
        // CPU build: place per-triangle flux in z-curve layout in mip-0,
        // then Falcor's generateMips builds the hierarchical chain.
        ref<Texture>     mpLocalLightPdf;          ///< Mip-0 = per-triangle flux; full chain auto-generated.
        uint32_t         mPdfTextureWidth = 0u;    ///< Mip-0 width (equal to height; pow2 ≥ ceil(sqrt(numTriangles))).
        uint32_t         mPdfTextureHeight = 0u;
        float            mInvTotalFlux = 0.f;      ///< 1 / sum of all triangle flux (for Power-style selection pdf).
        bool             mNeedsRebuild = true;     ///< Trigger rebuild on the next update().
    };
}

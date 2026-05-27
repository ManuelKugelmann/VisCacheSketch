/***************************************************************************
 # NRDHelpers.slang — shared NRD-buffer writer surface.
 #
 # Lifts the bit-identical NRD-writer bodies that every PT-lineage plugin
 # (PathTracerX + ReSTIRDIPass + ReSTIRDIReferencePass + ReSTIRNEEPass) used
 # to copy verbatim, behind a small `IPathStateNRD` interface so each plugin
 # can keep its own divergent `PathState` shape (NEE has K-RIS state, etc.).
 *************************************************************************/
import Rendering.Materials.IMaterialInstance;
import Rendering.Materials.IsotropicGGX;
import RenderPasses.Shared.Denoising.NRDBuffers;
import RenderPasses.Shared.Denoising.NRDConstants;
import RenderPasses.Shared.Denoising.NRDHelpers;
import Scene.Scene;
import Scene.ShadingData;
import Utils.Math.MathHelpers;
import RenderPasses.PathTraceCommon.IPathStateNRD;

void setNRDPrimaryHitEmission<P : IPathStateNRD>(NRDBuffers outputNRD, const bool useNRDDemodulation, const P path, const uint2 pixel, const bool isPrimaryHit, const float3 emission)
{
    if (isPrimaryHit && path.getSampleIdx() == 0)
    {
        // Generate primary hit guide buffers.
        if (useNRDDemodulation)
        {
            outputNRD.primaryHitEmission[pixel] = float4(emission, 1.f);
        }
        else
        {
            // Clear buffers on primary hit only if demodulation is disabled.
            outputNRD.primaryHitEmission[pixel] = 0.f;
        }
    }
}

void setNRDPrimaryHitReflectance<P : IPathStateNRD>(NRDBuffers outputNRD, const bool useNRDDemodulation, const P path, const uint2 pixel, const bool isPrimaryHit, const ShadingData sd, const BSDFProperties bsdfProperties)
{
    if (isPrimaryHit && path.getSampleIdx() == 0)
    {
        // Generate primary hit guide buffers.
        if (useNRDDemodulation)
        {
            // Use sum of reflection/transmission albedo as they are denoised together.
            const float3 diffuseReflectance = max(kNRDMinReflectance, bsdfProperties.diffuseReflectionAlbedo + bsdfProperties.diffuseTransmissionAlbedo);
            outputNRD.primaryHitDiffuseReflectance[pixel] = float4(diffuseReflectance, 1.f);

            // We use an approximate shading model with a single specular lobe.
            const float NdotV = saturate(dot(bsdfProperties.guideNormal, sd.V));
            const float ggxAlpha = bsdfProperties.roughness * bsdfProperties.roughness;
            float3 specularReflectance = approxSpecularIntegralGGX(bsdfProperties.specularReflectionAlbedo, ggxAlpha, NdotV);
            specularReflectance = max(kNRDMinReflectance, specularReflectance);
            outputNRD.primaryHitSpecularReflectance[pixel] = float4(specularReflectance, 1.f);
        }
        else
        {
            // Clear buffers on primary hit only if demodulation is disabled.
            outputNRD.primaryHitDiffuseReflectance[pixel] = 1.f;
            outputNRD.primaryHitSpecularReflectance[pixel] = 1.f;
        }
    }
}

void setNRDSampleHitDist<P : IPathStateNRD>(NRDBuffers outputNRD, const P path, const uint outSampleIdx)
{
    if (path.getVertexIndex() == 2)
    {
        outputNRD.sampleHitDist[outSampleIdx] = path.getSceneLengthF32();
    }
}

void setNRDPrimaryHitSeparatedRadiance<P : IPathStateNRD>(NRDBuffers outputNRD, const bool useNRDDemodulation, const P path, const bool isPrimaryHit, const uint outSampleIdx)
{
    if (isPrimaryHit)
    {
        if (useNRDDemodulation && path.isDeltaReflectionPrimaryHit())
        {
            outputNRD.samplePrimaryHitNEEOnDelta[outSampleIdx] = float4(path.getL(), 0);
        }
        else
        {
            outputNRD.samplePrimaryHitNEEOnDelta[outSampleIdx] = float4(0.f);
        }
    }
}

void setNRDSampleEmission<P : IPathStateNRD>(NRDBuffers outputNRD, const bool useNRDDemodulation, const P path, const uint outSampleIdx, const bool isPrimaryHit, const float3 emission, const bool wasDeltaOnlyPathBeforeScattering)
{
    if (useNRDDemodulation)
    {
        // Always demodulate emission on the primary hit (it seconds as a clear).
        if (isPrimaryHit)
        {
            outputNRD.sampleEmission[outSampleIdx] = float4(emission, 1.f);
        }
        // Additionally, accumulate emission along the delta path.
        else if ((path.isDeltaReflectionPrimaryHit() || path.isDeltaTransmissionPath()) && any(emission > 0.f))
        {
            const bool demodulateDeltaReflectionEmission = path.isDeltaReflectionPrimaryHit() && wasDeltaOnlyPathBeforeScattering;
            const bool demodulateDeltaTransmissionEmission = path.isDeltaTransmissionPath() && wasDeltaOnlyPathBeforeScattering;
            if (demodulateDeltaReflectionEmission || demodulateDeltaTransmissionEmission)
            {
                float3 prevEmission = outputNRD.sampleEmission[outSampleIdx].rgb;
                outputNRD.sampleEmission[outSampleIdx] = float4(prevEmission + emission, 1.f);
            }
        }
    }
    else if (isPrimaryHit)
    {
        outputNRD.sampleEmission[outSampleIdx] = 0.f;
    }
}

void setNRDSampleReflectance<P : IPathStateNRD>(NRDBuffers outputNRD, const bool useNRDDemodulation, const P path, const uint outSampleIdx, const bool isPrimaryHit, const ShadingData sd, const BSDFProperties bsdfProperties, const uint lobeTypes, const bool wasDeltaOnlyPathBeforeScattering)
{
    // Demodulate reflectance.
    if (useNRDDemodulation)
    {
        const bool hasDeltaLobes = (lobeTypes & (uint)LobeType::Delta) != 0;
        const bool hasNonDeltaLobes = (lobeTypes & (uint)LobeType::NonDelta) != 0;

        // Always demodulate reflectance from diffuse and specular paths on the primary hit (it seconds as a clear).
        if (isPrimaryHit)
        {
            if (path.isDiffusePrimaryHit())
            {
                // Use sum of reflection/transmission albedo as they are denoised together.
                const float3 diffuseReflectance = max(kNRDMinReflectance, bsdfProperties.diffuseReflectionAlbedo + bsdfProperties.diffuseTransmissionAlbedo);
                outputNRD.sampleReflectance[outSampleIdx] = float4(diffuseReflectance, 1.f);
            }
            else if (path.isSpecularPrimaryHit())
            {
                // We use an approximate shading model with a single specular lobe.
                const float NdotV = saturate(dot(bsdfProperties.guideNormal, sd.V));
                const float ggxAlpha = bsdfProperties.roughness * bsdfProperties.roughness;
                float3 specularReflectance = approxSpecularIntegralGGX(bsdfProperties.specularReflectionAlbedo, ggxAlpha, NdotV);
                specularReflectance = max(kNRDMinReflectance, specularReflectance);
                outputNRD.sampleReflectance[outSampleIdx] = float4(specularReflectance, 1.f);
            }
            else
            {
                outputNRD.sampleReflectance[outSampleIdx] = 1.f;
            }
        }
        // Demodulate reflectance from the second vertex along delta reflection paths.
        else if (path.isDeltaReflectionPrimaryHit() && wasDeltaOnlyPathBeforeScattering && hasNonDeltaLobes)
        {
            const MaterialType materialType = sd.mtl.getMaterialType();
            const bool hasDeltaLobes = (lobeTypes & (uint)LobeType::Delta) != 0;
            float3 deltaReflectance = getMaterialReflectanceForDeltaPaths(materialType, hasDeltaLobes, sd, bsdfProperties);

            outputNRD.sampleReflectance[outSampleIdx] = float4(deltaReflectance, 1.f);
        }
        // Demodulate reflectance from the first non-delta vertex along delta transmission paths.
        else if (path.isDeltaTransmissionPath() && wasDeltaOnlyPathBeforeScattering && hasNonDeltaLobes)
        {
            const MaterialType materialType = sd.mtl.getMaterialType();
            const bool hasDeltaLobes = (lobeTypes & (uint)LobeType::Delta) != 0;
            float3 deltaReflectance = getMaterialReflectanceForDeltaPaths(materialType, hasDeltaLobes, sd, bsdfProperties);

            outputNRD.sampleReflectance[outSampleIdx] = float4(deltaReflectance, 1.f);
        }
    }
    else if (isPrimaryHit)
    {
        outputNRD.sampleReflectance[outSampleIdx] = 1.f;
    }
}

/** Write out delta reflection guide buffers.
    Executed only for guide paths.
*/
void writeNRDDeltaReflectionGuideBuffers(NRDBuffers outputNRD, const bool useNRDDemodulation, const uint2 pixelPos, float3 reflectance, float3 emission, float3 normal, float roughness, float pathLength, float hitDist)
{
    emission = useNRDDemodulation ? emission : 0.f;
    reflectance = useNRDDemodulation ? max(kNRDMinReflectance, reflectance) : 1.f;

    float2 octNormal = ndir_to_oct_unorm(normal);
    // Clamp roughness so it's representable of what is actually used in the renderer.
    float clampedRoughness = roughness < 0.08f ? 0.00f : roughness;
    float materialID = 0.f;

    outputNRD.deltaReflectionEmission[pixelPos] = float4(emission, 0.f);
    outputNRD.deltaReflectionReflectance[pixelPos] = float4(reflectance, 0.f);
    outputNRD.deltaReflectionNormWRoughMaterialID[pixelPos] = float4(octNormal, clampedRoughness, materialID);
    outputNRD.deltaReflectionPathLength[pixelPos] = pathLength;
    outputNRD.deltaReflectionHitDist[pixelPos] = hitDist;
}

/** Write out delta transmission guide buffers.
    Executed only for guide paths.
*/
void writeNRDDeltaTransmissionGuideBuffers(NRDBuffers outputNRD, const bool useNRDDemodulation, const uint2 pixelPos, float3 reflectance, float3 emission, float3 normal, float roughness, float pathLength, float3 posW)
{
    emission = useNRDDemodulation ? emission : 0.f;
    reflectance = useNRDDemodulation ? max(kNRDMinReflectance, reflectance) : 1.f;

    float2 octNormal = ndir_to_oct_unorm(normal);
    // Clamp roughness so it's representable of what is actually used in the renderer.
    float clampedRoughness = roughness < 0.08f ? 0.00f : roughness;
    float materialID = 0.f;

    outputNRD.deltaTransmissionEmission[pixelPos] = float4(emission, 0.f);
    outputNRD.deltaTransmissionReflectance[pixelPos] = float4(reflectance, 0.f);
    outputNRD.deltaTransmissionNormWRoughMaterialID[pixelPos] = float4(octNormal, clampedRoughness, materialID);
    outputNRD.deltaTransmissionPathLength[pixelPos] = pathLength;
    outputNRD.deltaTransmissionPosW[pixelPos] = float4(posW, 0.f);
}

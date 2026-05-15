/***************************************************************************
 # Copyright (c) 2015-24, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
import Rendering.Lights.EnvMapSampler;
import Rendering.Lights.EmissiveLightSampler;
import Rendering.Lights.EmissiveLightSamplerHelpers;
import Rendering.Lights.LightHelpers;
import Rendering.Materials.IsotropicGGX;
import Rendering.Materials.InteriorListHelpers;
import Rendering.Volumes.HomogeneousVolumeSampler;
import Rendering.Utils.PixelStats;
import RenderPasses.Shared.Denoising.NRDConstants;
import RenderPasses.Shared.Denoising.NRDBuffers;
import RenderPasses.Shared.Denoising.NRDData;
import RenderPasses.Shared.Denoising.NRDHelpers;
import Utils.Color.ColorHelpers;
import Utils.Geometry.GeometryHelpers;
import Utils.Debug.PixelDebug;
import LoadShadingData;
import ColorType;
import NRDHelpers;
__exported import PathState;
__exported import Params;
import Rendering.RTXDI.RTXDI;

// Phase 3d Step 1: shared light-sample rebuilders + LightType/LightSampleDI types.
// Plugin keeps its nested LightType/LightSampleDI inside `struct PathTracer` for
// now (more specific scope wins); Step 2 will remove the nested types and let
// these imports be the canonical source.
import RenderPasses.PathTraceCommon.PathTraceCore;
import RenderPasses.ReSTIRCommon.LightReservoir;

#if USE_WS_RESERVOIRS
import RenderPasses.ReSTIRCommon.Reservoir;
import RenderPasses.ReSTIRCommon.ReservoirIO;
import RenderPasses.ReSTIRCommon.CellPool;
import RenderPasses.ReSTIRCommon.CellPoolIO;
import RenderPasses.VisCache.VisCache;   // VisCacheParams cbuffer (gWS*, vhfLookup)
import Utils.Math.MathHelpers;           // sample_triangle for emissive uv → barys
#include "Utils/Math/MathConstants.slangh"  // FLT_MIN
#elif USE_VISCACHE && USE_VISCACHE_LIGHTSELECTION
import RenderPasses.VisCache.VisCache;   // vhfLookup, VHFResult, gLightMuMin
#endif

// vcDiagCountRay() helper for ray-counter bumps at the WS-ReSTIR V-test sites
// that don't go through the cache's vhfGate/vhfCommit path. Lives in
// VisCacheDiagnostics.slang alongside the diag textures it writes.
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif

/** Interface for querying visibility in the scene.
    This is used in `handleHit`.
*/
interface IVisibilityQuery
{
    /** Trace a visibility ray against the scene.
        \param[in] ray Ray.
        \return Returns true if the ray endpoints are mutually visible (i.e. the ray does NOT intersect the scene).
    */
    [mutating] bool traceVisibilityRay(const Ray ray);

#if USE_VISCACHE_VISIBILITYCHECK
    /** CV+RRR visibility query via VisCache. Returns fractional visWeight in [0,1].
        \param[in] ray Shadow ray to evaluate.
        \param[in,out] sg Sample generator for RR coin flip.
        \return Unbiased CV+RRR visibility weight.
    */
    [mutating] float traceVisibilityRayCV(const Ray ray, inout SampleGenerator sg, uint2 pixel,
                                          uint sampleIdx, float3 normalA = float3(0.f));
#ifdef VISCACHE_DIAGNOSTICS
    [mutating] float traceVisibilityRayCVDiag(const Ray ray, inout SampleGenerator sg, uint2 pixel,
                                               uint sampleIdx, float3 normalA = float3(0.f));
#endif
#endif
};

/** Path tracer.

    This implements the high-level path tracing logic and is shared among
    different scheduling implementations.
*/
struct PathTracer
{
    PathTracerParams params;                        ///< Runtime parameters.

    // Samplers
    EnvMapSampler envMapSampler;                    ///< Environment map sampler. Only valid when kUseEnvLight == true.
    EmissiveLightSampler emissiveSampler;           ///< Emissive light sampler. Only valid when kUseEmissiveLights == true.

    // Inputs
    Texture2D<PackedHitInfo> vbuffer;               ///< Fullscreen V-buffer for the primary hits.
    Texture2D<float3> viewDir;                      ///< Optional view direction. Only valid when kUseViewDir == true.
    Texture2D<uint> sampleCount;                    ///< Optional input sample count buffer. Only valid when kSamplesPerPixel == 0.
    Texture2D<uint> sampleOffset;                   ///< Output offset into per-sample buffers. Only valid when kSamplesPerPixel == 0.

    // Outputs
    RWStructuredBuffer<ColorType> sampleColor;      ///< Output per-sample color if kSamplesPerPixel != 1.
    RWStructuredBuffer<GuideData> sampleGuideData;  ///< Output per-sample guide data.
    NRDBuffers outputNRD;                           ///< Output NRD data.

    RWTexture2D<float4> outputColor;                ///< Output color buffer if kSamplesPerPixel == 1.

    /*******************************************************************
                                Static members
    *******************************************************************/

    // Render settings that depend on the scene.
    // TODO: Move into scene defines.
    static const bool kUseEnvLight = USE_ENV_LIGHT != 0;
    static const bool kUseEmissiveLights = USE_EMISSIVE_LIGHTS != 0;
    static const bool kUseAnalyticLights = USE_ANALYTIC_LIGHTS != 0;
    static const bool kUseCurves = USE_CURVES != 0;
    static const bool kUseHairMaterial = USE_HAIR_MATERIAL != 0;

    // Additional specialization.
    static const bool kOutputGuideData = OUTPUT_GUIDE_DATA != 0;

    // LightType + LightSampleDI lifted to namespace level in
    // `RenderPasses.PathTraceCommon.PathTraceCore` (imported above). Bare references
    // inside this struct (`LightType::EnvMap`, `LightSampleDI`, etc.) now
    // resolve to the imported types via file-scope lookup.

    /** Describes a path vertex.
    */
    struct PathVertex
    {
        uint index;         ///< Vertex index (0 = camera, 1 = primary hit, 2 = secondary hit, etc.).
        float3 pos;         ///< Vertex position.
        float3 faceNormal;  ///< Geometry normal at the vertex (zero if not on a surface).
        bool frontFacing;   ///< True if path vertex is on the front-facing side (if on a surface).

        /** Initializes a path vertex.
            \param[in] index Vertex index.
            \param[in] pos Vertex position.
            \param[in] faceNormal Geometry normal.
            \param[in] frontFacing Front-facing flag.
        */
        __init(uint index, float3 pos, float3 faceNormal = float3(0.f), bool frontFacing = true)
        {
            this.index = index;
            this.pos = pos;
            this.faceNormal = faceNormal;
            this.frontFacing = frontFacing;
        }

        /** Get position with offset applied in direction of the geometry normal to avoid self-intersection
            for visibility rays.
            \param[in] rayDir Direction of the visibility ray (does not need to be normalized).
            \return Returns the offseted position.
        */
        float3 getRayOrigin(float3 rayDir)
        {
            return computeRayOrigin(pos, dot(faceNormal, rayDir) >= 0 ? faceNormal : -faceNormal);
        }

        /** Returns the oriented face normal.
            \return Face normal flipped to the same side as the view vector.
        */
        float3 getOrientedFaceNormal()
        {
            return frontFacing ? faceNormal : -faceNormal;
        }
    };

    /** Set guiding data when background is hit.
    */
    static void setBackgroundGuideData(inout GuideData guideData, const float3 dir, const float3 Le)
    {
        if (kOutputGuideData)
        {
            guideData.setGuideNormal(-dir);
            // Compress dynamic range similar to UE4.
            const float3 compressedColor = pow(Le / (Le + 1.f), 0.454545f);
            guideData.setAlbedo(compressedColor);
            guideData.setSpecularAlbedo(float3(0.f));
            guideData.setIndirectAlbedo(float3(0.f));
            guideData.setReflectionPos(float3(0.f));
        }
    }

    /** Set guiding data when primary surface is hit.
    */
    static void setPrimarySurfaceGuideData(inout GuideData guideData, const ShadingData sd, const BSDFProperties bsdfProperties)
    {
        if (kOutputGuideData)
        {
            guideData.setGuideNormal(bsdfProperties.guideNormal);
            // Use sum of reflection/transmission albedo as they are denoised together.
            guideData.setAlbedo(bsdfProperties.diffuseReflectionAlbedo + bsdfProperties.diffuseTransmissionAlbedo);
            guideData.setReflectionPos(sd.posW);

            const float NdotV = saturate(dot(bsdfProperties.guideNormal, sd.V));
            const float ggxAlpha = bsdfProperties.roughness * bsdfProperties.roughness;

            // We use an approximate shading model with a single specular lobe.
            // TODO: Generalize this to arbitrary materials.
            if (sd.mtl.getMaterialType() == MaterialType::Hair)
            {
                // Use a simple heuristic for hair material.
                const float3 preintegratedSpecular = approxSpecularIntegralGGX(float3(0.04f), ggxAlpha, NdotV);
                guideData.setSpecularAlbedo(preintegratedSpecular);
            }
            else
            {
                // Use pre-integrated FG term for specular
                const float3 preintegratedSpecular = approxSpecularIntegralGGX(bsdfProperties.specularReflectance, ggxAlpha, NdotV);
                guideData.setSpecularAlbedo(preintegratedSpecular);
            }
        }
    }

    /** Set guiding data when indirect surface is hit.
    */
    static void setIndirectSurfaceGuideData(inout GuideData guideData, const ShadingData sd, const BSDFProperties bsdfProperties)
    {
        if (any(bsdfProperties.emission > 0.f))
        {
            float3 indirectBaseColor = pow(bsdfProperties.emission / (bsdfProperties.emission + 1.0f), 0.454545f);
            guideData.setIndirectAlbedo(indirectBaseColor);
        }
        else
        {
            // Use sum of reflection/transmission albedo as they are denoised together.
            guideData.setIndirectAlbedo(bsdfProperties.diffuseReflectionAlbedo + bsdfProperties.diffuseTransmissionAlbedo);
        }
        guideData.setReflectionPos(sd.posW);
    }

    /*******************************************************************
                              Member functions
    *******************************************************************/

    /** Check if the path has finished all surface bounces and needs to be terminated.
        Note: This is expected to be called after generateScatterRay(), which increments the bounce counters.
        \param[in] path Path state.
        \return Returns true if path has processed all bounces.
    */
    bool hasFinishedSurfaceBounces(const PathState path)
    {
        const uint diffuseBounces = path.getBounces(BounceType::Diffuse);
        const uint specularBounces = path.getBounces(BounceType::Specular);
        const uint transmissionBounces = path.getBounces(BounceType::Transmission);
        const uint surfaceBounces = diffuseBounces + specularBounces + transmissionBounces;
        return
            (surfaceBounces > kMaxSurfaceBounces) ||
            (diffuseBounces > kMaxDiffuseBounces) ||
            (specularBounces > kMaxSpecularBounces) ||
            (transmissionBounces > kMaxTransmissionBounces);
    }

    /** Compute the total length of a terminated path.
        \param[in] path Path state.
        \return Returns the total number of bounces a path took.
    */
    uint getTerminatedPathLength(const PathState path)
    {
        // Account for the fact that we may have counted one bounce too many (scatter ray at the last path vertex).
        uint diffuseBounces = min(kMaxDiffuseBounces, path.getBounces(BounceType::Diffuse));
        uint specularBounces = min(kMaxSpecularBounces, path.getBounces(BounceType::Specular));
        uint transmissionBounces = min(kMaxTransmissionBounces, path.getBounces(BounceType::Transmission));
        uint surfaceBounces = min(kMaxSurfaceBounces, diffuseBounces + specularBounces + transmissionBounces);
        return surfaceBounces;
    }

    /** Generate the path state for a primary hit in screen space.
        This is treated equivalent to subsequent path vertices to reduce code divergence.
        \param[in] pathID Path ID which encodes pixel and sample index.
        \param[out] path Path state for the primary hit.
    */
    void generatePath(const uint pathID, out PathState path)
    {
        path = {};
        path.setActive();
        path.id = pathID;
        path.thp = float3(1.f);

        const uint2 pixel = path.getPixel();

        // Create primary ray.
        Ray cameraRay = gScene.camera.computeRayPinhole(pixel, params.frameDim);
        if (kUseViewDir) cameraRay.dir = -viewDir[pixel];
        path.origin = cameraRay.origin;
        path.dir = cameraRay.dir;

        // Create sample generator.
        const uint maxSpp = kSamplesPerPixel > 0 ? kSamplesPerPixel : kMaxSamplesPerPixel;
        path.sg = SampleGenerator(pixel, params.seed * maxSpp + path.getSampleIdx());

        // Load the primary hit info from the V-buffer.
        const HitInfo hit = unpackHitInfo(vbuffer[pixel]);

        // If invalid, the path is still active and treated as a miss.
        if (hit.isValid())
        {
            path.setHit(hit);
            path.setVertexIndex(1);
        }
    }

    /** Set up path for logging and debugging.
        \param[in] path Path state.
    */
    void setupPathLogging(const PathState path)
    {
        printSetPixel(path.getPixel());
        logSetPixel(path.getPixel());
    }

    /** Compute a set of coherence hints for a given path state.
        These hints predict the code path taken in the next call to handleHit() with the given path state.
        They are used by reordering schedulers to extract coherence.
        \param[in] path Path state.
        \param[in] isDeltaSpecular Hit material is pure delta specular.
        \param[in] isEmissive Hit material is emissive.
        \return Returns a bit mask of coherence hints. MSB is highest priority hint. Currently 4 bits are used.
    */
    uint getCoherenceHints(const PathState path, const bool isDeltaSpecular, const bool isEmissive)
    {
        bool terminatedByRussianRoulette = {}; ///< handleHit() will be terminated early due to russian roulette.
        bool terminated = {};                  ///< handleHit() will be terminated early.
        bool samplesLight = {};                ///< handleHit() will sample a light.
        bool computesEmissive = {};            ///< handleHit() will compute emission.

        // Determines if handleHit() will return early due to russian roulette.
        if (kUseRussianRoulette)
        {
            // This is under the assumption that the first random number drawn from the sample generator is used for russian roulette.
            // Keep in sync with handleHit().
            PathState tmpPath = path;
            terminatedByRussianRoulette = terminatePathByRussianRoulette(tmpPath, sampleNext1D(tmpPath.sg));
        }

        // Determines if handleHit() will return early.
        terminated = hasFinishedSurfaceBounces(path);
        if (kDisableCaustics && path.getBounces(BounceType::Diffuse) > 0 && isDeltaSpecular)
            terminated = true;

        // Determines if handleHit() will sample a light.
        samplesLight = true;
        if (isDeltaSpecular)
            samplesLight = false;
        if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume())
            samplesLight = false;

        // Determines if handleHit() will compute emission.
        computesEmissive = isEmissive && path.isLightSamplable();
        if (kUseRTXDI && path.getVertexIndex() == 2 && !isDeltaSpecular)
            computesEmissive = false;

        // MSB = highest priority hint.
        return
            select(computesEmissive, 0x1, 0x0) |
            select(samplesLight, 0x2, 0x0) |
            select(terminated, 0x4, 0x0) |
            select(terminatedByRussianRoulette, 0x8, 0x0);
    }

    /** Update the path throughouput.
        \param[in,out] path Path state.
        \param[in] weight Vertex throughput.
    */
    void updatePathThroughput(inout PathState path, const float3 weight)
    {
        path.thp *= weight;
    }

    /** Add radiance to the path contribution.
        \param[in,out] path Path state.
        \param[in] radiance Vertex radiance.
    */
    void addToPathContribution(inout PathState path, const float3 radiance)
    {
        path.L += path.thp * radiance;
    }

    /** Generates a new scatter ray using BSDF importance sampling.
        \param[in] sd Shading data.
        \param[in] mi Material instance at the shading point.
        \param[in,out] path The path state.
        \return True if a ray was generated, false otherwise.
    */
    bool generateScatterRay(const ShadingData sd, const IMaterialInstance mi, inout PathState path)
    {
        BSDFSample result;
        bool valid = mi.sample(sd, path.sg, result, kUseBSDFSampling);
        if (valid) valid = generateScatterRay(result, sd, mi, path);

        // Ignore valid on purpose for now.
        if (kOutputNRDData)
        {
            const uint lobeTypes = mi.getLobeTypes(sd);
            const bool hasDeltaTransmissionLobe = (lobeTypes & (uint)LobeType::DeltaTransmission) != 0;
            const bool hasNonDeltaLobes = (lobeTypes & (uint)LobeType::NonDelta) != 0;

            if (path.getVertexIndex() == 1)
            {
                path.setDiffusePrimaryHit(result.isLobe(LobeType::Diffuse));
                path.setSpecularPrimaryHit(result.isLobe(LobeType::Specular));

                if (kOutputNRDAdditionalData)
                {
                    // Mark path as delta-only if it followed delta lobe on the primary hit, even though there might have been non-delta lobes.
                    path.setDeltaOnlyPath(result.isLobe(LobeType::DeltaReflection) || result.isLobe(LobeType::DeltaTransmission));

                    path.setDeltaReflectionPrimaryHit(result.isLobe(LobeType::DeltaReflection));
                    path.setDeltaTransmissionPath(result.isLobe(LobeType::DeltaTransmission));
                }
            }

            if (path.getVertexIndex() > 1)
            {
                if (hasNonDeltaLobes) path.setDeltaOnlyPath(false);

                if (kOutputNRDAdditionalData && path.isDeltaTransmissionPath() && path.isDeltaOnlyPath() && hasDeltaTransmissionLobe)
                {
                    if (result.isLobe(LobeType::DeltaReflection) && !isDeltaReflectionAllowedAlongDeltaTransmissionPath(sd))
                    {
                        path.setDeltaTransmissionPath(false);
                    }
                }
            }
        }

        return valid;
    }

    /** Generates a new scatter ray given a valid BSDF sample.
        \param[in] bs BSDF sample (assumed to be valid).
        \param[in] sd Shading data.
        \param[in] mi Material instance at the shading point.
        \param[in,out] path The path state.
        \return True if a ray was generated, false otherwise.
    */
    bool generateScatterRay(const BSDFSample bs, const ShadingData sd, const IMaterialInstance mi, inout PathState path)
    {
        const bool isTriangleHit = path.hit.getType() == HitType::Triangle;
        const bool isCurveHit = kUseCurves && (path.hit.getType() == HitType::Curve);
        const bool isHairMaterial = kUseHairMaterial && (sd.mtl.getMaterialType() == MaterialType::Hair);
        // TODO: Decouple geometry from the material.
        const bool isCurvePolyTubeHit = isTriangleHit && isHairMaterial;

        path.dir = bs.wo;
        updatePathThroughput(path, bs.weight);
        path.pdf = bs.pdf;

        path.clearEventFlags();

        // Handle reflection events.
        if (bs.isLobe(LobeType::Reflection))
        {
            // We classify specular events as diffuse if the roughness is above some threshold.
            float roughness = mi.getProperties(sd).roughness;
            bool isDiffuse = bs.isLobe(LobeType::DiffuseReflection) || roughness > params.specularRoughnessThreshold;

            if (isDiffuse)
            {
                path.incrementBounces(BounceType::Diffuse);
            }
            else
            {
                path.incrementBounces(BounceType::Specular);
                path.setSpecular();
            }
        }

        // Handle delta events.
        if (bs.isLobe(LobeType::Delta))
        {
            path.setDelta();
        }

        // Handle transmission events.
        if (bs.isLobe(LobeType::Transmission))
        {
            path.incrementBounces(BounceType::Transmission);
            path.setTransmission();

            if (isCurveHit)
            {
                // No need to offset the origin in this case.
            }
            else if (isCurvePolyTubeHit)
            {
                // For curves tessellated into poly-tubes, we make sure that the origin is on the same side as a scatter ray direction
                // so there is no self-intersection.
                path.origin = sd.posW - sd.frame.N * sd.curveRadius * 2.1f;
            }
            else
            {
                // Compute ray origin for next ray segment.
                path.origin = sd.computeRayOrigin(false);

                // Update interior list and inside volume flag.
                if (!sd.mtl.isThinSurface())
                {
                    uint nestedPriority = sd.mtl.getNestedPriority();
                    path.interiorList.handleIntersection(sd.materialID, nestedPriority, sd.frontFacing);
                    path.setInsideDielectricVolume(!path.interiorList.isEmpty());
                }
            }
        }

        // Save the normal used for NEE. This is needed for MIS.
        path.normal = sd.getOrientedFaceNormal();

        // Mark the path as valid only if it has a non-zero throughput.
        bool valid = any(path.thp > 0.f);

        return valid;
    }

    /** Evaluates the currently configured heuristic for multiple importance sampling (MIS).
        \param[in] n0 Number of samples taken from the first sampling strategy.
        \param[in] p0 Pdf for the first sampling strategy.
        \param[in] n1 Number of samples taken from the second sampling strategy.
        \param[in] p1 Pdf for the second sampling strategy.
        \return Weight for the contribution from the first strategy (p0).
    */
    float evalMIS(float n0, float p0, float n1, float p1)
    {
        switch (MISHeuristic(kMISHeuristic))
        {
        case MISHeuristic::Balance:
        {
            // Balance heuristic
            float q0 = n0 * p0;
            float q1 = n1 * p1;
            return q0 / (q0 + q1);
        }
        case MISHeuristic::PowerTwo:
        {
            // Power two heuristic
            float q0 = (n0 * p0) * (n0 * p0);
            float q1 = (n1 * p1) * (n1 * p1);
            return q0 / (q0 + q1);
        }
        case MISHeuristic::PowerExp:
        {
            // Power exp heuristic
            float q0 = pow(n0 * p0, kMISPowerExponent);
            float q1 = pow(n1 * p1, kMISPowerExponent);
            return q0 / (q0 + q1);
        }
        default:
            return 0.f;
        }
    }

    /** Generates a light sample on the environment map.
        \param[in] vertex Path vertex.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateEnvMapSample(const PathVertex vertex, inout SampleGenerator sg, out LightSampleDI ls)
    {
        ls = {}; // Default initialization to avoid divergence at returns.

        if (!kUseEnvLight) return false;

        // Sample environment map.
        EnvMapSample lightSample;
        if (!envMapSampler.sample(sampleNext2D(sg), lightSample)) return false;

        // Setup returned sample.
        ls.Li = lightSample.pdf > 0.f ? lightSample.Le / lightSample.pdf : float3(0);
        ls.pdf = lightSample.pdf;
        ls.origin = vertex.getRayOrigin(lightSample.dir);
        ls.distance = kRayTMax;
        ls.dir = lightSample.dir;
        ls.lightIndex = 0u;          // §9.4 — env identity carried by ls.dir
        ls.lightUV = float2(0.f);

        return any(ls.Li > 0.f);
    }

    /** Generates a light sample on the emissive geometry.
        \param[in] vertex Path vertex.
        \param[in] upperHemisphere True if only upper hemisphere should be considered.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateEmissiveSample(const PathVertex vertex, const bool upperHemisphere, inout SampleGenerator sg, out LightSampleDI ls)
    {
        ls = {}; // Default initialization to avoid divergence at returns.
        if (!kUseEmissiveLights) return false;

        TriangleLightSample tls;
        if (!emissiveSampler.sampleLight(vertex.pos, vertex.getOrientedFaceNormal(), upperHemisphere, sg, tls)) return false;

        // Setup returned sample.
        ls.Li = tls.pdf > 0.f ? tls.Le / tls.pdf : float3(0);
        ls.pdf = tls.pdf;
        // Offset shading and light position to avoid self-intersection.
        float3 lightPos = computeRayOrigin(tls.posW, tls.normalW);
        ls.origin = vertex.getRayOrigin(lightPos - vertex.pos);
        float3 toLight = lightPos - ls.origin;
        ls.distance = length(toLight);
        ls.dir = normalize(toLight);
        ls.lightIndex = tls.triangleIndex;   // §9.4 — emissive identity = active triangle index
        ls.lightUV = tls.uv;                 // §9.4 — barycentric coords on the triangle

        return any(ls.Li > 0.f);
    }

#if USE_WS_RESERVOIRS
    /** §9.4 Pack the chosen LightSampleDI's surface payload according to type.
        Emissive: barys (16:16 unorm). EnvMap: dir (oct 16:16). Analytic: 0.
    */
    uint packLightSamplePayload(const LightSampleDI inLs)
    {
        if (inLs.lightType == (uint)LightType::Emissive) return packUV(inLs.lightUV);
        if (inLs.lightType == (uint)LightType::EnvMap)   return packDirOct(inLs.dir);
        return 0u;
    }

    /** §9.4 Re-materialise a LightSampleDI for the env map from a stored
        oct-packed direction, evaluated at the given shading point.
        Distance is kRayTMax (env is at infinity). pdf evaluated via the
        env-map sampler's solid-angle pdf for `dir`.
    */
    bool rebuildEnvMapLightSample(uint payload, const ShadingData sd, out LightSampleDI ls)
    {
        return coreRebuildEnvMapLightSample(payload, sd, envMapSampler, ls);
    }

    /** §9.4 Re-materialise a LightSampleDI for an analytic light from a stored
        lightIndex, re-evaluated at a different shading point. Calls Falcor's
        `sampleLight()` for the analytic light type — the sample is mostly
        deterministic for point/directional lights (no uv); for area-shaped
        analytic lights this consumes fresh randomness, which is fine.

        The cell's "stored sample identity" for analytics is just the light
        choice itself — the cell teaches "this light is good for this region",
        and we re-sample it from the current pixel.
    */
    bool rebuildAnalyticLightSample(uint lightIndex, const ShadingData sd, inout SampleGenerator sg, out LightSampleDI ls)
    {
        return coreRebuildAnalyticLightSample(lightIndex, sd, sg, ls);
    }

    /** §9.4 Re-materialise a LightSampleDI for an emissive triangle from
        stored (lightIndex, uv), re-evaluated at a different shading point.
        Mirrors generateEmissiveSample's per-sample math (see Falcor's
        EmissiveLightSamplerHelpers::sampleTriangle) but uses the stored u
        instead of drawing a new one.
    */
    bool rebuildEmissiveLightSample(uint triangleIndex, float2 u, const ShadingData sd, out LightSampleDI ls)
    {
        return coreRebuildEmissiveLightSample(triangleIndex, u, sd, emissiveSampler, ls);
    }
#endif

    /** Generates a light sample on the analytic lights.
        \param[in] vertex Path vertex.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateAnalyticLightSample(const PathVertex vertex, inout SampleGenerator sg, out LightSampleDI ls)
    {
        ls = {}; // Default initialization to avoid divergence at returns.

        uint lightCount = gScene.getLightCount();
        if (!kUseAnalyticLights || lightCount == 0) return false;

        // Sample analytic light source selected uniformly from the light list.
        // TODO: Sample based on estimated contributions as pdf.
        uint lightIndex = min(uint(sampleNext1D(sg) * lightCount), lightCount - 1);

        // Sample local light source.
        AnalyticLightSample lightSample;
        if (!sampleLight(vertex.pos, gScene.getLight(lightIndex), sg, lightSample)) return false;

        // Setup returned sample.
        ls.pdf = lightSample.pdf / lightCount;
        ls.Li = lightSample.Li * lightCount;
        // Offset shading position to avoid self-intersection.
        ls.origin = vertex.getRayOrigin(lightSample.dir);
        // Analytic lights do not currently have a geometric representation in the scene.
        // Do not worry about adjusting the ray length to avoid self-intersections at the light.
        ls.distance = lightSample.distance;
        ls.dir = lightSample.dir;
        ls.lightIndex = lightIndex;          // §9.4 — analytic light index
        ls.lightUV = float2(0.f);

        return any(ls.Li > 0.f);
    }

    /** Return the probabilities for selecting different light types.
        \param[out] p Probabilities.
    */
    void getLightTypeSelectionProbabilities(out float p[3])
    {
        // Set relative probabilities of the different sampling techniques.
        // TODO: These should use estimated irradiance from each light type. Using equal probabilities for now.
        p[0] = kUseEnvLight ? 1.f : 0.f;
        p[1] = kUseEmissiveLights ? 1.f : 0.f;
        p[2] = kUseAnalyticLights ? 1.f : 0.f;

        // Normalize probabilities. Early out if zero.
        float sum = p[0] + p[1] + p[2];
        if (sum == 0.f) return;

        float invSum = 1.f / sum;
        p[0] *= invSum;
        p[1] *= invSum;
        p[2] *= invSum;
    }

    float getEnvMapSelectionProbability()   { float p[3]; getLightTypeSelectionProbabilities(p); return p[0]; }
    float getEmissiveSelectionProbability() { float p[3]; getLightTypeSelectionProbabilities(p); return p[1]; }
    float getAnalyicSelectionProbability()  { float p[3]; getLightTypeSelectionProbabilities(p); return p[2]; }

    /** Select a light type for sampling.
        \param[out] lightType Selected light type.
        \param[out] pdf Probability for selected type.
        \param[in,out] sg Sample generator.
        \return Return true if selection is valid.
    */
    bool selectLightType(out uint lightType, out float pdf, inout SampleGenerator sg)
    {
        float p[3];
        getLightTypeSelectionProbabilities(p);

        float u = sampleNext1D(sg);

        [unroll]
        for (lightType = 0; lightType < 3; ++lightType)
        {
            if (u < p[lightType])
            {
                pdf = p[lightType];
                return true;
            }
            u -= p[lightType];
        }

        lightType = {};
        pdf = {};

        return false;
    }

    /** Samples a light source in the scene.
        This function first stochastically selects a type of light source to sample,
        and then calls that the sampling function for the chosen light type.
        \param[in] vertex Path vertex.
        \param[in] sampleUpperHemisphere True if the upper hemisphere should be sampled.
        \param[in] sampleLowerHemisphere True if the lower hemisphere should be sampled.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateLightSample(const PathVertex vertex, const bool sampleUpperHemisphere, const bool sampleLowerHemisphere, inout SampleGenerator sg, out LightSampleDI ls)
    {
        ls = {};

        uint lightType;
        float selectionPdf;
        if (!selectLightType(lightType, selectionPdf, sg)) return false;

        bool valid = false;
        if (kUseEnvLight && lightType == (uint)LightType::EnvMap) valid = generateEnvMapSample(vertex, sg, ls);
        if (kUseEmissiveLights && lightType == (uint)LightType::Emissive)
        {
            // Emissive light samplers have an option to exclusively sample the upper hemisphere.
            bool upperHemisphere = sampleUpperHemisphere && !sampleLowerHemisphere;
            valid = generateEmissiveSample(vertex, upperHemisphere, sg, ls);
        }
        if (kUseAnalyticLights && lightType == (uint)LightType::Analytic)
        {
            valid = generateAnalyticLightSample(vertex, sg, ls);
        }
        if (!valid) return false;

        // Reject samples in non-requested hemispheres.
        float NdotL = dot(vertex.getOrientedFaceNormal(), ls.dir);
        if ((!sampleUpperHemisphere && NdotL >= -kMinCosTheta) || (!sampleLowerHemisphere && NdotL <= kMinCosTheta))
            return false;

        // Account for light type selection.
        ls.lightType = lightType;
        ls.pdf *= selectionPdf;
        ls.Li /= selectionPdf;

        return true;
    }

    /** Handle hits on dielectrics.
        \return True if this is an valid intersection, false if it is rejected.
    */
    bool handleNestedDielectrics(inout ShadingData sd, inout PathState path)
    {
        // Check for false intersections.
        uint nestedPriority = sd.mtl.getNestedPriority();
        if (!path.interiorList.isTrueIntersection(nestedPriority))
        {
            // If it is a false intersection, we reject the hit and continue the path
            // on the other side of the interface.
            // If the offset position is not quite large enough, due to self-intersections
            // it is possible we repeatedly hit the same surface and try to reject it.
            // This has happened in a few occasions with large transmissive triangles.
            // As a workaround, count number of rejected hits and terminate the path if too many.
            if (path.rejectedHits < kMaxRejectedHits)
            {
                path.rejectedHits++;
                path.interiorList.handleIntersection(sd.materialID, nestedPriority, sd.frontFacing);
                path.origin = sd.computeRayOrigin(false);
                path.decrementVertexIndex();
            }
            else
            {
                path.terminate();
            }
            return false;
        }

        // Compute index of refraction for medium on the outside.
        sd.IoR = computeOutsideIoR(path.interiorList, sd.materialID, sd.frontFacing);

        return true;
    }

    /** Apply russian roulette to terminate paths early.
        \param[in,out] path Path.
        \param[in] u Uniform random number in [0,1).
        \return Returns true if path was terminated.
    */
    bool terminatePathByRussianRoulette(inout PathState path, float u)
    {
        const float rrVal = luminance(path.thp);
        const float prob = max(0.f, 1.f - rrVal);
        if (u < prob)
        {
            path.terminate();
            return true;
        }
        path.thp /= 1.f - prob;
        return false;
    }

    /** Helper to create a texture sampler instance.
        The method for computing texture level-of-detail depends on the configuration.
        \param[in] path Path state.
        \param[in] isPrimaryTriangleHit True if primary hit on a triangle.
        \return Texture sampler instance.
    */
    ITextureSampler createTextureSampler(const PathState path, bool isPrimaryHit)
    {
        const bool isTriangleHit = (path.hit.getType() == HitType::Triangle);
        if (kPrimaryLodMode == TexLODMode::RayDiffs && isPrimaryHit && isTriangleHit)
        {
            // Filtered lookups at primary hit on triangle.
            float2 ddx, ddy;
            computeDerivativesAtPrimaryTriangleHit(path.hit.getTriangleHit(), path.getPixel(), params.frameDim, ddx, ddy);
            return ExplicitGradientTextureSampler(ddx, ddy);
        }
        else
        {
            float lod = isPrimaryHit ? 0.f : params.lodBias;
            return ExplicitLodTextureSampler(lod);
        }
    }

    /** Pure helper: evaluate the MIS weight for an emissive surface hit.

        Mirrors `evalEnvAtMiss`'s pattern (Step 1 of the ReSTIRPTPass delegation
        plan): pure logic extraction so external callers can reuse the same
        emissive-MIS computation without duplicating it. No path/output side
        effects.

        @param[in] path             PathState at the emissive surface hit.
        @param[in] sd               Shading data at the hit.
        @param[in] isPrimaryHit     Hit is on the primary (camera) ray.
        @param[in] isLightSamplable Hit is on a surface that NEE can sample.
        @param[in] isTriangleHit    Hit is on a triangle (only triangles are emissive-sampled).
        @return    misWeight (1.f when no emissive-NEE-MIS combination applies).
    */
    float evalEmissiveMIS(in const PathState path, in const ShadingData sd, bool isPrimaryHit, bool isLightSamplable, bool isTriangleHit)
    {
        if (!(kUseEmissiveLights && kUseNEE && kUseMIS && isTriangleHit && !isPrimaryHit && path.isLightSampled() && isLightSamplable))
            return 1.f;

        // Prepare hit point struct with data needed for emissive light PDF evaluation.
        TriangleLightHit hit;
        TriangleHit triangleHit = path.hit.getTriangleHit();
        hit.triangleIndex = gScene.lightCollection.getTriangleIndex(triangleHit.instanceID, triangleHit.primitiveIndex);
        hit.posW = sd.posW;
        hit.normalW = sd.getOrientedFaceNormal();

        // Evaluate PDF at the hit, had it been generated with light sampling.
        // Emissive light samplers have an option to exclusively sample the upper hemisphere.
        bool upperHemisphere = path.isLightSampledUpper() && !path.isLightSampledLower();
        float lightPdf = getEmissiveSelectionProbability() * emissiveSampler.evalPdf(path.origin, path.normal, upperHemisphere, hit);

        // Compute MIS weight by combining this with BSDF sampling.
        // Note we can assume path.pdf > 0.f since we shouldn't have got here otherwise.
        return evalMIS(1, path.pdf, 1, lightPdf);
    }

    /** Handle the case when a scatter ray hits a surface.
        After handling the hit, a new scatter ray is generated or the path is terminated.
        \param[in,out] path The path state.
        \param[in,out] vq Visibility query.
    */
    void handleHit<VisibilityQuery : IVisibilityQuery>(inout PathState path, inout VisibilityQuery vq)
    {
        // Upon hit:
        // - Load vertex/material data
        // - Compute MIS weight if path.getVertexIndex() > 1 and emissive hit
        // - Add emitted radiance
        // - Sample light(s) using shadow rays
        // - Sample scatter ray or terminate

        const bool isPrimaryHit = path.getVertexIndex() == 1;
        const HitType hitType = path.hit.getType();
        const bool isTriangleHit = hitType == HitType::Triangle;
        const bool isCurveHit = kUseCurves && (hitType == HitType::Curve);

        // Load shading data. This is a long latency operation.
        ShadingData sd = loadShadingData(path.hit, path.origin, path.dir);

        const bool isHairMaterial = kUseHairMaterial && (sd.mtl.getMaterialType() == MaterialType::Hair);
        // TODO: Decouple geometry from the material.
        const bool isCurvePolyTubeHit = isTriangleHit && isHairMaterial;

        // Account for volume absorption.
        if (!path.interiorList.isEmpty())
        {
            const uint materialID = path.interiorList.getTopMaterialID();
            let material = gScene.materials.getMaterial(materialID);
            let vp = material.getHomogeneousVolumeProperties(gScene.materials, materialID);
            updatePathThroughput(path, HomogeneousVolumeSampler::evalTransmittance(vp, length(sd.posW - path.origin)));
        }

        // Reject false hits in nested dielectrics.
        if (!handleNestedDielectrics(sd, path)) return;

        logPathVertex();

        // Create texture sampler.
        let lod = createTextureSampler(path, isPrimaryHit);

        // Create BSDF instance and query its properties.
        let hints = getMaterialInstanceHints(path.hit, isPrimaryHit);
        const IMaterialInstance mi = gScene.materials.getMaterialInstance(sd, lod, hints);
        BSDFProperties bsdfProperties = mi.getProperties(sd);

        // Disable specular lobes if caustics are disabled and path already contains a diffuse vertex.
        bool isSpecular = bsdfProperties.roughness <= params.specularRoughnessThreshold;
        if (kDisableCaustics && path.getBounces(BounceType::Diffuse) > 0 && isSpecular)
        {
            sd.mtl.setActiveLobes((uint)LobeType::Diffuse);
        }

        // Optionally disable emission inside volumes.
        if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume())
        {
            bsdfProperties.emission = float3(0.f);
        }

        // Check if the scatter event is samplable by the light sampling technique.
        const bool isLightSamplable = path.isLightSamplable();

        // Add emitted radiance.
        // The primary hit is always included, secondary hits only if emissive lights are enabled and the full light contribution hasn't been sampled elsewhere.
        bool computeEmissive = isPrimaryHit || kUseEmissiveLights && (!kUseNEE || kUseMIS || !path.isLightSampled() || !isLightSamplable);

        // With RTXDI enabled, we sample the full direct illumination contribution on the primary hit.
        // Skip any additional contribution on the secondary hit unless it comes from a scatter event
        // that RTXDI cannot handle, such as transmission or delta scattering events.
        if (kUseRTXDI && path.getVertexIndex() == 2 && !path.isTransmission() && !path.isDelta()) computeEmissive = false;

        float3 attenuatedEmission = 0.f;

        if (computeEmissive && any(bsdfProperties.emission > 0.f))
        {
            float misWeight = evalEmissiveMIS(path, sd, isPrimaryHit, isLightSamplable, isTriangleHit);

            // Accumulate emitted radiance weighted by path throughput and MIS weight.
            addToPathContribution(path, misWeight * bsdfProperties.emission);

            attenuatedEmission = path.thp * misWeight * bsdfProperties.emission;
        }

        // Terminate after scatter ray on last vertex has been processed.
        if (hasFinishedSurfaceBounces(path))
        {
            path.terminate();
            return;
        }

        // Compute origin for rays traced from this path vertex.
        if (isCurveHit)
        {
            // For curves, we set the new origin at the sphere center.
            path.origin = sd.posW - sd.frame.N * sd.curveRadius;
        }
        else if (isCurvePolyTubeHit)
        {
            // For curves tessellated into poly-tubes, we offset the new origin away from the curve center.
            path.origin = sd.posW + sd.frame.N * sd.curveRadius * 0.1f;
        }
        else
        {
            path.origin = sd.computeRayOrigin();
        }

        // Determine if BSDF has non-delta lobes.
        const uint lobeTypes = mi.getLobeTypes(sd);
        const bool hasNonDeltaLobes = (lobeTypes & (uint)LobeType::NonDelta) != 0;

        // Check if we should apply NEE.
        const bool applyNEE = kUseNEE && hasNonDeltaLobes;

        // Check if sample from RTXDI should be applied instead of NEE.
        const bool applyRTXDI = kUseRTXDI && isPrimaryHit && hasNonDeltaLobes;

        // TODO: Support multiple shadow rays.
        path.setLightSampled(false, false);
        if (applyNEE || applyRTXDI)
        {
            LightSampleDI ls = {};
            bool validSample = false;

            if (applyRTXDI)
            {
                // Query final sample from RTXDI.
                validSample = gRTXDI.getFinalSample(path.getPixel(), ls.dir, ls.distance, ls.Li);
                ls.origin = path.origin;
            }
            else
            {
                // Setup path vertex.
                PathVertex vertex = PathVertex(path.getVertexIndex(), sd.posW, sd.faceN, sd.frontFacing);

                const bool canNeeSampleSphere = isCurveHit || isCurvePolyTubeHit;
                // Determine if upper/lower hemispheres need to be sampled.
                bool sampleUpperHemisphere = canNeeSampleSphere || ((lobeTypes & (uint)LobeType::NonDeltaReflection) != 0);
                bool sampleLowerHemisphere = canNeeSampleSphere || ((lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0);
                if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) sampleUpperHemisphere = false;

                // Sample a light.
                validSample = generateLightSample(vertex, sampleUpperHemisphere, sampleLowerHemisphere, path.sg, ls);
                path.setLightSampled(sampleUpperHemisphere, sampleLowerHemisphere);
            }

            if (validSample)
            {
                // Apply MIS weight.
                if (kUseMIS && !applyRTXDI && ls.lightType != (uint)LightType::Analytic)
                {
                    float scatterPdf = mi.evalPdf(sd, ls.dir, kUseBSDFSampling);
                    ls.Li *= evalMIS(1, ls.pdf, 1, scatterPdf);
                }

                float3 weight = mi.eval(sd, ls.dir, path.sg);
                float3 Lr = weight * ls.Li;

#if USE_WS_RESERVOIRS
                // §9.4 WS-ReSTIR DI: full read+merge+write at the primary hit.
                //  1. seed local reservoir with the fresh NEE candidate
                //  2. gather home cell + spatial neighbours, re-evaluate each
                //     candidate at THIS shading point, merge into the local
                //  3. swap the picked sample into ls (and recompute Lr)
                //  4. persist the local back to the home cell
                // Handles emissive, analytic AND env-map lights — full coverage
                // of Falcor's three light-type families.
                bool isEmissive = ls.lightType == (uint)LightType::Emissive;
                bool isAnalytic = ls.lightType == (uint)LightType::Analytic;
                bool isEnv      = ls.lightType == (uint)LightType::EnvMap;
                if (path.getVertexIndex() == 1 && enabled() && (isEmissive || isAnalytic || isEnv))
                {
                    LocalReservoir local; local.init();

                    // §9.4 Pool address — resolved once, used for both write-back
                    // and per-candidate insert-on-fill (so the pool fills within
                    // a single dispatch instead of waiting for next frame).
                    // §9.4 mode-dispatched pool address: 3D world cell OR
                    // 2D screen tile (RTXDI-style). Same buffer/struct/insert
                    // math; only the address resolver differs.
                    CellAddress poolAddrA = resolvePoolAddr(sd.posW, sd.faceN, path.getPixel());

                    // §9.4 — RTXDI port: pool fills via BOTH pre-pass AND
                    // main pass (matches RTXDI conceptually — every frame's
                    // light proposals contribute to the tile/cell). Main pass
                    // also seeds the local reservoir with the fresh NEE
                    // sample as the first RIS candidate, then folds K_pool
                    // additional candidates from the pool (block 1c). This
                    // gives x1 vanilla-NEE-baseline behavior even when the
                    // pool is cold (frame 1 / new viewpoint). Across frames,
                    // pool fills and K=24 pool draws dominate, recovering
                    // RTXDI-tile-presample quality.

                    // (1) Add the fresh sample as the first RIS candidate.
                    if (any(Lr > 0.f))
                    {
                        // pHat = luminance(Lr) directly. Falcor's ls.Li = Le/pdf,
                        // so weight*Li = (BSDF*cos*Le)/pdf = unbiased single-sample
                        // direct-lighting estimator. RIS over already-MC-divided
                        // contributions uses w_i = lum(contribution); the /pdf is
                        // already in Lr. invPdf passed as 1.0 below.
                        // CRITICAL: this works for BOTH area lights (pdf>0) AND
                        // point/directional lights (pdf=0, Dirac). Earlier
                        // formulations using `pHat × 1/ls.pdf` divided by zero
                        // for Dirac lights, making point-light candidates have
                        // RIS weight 0 → reservoir empty → K-RIS fell through to
                        // vanilla NEE bit-identically.
                        float pHatFresh = luminance(Lr);
                        // §9.4 Visibility-aware target function (RTXDI fix).
                        // Runtime-selected by gVisInPHat:
                        //   0 = blind (no V — biased on emissive-heavy scenes)
                        //   1 = cache-amortized via traceVisibilityRayCV (cheap once warm)
                        //   2 = explicit always-trace via traceVisibilityRay (K rays/pixel,
                        //       no cache — unbiased reference, isolates RIS math from cache)
                        if (!isEnv && visInPHatMode() != 0u)
                        {
                            Ray vrayF = ls.getVisibilityRay();
                            float vF = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                            if (visInPHatMode() == 1u)
                                vF = vq.traceVisibilityRayCV(vrayF, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                            else
                                vF = vq.traceVisibilityRay(vrayF) ? 1.f : 0.f;
#else
                            vF = vq.traceVisibilityRay(vrayF) ? 1.f : 0.f;
#endif
                            pHatFresh *= max(vF, lightMuMin());
                        }
                        // invPdf = 1 because pHatFresh = lum(Lr) already includes
                        // the 1/pdf factor (Lr = weight × Li = integrand / pdf).
                        // Standard RIS over MC-divided contributions. Fresh
                        // sample seeds the local reservoir AND fills the pool
                        // for next-frame reads. Empirically the fresh sample is
                        // the highest-quality candidate (proper pHat at reader,
                        // not cross-pixel-biased) — dropping it for "pure RTXDI
                        // pool-only K-RIS" regressed Sponza x1 by +9pp.
                        uint freshLTI = packLightTypeIndex(ls.lightType, ls.lightIndex);
                        uint freshPL  = packLightSamplePayload(ls);
                        local.streamingAdd(freshLTI, freshPL,
                            pHatFresh, 1.f, path.sg);
                        if (cellPoolEnabled())
                        {
                            // §9.4 step (d) FIXED: V-aware RIS-at-insert via target
                            // multiplier (NOT probabilistic acceptance). The previous
                            // formulation `if (rand < V) insert with sourcePdf*V`
                            // mathematically AMPLIFIED occluded candidates' weight
                            // (rare 1% inserts → 100× weight → reservoir biased
                            // toward occluded — opposite of intent). Correct form:
                            // always insert; modulate the RIS *target* by V, leave
                            // sourcePdf unchanged. Then pool slot replacement
                            // probability is ∝ pHat × V / ls.pdf — slots concentrate
                            // on visible-bright candidates without bias inflation.
                            // Reader's 1/sourcePdf RIS weight uses unmodified
                            // ls.pdf — clean unbiased proposal density.
                            //
                            // V-aware fill is decoupled from visInPHat (the K-RIS
                            // p̂ V-mode) so the cell pool always gets V-filtered
                            // candidates when enabled — RTXDI's tile-pool analog.
                            float muF = 1.f;
                            if (!isEnv && ls.distance > 0.f)
                            {
                                float3 lightPosB = ls.origin + ls.dir * ls.distance;
                                VHFResult vr = vhfLookup(sd.posW, lightPosB, sd.faceN);
                                muF = vr.valid ? vr.mu : 1.f;
                            }
                            float vWeight = max(muF, lightMuMin());  // defensive μmin floor
#if WS_CELL_POOL_FILL_ONLY
                            // Pool inserts only from pre-pass (RTXDI-style: dedicated
                            // fill source). Main pass uses LightBVH for fresh K-RIS in
                            // the local stream but does NOT write to pool, so pool
                            // content reflects only the pre-pass's sampler choice
                            // (e.g. shading-agnostic Power for cross-pixel diversity).
                            cellPoolInsert(poolAddrA, freshLTI, freshPL, ls.pdf, pHatFresh * vWeight, path.sg);
#endif
                        }
                    }

                    // (1b) Generate K-1 ADDITIONAL fresh candidates per pixel
                    //      (RTXDI parity: localLightCandidateCount default 8).
                    //      This is the dominant variance reducer on many-lights
                    //      scenes — single-candidate fall-through gives no gain
                    //      over vanilla NEE.
                    {
                        PathVertex vtxK = PathVertex(path.getVertexIndex(), sd.posW, sd.faceN, sd.frontFacing);
                        const bool canNeeSampleSphereK = isCurveHit || isCurvePolyTubeHit;
                        bool sampleUpperK = canNeeSampleSphereK || ((lobeTypes & (uint)LobeType::NonDeltaReflection) != 0);
                        bool sampleLowerK = canNeeSampleSphereK || ((lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0);
                        if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) sampleUpperK = false;

                        uint extraK = (gInitialCandidates > 1u) ? (gInitialCandidates - 1u) : 0u;
                        for (uint k = 0u; k < extraK; ++k)
                        {
                            LightSampleDI lsK = {};
                            if (!generateLightSample(vtxK, sampleUpperK, sampleLowerK, path.sg, lsK)) continue;
                            float3 weightK = mi.eval(sd, lsK.dir, path.sg);
                            float3 LrK = weightK * lsK.Li;
                            if (!any(LrK > 0.f)) continue;
                            // pHat = luminance(Lr); invPdf=1. Works for both
                            // area lights (pdf>0) and Dirac point/directional
                            // lights (pdf=0). See fresh-candidate site.
                            float pHatK = luminance(LrK);
                            if (lsK.lightType != (uint)LightType::EnvMap && visInPHatMode() != 0u)
                            {
                                Ray vrayK = lsK.getVisibilityRay();
                                float vK = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                                if (visInPHatMode() == 1u)
                                    vK = vq.traceVisibilityRayCV(vrayK, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                                else
                                    vK = vq.traceVisibilityRay(vrayK) ? 1.f : 0.f;
#else
                                vK = vq.traceVisibilityRay(vrayK) ? 1.f : 0.f;
#endif
                                pHatK *= max(vK, lightMuMin());
                            }
                            uint kLTI = packLightTypeIndex(lsK.lightType, lsK.lightIndex);
                            uint kPL  = packLightSamplePayload(lsK);
                            // invPdf=1; pHatK already pdf-divided (lum(Lr)).
                            local.streamingAdd(kLTI, kPL, pHatK, 1.f, path.sg);
                            if (cellPoolEnabled())
                            {
                                // §9.4 step (d) FIXED — V-aware target-multiplier
                                // form. See full rationale at the fresh-insert
                                // site above. always-insert with pHat × V as RIS
                                // target, sourcePdf left = ls.pdf (unbiased).
                                // V-aware fill is decoupled from visInPHat —
                                // the cell pool always gets V-filtered candidates.
                                float muK = 1.f;
                                if (lsK.lightType != (uint)LightType::EnvMap
                                    && lsK.distance > 0.f)
                                {
                                    float3 lightPosBK = lsK.origin + lsK.dir * lsK.distance;
                                    VHFResult vrK = vhfLookup(sd.posW, lightPosBK, sd.faceN);
                                    muK = vrK.valid ? vrK.mu : 1.f;
                                }
                                float vWeightK = max(muK, lightMuMin());
#if WS_CELL_POOL_FILL_ONLY
                                cellPoolInsert(poolAddrA, kLTI, kPL, lsK.pdf, pHatK * vWeightK, path.sg);
#endif
                            }
                        }
                    }

                    // (1c) §9.4 WS-cascade ReGIR — draw K candidates from the
                    //     home cell's multi-light pool. Pool fills from main-
                    //     pass winners (step a write-back below) and over time
                    //     concentrates on the popular high-pHat lights for this
                    //     region. Acts as a per-region importance prior on top
                    //     of LightBVH's global power weighting.
                    //     Each pool entry was inserted with its writer-side NEE
                    //     proposal pdf, so we treat the entry as a sample drawn
                    //     from that pdf at this reading pixel — RIS unbiases via
                    //     pHat(reader) / sourcePdf, exactly as if the entry had
                    //     been freshly drawn at the reader.
                    if (gCellPoolDrawK > 0u && cellPoolEnabled())
                    {
                        // AoS reader — fetch one whole CellPoolSlot per
                        // K-RIS iteration. The 12-B slot is a single
                        // bufferLoad at one offset, so the three fields
                        // (lightTypeIndex, payload, sourcePdf) come from
                        // the same writer's contribution — no torn reads
                        // under concurrent writes. Avoids the 12 KB whole-
                        // struct copy that DXIL rejects at N=1024.
                        uint poolSlot, poolCount;
                        if (lookupCellPool(poolAddrA, poolSlot, poolCount))
                        {
                            uint kPool = min(gCellPoolDrawK, poolCount);
                            for (uint d = 0u; d < kPool; ++d)
                            {
                                uint slotR = uint(sampleNext1D(path.sg) * float(poolCount)) % poolCount;
                                CellPoolSlot ps = gCellPoolSlotBuf[slotIndex(poolSlot, slotR)];
                                // Per-slot freshness filter — `frameStamp ==
                                // currentFrame` means the slot was written this
                                // frame and is valid; otherwise it's stale (from
                                // a previous frame or previous cell occupant).
                                // sourcePdf guard remains as defense-in-depth.
                                // Per-slot freshness filter — `slotFrame == currentFrame & 0xFFFF`
                                // means slot was written this frame. Modular handling of 16-bit wrap.
                                if (slotGetFrame(ps) != slotCurrentFrame()) continue;
                                if (ps.sourcePdf <= 0.f) continue;
                                uint pLTI  = ps.lightTypeIndex;
                                uint pType = unpackLightType(pLTI);
                                uint pIdxL = unpackLightIndex(pLTI);
                                float pSrcPdf = ps.sourcePdf;
                                uint pPayload = ps.payload;
                                // P3d (mode=0): M=0 → pSlotM=1 → no extra weight (identity).
                                // PR3d (mode=1): scale K-RIS weight by M (slot's reservoir-sample count).
                                float pSlotM = (gCellPoolMode != 0u) ? float(max(slotGetM(ps), 1u)) : 1.0f;
                                LightSampleDI poolLs;
                                bool poolOk = false;
                                if (pType == (uint)LightType::Emissive)
                                    poolOk = rebuildEmissiveLightSample(pIdxL, unpackUV(pPayload), sd, poolLs);
                                else if (pType == (uint)LightType::Analytic)
                                    poolOk = rebuildAnalyticLightSample(pIdxL, sd, path.sg, poolLs);
                                else if (pType == (uint)LightType::EnvMap)
                                    poolOk = rebuildEnvMapLightSample(pPayload, sd, poolLs);
                                if (!poolOk) continue;

                                float NdotLP = dot(sd.faceN, poolLs.dir);
                                bool hasReflP  = (lobeTypes & (uint)LobeType::NonDeltaReflection) != 0;
                                bool hasTransP = (lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0;
                                bool acceptUP = (NdotLP >  kMinCosTheta) && hasReflP;
                                bool acceptLP = (NdotLP < -kMinCosTheta) && hasTransP;
                                if (!acceptUP && !acceptLP) continue;

                                // §9.4 MIS for pool draws — match the fresh-sample path
                                // in block 1a (line ~1179): light-vs-BSDF MIS damps
                                // the candidate's Li by the balance heuristic. Without
                                // this, pool candidates have higher weight than fresh
                                // candidates by the MIS factor, biasing the RIS toward
                                // pool and over-weighting reused samples. Skipped for
                                // Analytic lights (Falcor convention).
                                if (kUseMIS && !applyRTXDI && pType != (uint)LightType::Analytic)
                                {
                                    float scatterPdfP = mi.evalPdf(sd, poolLs.dir, kUseBSDFSampling);
                                    poolLs.Li *= evalMIS(1, poolLs.pdf, 1, scatterPdfP);
                                }

                                float3 weightP = mi.eval(sd, poolLs.dir, path.sg);
                                float3 LrP = weightP * poolLs.Li;
                                if (!any(LrP > 0.f)) continue;
                                // pHat = luminance(Lr) at reading pixel.
                                float pHatP = luminance(LrP);
                                // §9.4 step (d) — V-aware target function for pool draws.
                                // Reuses the existing visInPHat machinery: mode 1 = cache-
                                // amortized (μ from VisCache), mode 2 = explicit shadow ray.
                                // Applied to pool draws on top of the existing fresh-candidate
                                // path so the per-pixel K-RIS picks visibility-aware candidates
                                // regardless of whether they came from the pool or fresh draws.
                                if (pType != (uint)LightType::EnvMap && visInPHatMode() != 0u)
                                {
                                    Ray vrayP = poolLs.getVisibilityRay();
                                    float vP = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                                    if (visInPHatMode() == 1u)
                                        vP = vq.traceVisibilityRayCV(vrayP, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                                    else
                                        vP = vq.traceVisibilityRay(vrayP) ? 1.f : 0.f;
#else
                                    vP = vq.traceVisibilityRay(vrayP) ? 1.f : 0.f;
#endif
                                    pHatP *= max(vP, lightMuMin());
                                }
                                // §9.4 read-side — Convention B (UNBIASED, RTXDI-faithful)
                                // with reader-evaluated pdf. Validated 2026-05-05:
                                // closes Cornell_3AL_x4 trail by -0.18pp, wins on
                                // BistroExt_x4 by -0.96pp, no firefly regression on
                                // Sponza/BistroExt (Sponza_x4 +0.04 within noise).
                                // Earlier Conv B w/ stored solid-angle pdf fireflies
                                // because writer's r²/cos was baked in. Computing
                                // pdf at READER via emissiveSampler.evalPdf uses
                                // reader's geometry → position-invariant RIS weight.
                                // Emissive only; analytic/env fall back to Conv A
                                // (Dirac/env pdf eval may not exist).
                                float invSrcPdf = 1.f;
                                if (pType == (uint)LightType::Emissive)
                                {
                                    // Compute triangle normal from vertices —
                                    // inner LightSampleDI lacks normalW.
                                    const EmissiveTriangle pet = gScene.lightCollection.getTriangle(pIdxL);
                                    float3 pe0 = pet.posW[1] - pet.posW[0];
                                    float3 pe1 = pet.posW[2] - pet.posW[0];
                                    TriangleLightHit poolHit;
                                    poolHit.triangleIndex = pIdxL;
                                    poolHit.posW = poolLs.origin + poolLs.dir * poolLs.distance;
                                    poolHit.normalW = normalize(cross(pe0, pe1));
                                    float readerPdf = emissiveSampler.evalPdf(sd.posW, sd.faceN, true, poolHit);
                                    invSrcPdf = (readerPdf > 0.f) ? (1.f / readerPdf) : 0.f;
                                }
                                // PR3d: weight by M_slot. P3d: pSlotM=1 (no-op).
                                local.streamingAdd(
                                    pLTI, pPayload,
                                    pHatP * pSlotM, invSrcPdf, path.sg);
                            }
                        }
                    }

#if !WS_CELL_POOL_FILL_ONLY
                    // §9.4 RTXDI port: testCandidateVisibility (RTXDI default = true).
                    // [Differences from literal RTXDI port — see paper §9.4 + DEVLOG
                    //  for the complete table. Algorithmic deviations: 1) pool fill
                    //  via main+Bayer-pre-pass NEE writes (not RTXDI's compute pre-
                    //  pass with pdf-mipmap) — Falcor uses LightBVH; 2) Convention A
                    //  read (`w = pHat × 1`, not RTXDI's `targetPdf × invSourcePdf`)
                    //  — LightBVH's shading-conditional pdf would cause ratio
                    //  fireflies under Conv B; 3) K=8 fresh + K=16 pool = 24 total
                    //  (RTXDI uses K=24 from tile only; we keep fresh in local
                    //  because pool-only regressed Sponza x1 +9pp); 4) MIS re-
                    //  applied at reuse sites because we re-evaluate Li at reader.]
                    // After the K-RIS picks its winner from the pool, trace
                    // ONE shadow ray to verify visibility. If V=0, ZERO the
                    // winner's targetPdf (so the reservoir's W = wSum/(pHat×M)
                    // makes the swap skip this frame: `if (targetPdf > 0)`
                    // gate fails). Spatial/temporal merge still get the
                    // accumulated wSum/M mass; subsequent neighbor merges
                    // can replace the shadowed winner with a visible one.
                    // Less aggressive than `local.init()` (keeps reservoir
                    // mass intact). Matches RTXDI's reject-this-sample
                    // semantics without losing K-RIS state.
                    // Cost: 1 shadow ray per pixel per frame, main pass only.
                    if (local.M > 0.f && local.targetPdf > 0.f)
                    {
                        uint winnerType = unpackLightType(local.lightTypeIndex);
                        uint winnerIdx  = unpackLightIndex(local.lightTypeIndex);
                        LightSampleDI winnerLs;
                        bool winnerOk = false;
                        if (winnerType == (uint)LightType::Emissive)
                            winnerOk = rebuildEmissiveLightSample(winnerIdx, unpackUV(local.payload), sd, winnerLs);
                        else if (winnerType == (uint)LightType::Analytic)
                            winnerOk = rebuildAnalyticLightSample(winnerIdx, sd, path.sg, winnerLs);
                        else if (winnerType == (uint)LightType::EnvMap)
                            winnerOk = rebuildEnvMapLightSample(local.payload, sd, winnerLs);
                        if (winnerOk)
                        {
                            Ray vrayWin = winnerLs.getVisibilityRay();
                            bool winnerVisible = vq.traceVisibilityRay(vrayWin);
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
                            vcDiagCountRay(path.getPixel(), true);   // K-RIS winner V-test
#endif
                            if (!winnerVisible)
                            {
                                // Shadowed → zero the winner's pHat. wSum/M
                                // stay intact for spatial reuse to potentially
                                // replace the winner with a visible candidate.
                                local.targetPdf = 0.f;
                            }
                        }
                    }

                    // (2) Gather home cell + jittered neighbours. Home is the
                    // unjittered query; neighbours are tangent-plane-jittered
                    // queries through the same resolveCell function. We
                    // filter out queries that landed back in the home cell
                    // by fingerprint compare.
                    //
                    // gUseCellInRIS gates this whole block off — when 0,
                    // shading falls back to pure per-pixel ReSTIR DI (per-pixel
                    // temporal + spatial reuse via gPixelReservoirs only).
                    CellAddress homeAddr = resolveCell(sd.posW, sd.faceN);
                    const uint nNeighbours = (gUseCellInRIS != 0u) ? spatialNeighbourCount() : 0u;
                    // Cell-merge pairwise canonical-correction. Same pattern as
                    // temporal/spatial-pixel pairwise: snapshot canonical (K-RIS
                    // result) before the cell loop, re-init local, stream cells
                    // with pairwise m_j + m-weighted M, re-stream canonical at
                    // end with accumulated MIS. Cell merges cross surfaces by
                    // construction (cells aggregate ALL pixels keyed to the
                    // same world-space cell), so this is load-bearing — without
                    // it the basic Bitterli merge gives Cornell rmse 2001 vs
                    // vanilla 0.5 (catastrophic firefly).
                    float cCanonM_save = 0.f;
                    float cCanonWSum_save = 0.f;
                    float cCanonTargetPdf_save = 0.f;
                    uint  cCanonLightTypeIndex_save = 0u;
                    uint  cCanonPayload_save = 0u;
                    float cCanonMISAcc = 0.f;
                    float cLocalMWeighted = 0.f;
                    bool  cAnyStreamed = false;
#if BIAS_CORRECTION == 1
                    if (gUseCellInRIS != 0u)
                    {
                        cCanonM_save = local.M;
                        cCanonWSum_save = local.wSum;
                        cCanonTargetPdf_save = local.targetPdf;
                        cCanonLightTypeIndex_save = local.lightTypeIndex;
                        cCanonPayload_save = local.payload;
                        local.init();
                    }
#endif
                    for (uint i = 0u; (gUseCellInRIS != 0u) && i <= nNeighbours; ++i)
                    {
                        CellAddress addr;
                        if (i == 0u)
                        {
                            addr = homeAddr;
                        }
                        else
                        {
                            float2 j2d = sampleNext2D(path.sg);
                            addr = resolveJitteredCell(sd.posW, sd.faceN, i - 1u, nNeighbours, j2d);
                            // Skip if jitter landed back in the home cell —
                            // already covered by i==0.
                            if (addr.fingerprint == homeAddr.fingerprint) continue;
                        }
                        Reservoir cell;
                        if (!loadCell(addr, cell)) continue;
                        if (cell.M <= 0.f) continue;
                        // cell.W is no longer consumed for shading (selection-only
                        // design after the v5 fix); identity is what matters.

                        uint cellType = unpackLightType(cell.lightTypeIndex);
                        uint cellIdx  = unpackLightIndex(cell.lightTypeIndex);
                        LightSampleDI cellLs;
                        bool cellOk = false;
                        if (cellType == (uint)LightType::Emissive)
                            cellOk = rebuildEmissiveLightSample(cellIdx, unpackUV(cell.payload), sd, cellLs);
                        else if (cellType == (uint)LightType::Analytic)
                            cellOk = rebuildAnalyticLightSample(cellIdx, sd, path.sg, cellLs);
                        else if (cellType == (uint)LightType::EnvMap)
                            cellOk = rebuildEnvMapLightSample(cell.payload, sd, cellLs);
                        if (!cellOk) continue;

                        // Hemisphere check matching legacy NEE: accept reflection
                        // samples only when BSDF has reflection lobes; transmission
                        // samples only when it has transmission lobes.
                        float NdotL = dot(sd.faceN, cellLs.dir);
                        bool hasRefl  = (lobeTypes & (uint)LobeType::NonDeltaReflection) != 0;
                        bool hasTrans = (lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0;
                        bool acceptUpper = (NdotL >  kMinCosTheta) && hasRefl;
                        bool acceptLower = (NdotL < -kMinCosTheta) && hasTrans;
                        if (!acceptUpper && !acceptLower) continue;

                        float3 cellWeight = mi.eval(sd, cellLs.dir, path.sg);
                        float3 cellLr     = cellWeight * cellLs.Li;
                        // pHat = luminance(Lr); invPdf=1. Cell candidate is
                        // a re-drawn light sample at the reader, with cellLs.Li
                        // already pdf-divided. Works for Dirac lights.
                        float pHatCell    = luminance(cellLr);
                        if (pHatCell <= 0.f) continue;
                        if (cellType != (uint)LightType::EnvMap && visInPHatMode() != 0u)
                        {
                            Ray vrayC = cellLs.getVisibilityRay();
                            float vC = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                            if (visInPHatMode() == 1u)
                                vC = vq.traceVisibilityRayCV(vrayC, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                            else
                                vC = vq.traceVisibilityRay(vrayC) ? 1.f : 0.f;
#else
                            vC = vq.traceVisibilityRay(vrayC) ? 1.f : 0.f;
#endif
                            pHatCell *= max(vC, lightMuMin());
                        }

                        // Cell read mode (gCellReservoirMerge):
                        //   0 (default) — IDENTITY hint: add cell.{lightTypeIndex,payload}
                        //     as ONE single RIS candidate at the local pixel's pHat. Per-pixel
                        //     W stays local; avoids spatial-block artifacts from inherited W.
                        //   1 — full Bitterli weighted MERGE: read cell.W and cell.M and
                        //     fold the cell as an aggregated reservoir. World-space analog
                        //     of the per-pixel temporal/spatial reservoir; no reprojection
                        //     needed (cell ID is camera-invariant). Used by `restir_3d`.
                        if (gCellReservoirMerge == 1u && cell.M > 0.f && cell.W > 0.f)
                        {
                            float Mcap = min(cell.M, gMCap);
                            float m_c = 1.f;
#if BIAS_CORRECTION == 1
                            {
                                // RTXDI pairwise m_j: uses (pHat_reader for
                                // nbr) and (nbr's stored targetPdf at its own
                                // surface). m_j downweights when nbr's sample
                                // doesn't fit the reader's surface.
                                float cPairwiseDenom = pHatCell * cCanonM_save + cell.targetPdf * Mcap;
                                if (cPairwiseDenom > 0.f)
                                {
                                    m_c = (cell.targetPdf * Mcap) / cPairwiseDenom;
                                }
                                // m_canonical: RTXDI uses canon's sample's
                                // pHat at canon's surface (= cCanonTargetPdf)
                                // for BOTH numerator and the canon-side
                                // denominator term — neighbour-surface eval
                                // not available, so same-surface approx
                                // degenerates this to a pure M-ratio. (Was
                                // pHatCell * cCanonM_save before — biased
                                // when reader's pHat for nbr's sample differs
                                // wildly from canon.targetPdf.)
                                if (cCanonM_save + Mcap > 0.f)
                                {
                                    cCanonMISAcc += cCanonM_save / (cCanonM_save + Mcap);
                                }
                            }
#endif
                            float w = m_c * pHatCell * cell.W * Mcap;
                            if (w > 0.f && !isnan(w))
                            {
                                local.wSum += w;
                                local.M    += Mcap;
                                cLocalMWeighted += m_c * Mcap;
                                cAnyStreamed = true;
                                if (sampleNext1D(path.sg) * local.wSum <= w)
                                {
                                    local.lightTypeIndex = cell.lightTypeIndex;
                                    local.payload        = cell.payload;
                                    local.targetPdf      = pHatCell;
                                }
                            }
                        }
                        else
                        {
                            // Identity-hint legacy path.
                            local.streamingAdd(
                                cell.lightTypeIndex, cell.payload,
                                pHatCell, 1.f, path.sg);
                        }
                    }
                    // Re-stream canonical with accumulated cell-merge MIS weight.
#if BIAS_CORRECTION == 1
                    if (gUseCellInRIS != 0u && cCanonM_save > 0.f && cCanonTargetPdf_save > 0.f)
                    {
                        if (cAnyStreamed)
                        {
                            float cWnCanon = cCanonMISAcc * cCanonWSum_save;
                            if (cWnCanon > 0.f && !isnan(cWnCanon))
                            {
                                local.wSum += cWnCanon;
                                local.M    += cCanonM_save;
                                cLocalMWeighted += cCanonMISAcc * cCanonM_save;
                                if (sampleNext1D(path.sg) * local.wSum <= cWnCanon)
                                {
                                    local.lightTypeIndex = cCanonLightTypeIndex_save;
                                    local.payload        = cCanonPayload_save;
                                    local.targetPdf      = cCanonTargetPdf_save;
                                }
                            }
                        }
                        else
                        {
                            local.wSum           = cCanonWSum_save;
                            local.M              = cCanonM_save;
                            cLocalMWeighted      = cCanonM_save;
                            local.targetPdf      = cCanonTargetPdf_save;
                            local.lightTypeIndex = cCanonLightTypeIndex_save;
                            local.payload        = cCanonPayload_save;
                        }
                        local.M = cLocalMWeighted;
                    }
#endif

                    // (2.5) Per-pixel temporal+spatial reservoir layer.
                    // Active only when enablePixelReservoir=True (default);
                    // disabled by setting pixelReservoirEnabled() to false
                    // for pure-WS-cell-only ablation. Provides the screen-
                    // space spatial diversity that cell jittered queries
                    // cannot replicate (close cells share popular winners,
                    // close pixels' reservoirs picked diverse winners).
                    if (pixelReservoirEnabled())
                    {
                        // ----- temporal: read self ----------------------------------
                        // Normal-aware rejection: if last frame's reservoir came
                        // from a different surface (silhouette / camera moved
                        // across an edge), skip. Cos threshold 0.9 ≈ 26°.
                        const float kWSNormalCos = 0.5f;   // RTXDI's normalThreshold default — looser angular reject (60° vs 26°), more spatial reuse

                        // Temporal merge: snapshot canonical (K-RIS + any prior
                        // cell-merge result), re-init local, stream prev with
                        // pairwise m_j + m-weighted M, re-stream canonical.
                        // Same RTXDI-Pairwise pattern the spatial merge below
                        // uses. Cascades cleanly: temporal pairwise output
                        // becomes spatial pairwise's canonical.
                        float tCanonM_save = 0.f;
                        float tCanonWSum_save = 0.f;
                        float tCanonTargetPdf_save = 0.f;
                        uint  tCanonLightTypeIndex_save = 0u;
                        uint  tCanonPayload_save = 0u;
                        float tCanonMISAcc = 0.f;
                        float tLocalMWeighted = 0.f;
                        bool  tPrevStreamed = false;
#if BIAS_CORRECTION == 1
                        tCanonM_save = local.M;
                        tCanonWSum_save = local.wSum;
                        tCanonTargetPdf_save = local.targetPdf;
                        tCanonLightTypeIndex_save = local.lightTypeIndex;
                        tCanonPayload_save = local.payload;
                        local.init();
#endif
                        uint pIdx = pixelIndex(path.getPixel());
                        Reservoir prev = gPixelReservoirs[pIdx];
                        bool prevNormalOk = true;
                        if (prev.normalOct != 0u)
                        {
                            float3 prevN = unpackDirOct(prev.normalOct);
                            prevNormalOk = (dot(sd.faceN, prevN) >= kWSNormalCos);
                        }
                        if (prevNormalOk && prev.M > 0.f && prev.fingerprint != 0u)
                        {
                            uint prevType = unpackLightType(prev.lightTypeIndex);
                            uint prevIdx  = unpackLightIndex(prev.lightTypeIndex);
                            LightSampleDI prevLs;
                            bool prevOk = false;
                            if (prevType == (uint)LightType::Emissive)
                                prevOk = rebuildEmissiveLightSample(prevIdx, unpackUV(prev.payload), sd, prevLs);
                            else if (prevType == (uint)LightType::Analytic)
                                prevOk = rebuildAnalyticLightSample(prevIdx, sd, path.sg, prevLs);
                            else if (prevType == (uint)LightType::EnvMap)
                                prevOk = rebuildEnvMapLightSample(prev.payload, sd, prevLs);
                            if (prevOk)
                            {
                                float NdotL_prev = dot(sd.faceN, prevLs.dir);
                                bool hasReflP  = (lobeTypes & (uint)LobeType::NonDeltaReflection) != 0;
                                bool hasTransP = (lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0;
                                bool acceptP = ((NdotL_prev > kMinCosTheta) && hasReflP)
                                            || ((NdotL_prev < -kMinCosTheta) && hasTransP);
                                if (acceptP)
                                {
                                    // §9.4 MIS for temporal reuse — match the
                                    // fresh-sample path (block 1a). Without MIS
                                    // pool/temporal/spatial candidates have higher
                                    // weight than fresh, biasing the RIS.
                                    if (kUseMIS && !applyRTXDI && prevType != (uint)LightType::Analytic)
                                    {
                                        float scatterPdfP = mi.evalPdf(sd, prevLs.dir, kUseBSDFSampling);
                                        prevLs.Li *= evalMIS(1, prevLs.pdf, 1, scatterPdfP);
                                    }
                                    float3 prevW3 = mi.eval(sd, prevLs.dir, path.sg);
                                    // pHat = luminance(Lr) at reader; consistent
                                    // with K-RIS path. Works for Dirac lights.
                                    float pHatPrev = luminance(prevW3 * prevLs.Li);
                                    // §9.4 layer (b) — retrace V on reservoir reuse (RTXDI BiasCorrection
                                    // analog). Mode 0=Off (default; matches RTXDI Basic, our shipping
                                    // behaviour: stored W carries write-time V). Mode 1=FullTrace (≡ RTXDI
                                    // RayTraced — unbiased, expensive). Mode 2=CacheCV (cheap CV+RRR via
                                    // cache, same PT-canonical knobs as the regular shadow gate). Env-map
                                    // samples have no finite-distance V — skip retrace for them.
                                    uint reuseMode = retraceOnReuseMode();
                                    if (reuseMode != 0u && prevType != (uint)LightType::EnvMap && pHatPrev > 0.f)
                                    {
                                        Ray vrayR = prevLs.getVisibilityRay();
                                        float vR = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                                        if (reuseMode == 2u)
                                        {
                                            // CacheCV path — vcWriteDiag inside evalRevalidationCV
                                            // already bumps the diag rays counter; no extra count here.
                                            vR = vq.traceVisibilityRayCV(vrayR, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                                        }
                                        else
                                        {
                                            vR = vq.traceVisibilityRay(vrayR) ? 1.f : 0.f;
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
                                            vcDiagCountRay(path.getPixel(), true, VC_RAY_SITE_REVAL);   // FullTrace retrace-on-reuse (temporal)
#endif
                                        }
#else
                                        vR = vq.traceVisibilityRay(vrayR) ? 1.f : 0.f;
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
                                        vcDiagCountRay(path.getPixel(), true, VC_RAY_SITE_REVAL);
#endif
#endif
                                        pHatPrev *= vR;
                                    }
                                    if (pHatPrev > 0.f)
                                    {
                                        float Mcap = min(prev.M, gMCap);
                                        float m_t = 1.f;
#if BIAS_CORRECTION == 1
                                        {
                                            // See cell-merge for m_canon formula
                                            // justification. Same-surface approx
                                            // for temporal (same pixel) is exact.
                                            float tPairwiseDenom = pHatPrev * tCanonM_save + prev.targetPdf * Mcap;
                                            if (tPairwiseDenom > 0.f)
                                            {
                                                m_t = (prev.targetPdf * Mcap) / tPairwiseDenom;
                                            }
                                            if (tCanonM_save + Mcap > 0.f)
                                            {
                                                tCanonMISAcc += tCanonM_save / (tCanonM_save + Mcap);
                                            }
                                        }
#endif
                                        float w    = m_t * pHatPrev * prev.W * Mcap;
                                        if (w > 0.f && !isnan(w))
                                        {
                                            local.wSum += w;
                                            local.M    += Mcap;
                                            tLocalMWeighted += m_t * Mcap;
                                            tPrevStreamed = true;
                                            if (sampleNext1D(path.sg) * local.wSum <= w)
                                            {
                                                local.lightTypeIndex = prev.lightTypeIndex;
                                                local.payload        = prev.payload;
                                                local.targetPdf      = pHatPrev;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        // Re-stream canonical with accumulated MIS weight for
                        // the temporal pairwise. If no prev was streamed (cold
                        // frame / silhouette reject), restore canonical verbatim.
#if BIAS_CORRECTION == 1
                        if (tCanonM_save > 0.f && tCanonTargetPdf_save > 0.f)
                        {
                            if (tPrevStreamed)
                            {
                                float tWnCanon = tCanonMISAcc * tCanonWSum_save;
                                if (tWnCanon > 0.f && !isnan(tWnCanon))
                                {
                                    local.wSum += tWnCanon;
                                    local.M    += tCanonM_save;
                                    tLocalMWeighted += tCanonMISAcc * tCanonM_save;
                                    if (sampleNext1D(path.sg) * local.wSum <= tWnCanon)
                                    {
                                        local.lightTypeIndex = tCanonLightTypeIndex_save;
                                        local.payload        = tCanonPayload_save;
                                        local.targetPdf      = tCanonTargetPdf_save;
                                    }
                                }
                            }
                            else
                            {
                                // No temporal contribution; restore canonical.
                                local.wSum           = tCanonWSum_save;
                                local.M              = tCanonM_save;
                                tLocalMWeighted      = tCanonM_save;
                                local.targetPdf      = tCanonTargetPdf_save;
                                local.lightTypeIndex = tCanonLightTypeIndex_save;
                                local.payload        = tCanonPayload_save;
                            }
                            local.M = tLocalMWeighted;
                        }
#endif

                        // ----- spatial: gather K random neighbour pixels -----------
                        // gSpatialPixelsK / gSpatialPixelsRadius are runtime
                        // knobs (Python-tunable via spatialPixelsK + Radius).
                        // Defaults 4 / 32 match RTXDI's 1-round k≈4-5; bumping
                        // K is the primary lever for testing the multi-round
                        // gap (more candidates per round) without an extra
                        // dispatch.
                        const uint kSpatialPixels = gSpatialPixelsK;
                        const int  kSpatialRadius = (int)gSpatialPixelsRadius;
                        uint2 px = path.getPixel();
                        // Pairwise MIS canonical-correction (Boksansky 2022 §4).
                        // Snapshot the local reservoir = "canonical" (K-RIS +
                        // any prior cell/temporal merges). Re-init local; the
                        // spatial loop will stream neighbours into the fresh
                        // local with pairwise m_j weights, accumulating the
                        // canonical's MIS contribution as m_canon_acc. At the
                        // end we re-stream canonical with that accumulated
                        // weight — fully unbiased pairwise MIS combine.
                        // BIAS_CORRECTION=0 path keeps the simpler Bitterli
                        // basic merge (skips snapshot / re-init / re-stream).
                        float canonM_save = 0.f;
                        float canonWSum_save = 0.f;
                        float canonTargetPdf_save = 0.f;
                        uint  canonLightTypeIndex_save = 0u;
                        uint  canonPayload_save = 0u;
                        float canonMISAcc = 0.f;
                        // m-weighted M accumulator. The standard ReSTIR finalize
                        // formula W = wSum / (pHat × M) requires that M reflect
                        // the same MIS partitioning as wSum. Without this, the
                        // pairwise estimator is biased: equal-pHat-equal-M case
                        // gives W/2 instead of W (verified analytically and
                        // matched the empirical Cornell 2D err 4.37 → 8.03
                        // regression on 2026-05-15). Each neighbour stream
                        // contributes m_j × Mcn; the canonical re-stream
                        // contributes canonMISAcc × canon.M. Sum = M_eff.
                        float localMWeighted = 0.f;
#if BIAS_CORRECTION == 1
                        canonM_save = local.M;
                        canonWSum_save = local.wSum;
                        canonTargetPdf_save = local.targetPdf;
                        canonLightTypeIndex_save = local.lightTypeIndex;
                        canonPayload_save = local.payload;
                        local.init();
#endif
                        for (uint s = 0u; s < kSpatialPixels; ++s)
                        {
                            float2 r = sampleNext2D(path.sg);
                            int2 off = int2((r - 0.5f) * 2.f * float(kSpatialRadius));
                            if (off.x == 0 && off.y == 0) continue;
                            int2 npx = int2(px) + off;
                            if (npx.x < 0 || npx.y < 0 ||
                                uint(npx.x) >= gFrameDimX || uint(npx.y) >= gFrameDimY) continue;
                            uint nIdx = uint(npx.y) * gFrameDimX + uint(npx.x);
                            Reservoir nbr = gPixelReservoirs[nIdx];
                            if (nbr.M <= 0.f || nbr.fingerprint == 0u) continue;
                            // Normal-aware rejection: skip neighbours whose
                            // surface diverged. 0.9 ≈ 26° matches RTXDI default.
                            if (nbr.normalOct != 0u)
                            {
                                float3 nbrN = unpackDirOct(nbr.normalOct);
                                if (dot(sd.faceN, nbrN) < kWSNormalCos) continue;
                            }
                            uint nbrType = unpackLightType(nbr.lightTypeIndex);
                            uint nbrIdx  = unpackLightIndex(nbr.lightTypeIndex);
                            LightSampleDI nbrLs;
                            bool nbrOk = false;
                            if (nbrType == (uint)LightType::Emissive)
                                nbrOk = rebuildEmissiveLightSample(nbrIdx, unpackUV(nbr.payload), sd, nbrLs);
                            else if (nbrType == (uint)LightType::Analytic)
                                nbrOk = rebuildAnalyticLightSample(nbrIdx, sd, path.sg, nbrLs);
                            else if (nbrType == (uint)LightType::EnvMap)
                                nbrOk = rebuildEnvMapLightSample(nbr.payload, sd, nbrLs);
                            if (!nbrOk) continue;
                            float NdotL_n = dot(sd.faceN, nbrLs.dir);
                            bool hasReflN  = (lobeTypes & (uint)LobeType::NonDeltaReflection) != 0;
                            bool hasTransN = (lobeTypes & (uint)LobeType::NonDeltaTransmission) != 0;
                            bool acceptN = ((NdotL_n > kMinCosTheta) && hasReflN)
                                        || ((NdotL_n < -kMinCosTheta) && hasTransN);
                            if (!acceptN) continue;
                            // §9.4 MIS for spatial reuse — see temporal block.
                            if (kUseMIS && !applyRTXDI && nbrType != (uint)LightType::Analytic)
                            {
                                float scatterPdfN = mi.evalPdf(sd, nbrLs.dir, kUseBSDFSampling);
                                nbrLs.Li *= evalMIS(1, nbrLs.pdf, 1, scatterPdfN);
                            }
                            float3 nbrW3 = mi.eval(sd, nbrLs.dir, path.sg);
                            // pHat = luminance(Lr); consistent with K-RIS path.
                            // Works for Dirac lights.
                            float pHatN = luminance(nbrW3 * nbrLs.Li);
                            // §9.4 layer (b) — retrace V on spatial reuse. See temporal block above.
                            uint reuseModeN = retraceOnReuseMode();
                            if (reuseModeN != 0u && nbrType != (uint)LightType::EnvMap && pHatN > 0.f)
                            {
                                Ray vrayN = nbrLs.getVisibilityRay();
                                float vN = 1.f;
#if USE_VISCACHE_VISIBILITYCHECK
                                if (reuseModeN == 2u)
                                {
                                    // CacheCV — vcWriteDiag inside evalRevalidationCV bumps counter.
                                    vN = vq.traceVisibilityRayCV(vrayN, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
                                }
                                else
                                {
                                    vN = vq.traceVisibilityRay(vrayN) ? 1.f : 0.f;
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
                                    vcDiagCountRay(path.getPixel(), true, VC_RAY_SITE_REVAL);   // FullTrace retrace-on-reuse (spatial)
#endif
                                }
#else
                                vN = vq.traceVisibilityRay(vrayN) ? 1.f : 0.f;
#if USE_VISCACHE && VISCACHE_DIAGNOSTICS
                                vcDiagCountRay(path.getPixel(), true, VC_RAY_SITE_REVAL);
#endif
#endif
                                pHatN *= vN;
                            }
                            if (pHatN <= 0.f) continue;
                            float Mcn = min(nbr.M, gMCap);
                            // Bias correction:
                            //   0 = Bitterli basic (M-weighted) — pHat_reader * W_j * M_j
                            //   1 = Pairwise MIS (Boksansky 2022 §4 / RTXDI Pairwise)
                            //       m_j = pHat_j*M_j / (pHat_reader*M_canon + pHat_j*M_j)
                            //       Uses snapshotted canonM_save (not the running local.M)
                            //       so all pairwise weights see the same canonical. After
                            //       the loop we re-stream canonical with accumulated
                            //       m_canonical_j weight — fully unbiased Talbot pairwise.
                            float m_j = 1.f;
#if BIAS_CORRECTION == 1
                            {
                                float pairwiseDenom = pHatN * canonM_save + nbr.targetPdf * Mcn;
                                if (pairwiseDenom <= 0.f) continue;
                                m_j = (nbr.targetPdf * Mcn) / pairwiseDenom;

                                // m_canon: RTXDI's proper formula needs
                                // canonicalWeightAtNeighbor = canon's sample's
                                // pHat at neighbour's surface. Load neighbour
                                // surface (VBuffer + ShadingData + Material-
                                // Instance) and re-evaluate canonical's light
                                // sample there. Falls back to M-ratio same-
                                // surface approx if neighbour VBuffer entry is
                                // missing or canon's light-sample rebuild fails
                                // at nbr surface.
                                float cWAtN_eff = canonTargetPdf_save;  // default fallback
                                bool haveCWAtN = false;
                                uint2 npx_u = uint2(uint(npx.x), uint(npx.y));
                                HitInfo nbrHit = HitInfo(vbuffer[npx_u]);
                                if (nbrHit.isValid() && canonTargetPdf_save > 0.f && canonM_save > 0.f)
                                {
                                    Ray cameraRayN = gScene.camera.computeRayPinhole(npx_u, params.frameDim);
                                    ShadingData sd_nbr = loadShadingData(nbrHit, cameraRayN.origin, cameraRayN.dir);
                                    let lod_nbr = ExplicitLodTextureSampler(params.lodBias);
                                    let hints_nbr = getMaterialInstanceHints(nbrHit, true);
                                    const IMaterialInstance mi_nbr = gScene.materials.getMaterialInstance(sd_nbr, lod_nbr, hints_nbr);
                                    uint canonType = unpackLightType(canonLightTypeIndex_save);
                                    uint canonIdx  = unpackLightIndex(canonLightTypeIndex_save);
                                    LightSampleDI canonLs_at_nbr;
                                    bool canonRebuildOk = false;
                                    if (canonType == (uint)LightType::Emissive)
                                        canonRebuildOk = rebuildEmissiveLightSample(canonIdx, unpackUV(canonPayload_save), sd_nbr, canonLs_at_nbr);
                                    else if (canonType == (uint)LightType::Analytic)
                                        canonRebuildOk = rebuildAnalyticLightSample(canonIdx, sd_nbr, path.sg, canonLs_at_nbr);
                                    else if (canonType == (uint)LightType::EnvMap)
                                        canonRebuildOk = rebuildEnvMapLightSample(canonPayload_save, sd_nbr, canonLs_at_nbr);
                                    if (canonRebuildOk)
                                    {
                                        float3 cWeight_at_nbr = mi_nbr.eval(sd_nbr, canonLs_at_nbr.dir, path.sg);
                                        cWAtN_eff = luminance(cWeight_at_nbr * canonLs_at_nbr.Li);
                                        haveCWAtN = true;
                                    }
                                }
                                if (haveCWAtN)
                                {
                                    // Proper RTXDI pairwise m_canon:
                                    //   m_canon = cWAtC * M_canon / (cWAtN * Mcn + cWAtC * M_canon)
                                    float cMisDenom = cWAtN_eff * Mcn + canonTargetPdf_save * canonM_save;
                                    if (cMisDenom > 0.f)
                                    {
                                        canonMISAcc += (canonTargetPdf_save * canonM_save) / cMisDenom;
                                    }
                                }
                                else if (canonM_save + Mcn > 0.f)
                                {
                                    // Same-surface fallback (M-ratio).
                                    canonMISAcc += canonM_save / (canonM_save + Mcn);
                                }
                            }
#endif
                            float wn  = m_j * pHatN * nbr.W * Mcn;
                            if (wn <= 0.f || isnan(wn)) continue;
                            local.wSum += wn;
                            local.M    += Mcn;
                            localMWeighted += m_j * Mcn;
                            if (sampleNext1D(path.sg) * local.wSum <= wn)
                            {
                                local.lightTypeIndex = nbr.lightTypeIndex;
                                local.payload        = nbr.payload;
                                local.targetPdf      = pHatN;
                            }
                        }
                        // Re-stream canonical with the accumulated MIS weight
                        // (Boksansky 2022 §4). RIS weight for canonical's sample:
                        //   wn_canon = canonMISAcc * canonical.W * canonical.targetPdf * canonical.M
                        //            = canonMISAcc * canonWSum_save
                        // (since canonical.W*M*pHat = wSum by the W definition).
                        // The streaming pick at the end gives canonical its proper
                        // chance to win against all neighbours we already streamed.
#if BIAS_CORRECTION == 1
                        if (canonM_save > 0.f && canonTargetPdf_save > 0.f)
                        {
                            float wn_canon = canonMISAcc * canonWSum_save;
                            if (wn_canon > 0.f && !isnan(wn_canon))
                            {
                                local.wSum += wn_canon;
                                local.M    += canonM_save;
                                localMWeighted += canonMISAcc * canonM_save;
                                if (sampleNext1D(path.sg) * local.wSum <= wn_canon)
                                {
                                    local.lightTypeIndex = canonLightTypeIndex_save;
                                    local.payload        = canonPayload_save;
                                    local.targetPdf      = canonTargetPdf_save;
                                }
                            }
                            else
                            {
                                // No valid neighbours streamed; restore canonical
                                // verbatim so downstream code sees the K-RIS state.
                                local.wSum           = canonWSum_save;
                                local.M              = canonM_save;
                                localMWeighted       = canonM_save;
                                local.targetPdf      = canonTargetPdf_save;
                                local.lightTypeIndex = canonLightTypeIndex_save;
                                local.payload        = canonPayload_save;
                            }
                            // Overwrite local.M with the m-weighted value so the
                            // finalize formula W = wSum / (pHat * M) uses M_eff.
                            // (Bitterli basic path keeps local.M unchanged.)
                            local.M = localMWeighted;
                        }
#endif
                    }

                    // (3) Swap winner if the local picked a sample we can rebuild.
                    // Skip the swap when only the original fresh sample contributed
                    // (M==1) — no rebuild needed, original ls is already correct.
                    // The rebuilder's offset / pdf reconstruction otherwise introduces
                    // small numerical drift that biases the metric vs vanilla.
                    if (local.M > 1.f && local.targetPdf > 0.f)
                    {
                        uint winnerType = unpackLightType(local.lightTypeIndex);
                        uint winnerIdx  = unpackLightIndex(local.lightTypeIndex);
                        LightSampleDI winnerLs;
                        bool winnerOk = false;
                        if (winnerType == (uint)LightType::Emissive)
                            winnerOk = rebuildEmissiveLightSample(winnerIdx, unpackUV(local.payload), sd, winnerLs);
                        else if (winnerType == (uint)LightType::Analytic)
                            winnerOk = rebuildAnalyticLightSample(winnerIdx, sd, path.sg, winnerLs);
                        else if (winnerType == (uint)LightType::EnvMap)
                            winnerOk = rebuildEnvMapLightSample(local.payload, sd, winnerLs);

                        if (winnerOk)
                        {
                            ls = winnerLs;
                            // Apply MIS the same way generateLightSample does
                            // (analytic lights skip MIS — Falcor convention).
                            if (kUseMIS && !applyRTXDI && ls.lightType != (uint)LightType::Analytic)
                            {
                                float scatterPdf = mi.evalPdf(sd, ls.dir, kUseBSDFSampling);
                                ls.Li *= evalMIS(1, ls.pdf, 1, scatterPdf);
                            }

                            float3 weight = mi.eval(sd, ls.dir, path.sg);
                            // ReSTIR W = wSum / (p̂(y) * M). With pHat=lum(Lr) and
                            // invPdf=1 convention, the candidate's contribution at
                            // the reader is `weight × ls.Li` (Lr_winner). Multiply
                            // by W to produce the unbiased pixel estimate.
                            // CRITICAL: do NOT multiply by ls.pdf here — that
                            // breaks Dirac lights (point/directional) where pdf=0
                            // makes the contribution evaluate to zero.
                            float winnerW = local.wSum / max(local.targetPdf * local.M, 1e-12f);
                            Lr = weight * ls.Li * winnerW;
                        }
                    }

                    // (4) Stream the per-pixel local into the home cell with M-cap
                    // accumulation. The cell aggregates across frames (M grows to
                    // gMCap) so its identity converges to the popular sample for
                    // the region. Read side only consumes identity; the cell's
                    // M/W are bookkeeping for this write-side reservoir merge.
                    mergeIntoCell(homeAddr, local, path.sg);

                    // (Pool write-back: now done at candidate-generation time
                    //  with per-entry sourcePdf — see (1) and (1b) above.
                    //  Winner write-back removed: it double-counted entries
                    //  and the writer's effective proposal pdf for the winner
                    //  isn't well-defined post-RIS.)

                    // (5) Persist the merged local back to the per-pixel
                    // reservoir for next frame's temporal reuse. Active when
                    // pixelReservoirEnabled() returns true.
                    if (pixelReservoirEnabled() && local.M > 0.f && local.targetPdf > 0.f)
                    {
                        uint pIdx = pixelIndex(path.getPixel());
                        Reservoir px = reservoirInit(0xFFFFFFFFu);
                        px.lightTypeIndex   = local.lightTypeIndex;
                        px.payload          = local.payload;
                        px.targetPdf        = local.targetPdf;
                        px.M                = min(local.M, gMCap);
                        px.W                = local.wSum / max(local.targetPdf * local.M, 1e-12f);
                        px.frameLastUpdated = gFrameCount;
                        // Stamp the shading normal so spatial gather can reject
                        // neighbours whose surface diverged (silhouette / sharp
                        // crease). Standard ReSTIR variance-reduction technique.
                        px.normalOct        = packDirOct(sd.faceN);
                        gPixelReservoirs[pIdx] = px;
                    }
#endif // !WS_CELL_POOL_FILL_ONLY

#if WS_CELL_POOL_FILL_ONLY
                    // §9.4 Step (b) fill-only: zero out Lr so the visibility-ray
                    // block below skips and the path's contribution this dispatch
                    // is exactly zero. Pool inserts above are the only side effect.
                    Lr = float3(0.f);
#endif
                }
#endif // USE_WS_RESERVOIRS

                if (any(Lr > 0.f))
                {
                    Ray ray = ls.getVisibilityRay();


                    if (isCurvePolyTubeHit)
                    {
                        // For curves tessellated into poly-tubes, we make sure that the origin is on the same side as light
                        // so there is no self-shadowing (transmission lobe of hair BSDF takes care of that).
                        if (dot(sd.frame.N, ray.dir) < 0.f)
                        {
                            ray.origin = ray.origin - sd.frame.N * sd.curveRadius * 2.1f;
                        }
                    }

                    logTraceRay(PixelStatsRayType::Visibility);
#if USE_VISCACHE_VISIBILITYCHECK
#ifdef VISCACHE_DIAGNOSTICS
                    // Write diagnostics only for the primary hit's NEE ray (bounce 0).
                    // Later bounces use the non-diagnostic path to avoid overwriting.
                    float visWeight = (path.getVertexIndex() <= 1)
                        ? vq.traceVisibilityRayCVDiag(ray, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N)
                        : vq.traceVisibilityRayCV(ray, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
#else
                    float visWeight = vq.traceVisibilityRayCV(ray, path.sg, path.getPixel(), path.getSampleIdx(), sd.frame.N);
#endif
                    if (visWeight > 0.f) addToPathContribution(path, Lr * visWeight);
                    bool chosenVisible = visWeight > 0.f;
#else
                    bool visible = vq.traceVisibilityRay(ray);
                    if (visible) addToPathContribution(path, Lr);
                    bool chosenVisible = visible;
#endif

#if USE_WS_RESERVOIRS
                    // §9.4 LOCK-IN BREAK: V=0 invalidation of per-pixel reservoir.
                    // Active when pixelReservoirEnabled() returns true.
                    if (path.getVertexIndex() == 1 && enabled() && pixelReservoirEnabled()
                        && !chosenVisible && (isEmissive || isAnalytic || isEnv))
                    {
                        uint pIdx = pixelIndex(path.getPixel());
                        gPixelReservoirs[pIdx] = reservoirInit(0u);
                    }
#endif
                }
            }
        }

        // Russian roulette to terminate paths early.
        if (kUseRussianRoulette)
        {
            if (terminatePathByRussianRoulette(path, sampleNext1D(path.sg))) return;
        }

        const bool wasDeltaOnlyPathBeforeScattering = path.isDeltaOnlyPath();

        // Generate the next path segment or terminate.
        bool valid = generateScatterRay(sd, mi, path);

        // Output guide data.
        if (path.getVertexIndex() == 1)
        {
            setPrimarySurfaceGuideData(path.guideData, sd, bsdfProperties);
        }
        if (path.getVertexIndex() == 2 && (path.getBounces(BounceType::Specular) == 1 || path.getBounces(BounceType::Transmission) == 1))
        {
            setIndirectSurfaceGuideData(path.guideData, sd, bsdfProperties);
        }

        if (kOutputNRDData)
        {
            const uint2 pixel = path.getPixel();
            const uint outSampleIdx = params.getSampleOffset(pixel, sampleOffset) + path.getSampleIdx();

            setNRDPrimaryHitEmission(outputNRD, kUseNRDDemodulation, path, pixel, isPrimaryHit, attenuatedEmission);
            setNRDPrimaryHitReflectance(outputNRD, kUseNRDDemodulation, path, pixel, isPrimaryHit, sd, bsdfProperties);

            setNRDSampleHitDist(outputNRD, path, outSampleIdx);
            setNRDSampleEmission(outputNRD, kUseNRDDemodulation, path, outSampleIdx, isPrimaryHit, attenuatedEmission, wasDeltaOnlyPathBeforeScattering);
            setNRDSampleReflectance(outputNRD, kUseNRDDemodulation, path, outSampleIdx, isPrimaryHit, sd, bsdfProperties, lobeTypes, wasDeltaOnlyPathBeforeScattering);
            setNRDPrimaryHitSeparatedRadiance(outputNRD, kUseNRDDemodulation, path, isPrimaryHit, outSampleIdx);
        }

        // Check if this is the last path vertex.
        const bool isLastVertex = hasFinishedSurfaceBounces(path);

        // Terminate if this is the last path vertex and light sampling already completely sampled incident radiance.
        if (kUseNEE && !kUseMIS && isLastVertex && path.isLightSamplable()) valid = false;

        // Terminate caustics paths.
        if (kDisableCaustics && path.getBounces(BounceType::Diffuse) > 0 && path.isSpecular()) valid = false;

        if (!valid)
        {
            path.terminate();
        }
    }

    /** Handle the case when a scatter ray misses the scene.
        \param[in,out] path The path state.
    */
    /** Pure helper: evaluate the env-map radiance contribution at a path miss.

        Computes `Le` and the MIS weight for the missed env-map contribution.
        Does NOT modify path state or write outputs — purely computational so
        external callers (e.g. ReSTIRPTPass plugin's handleMiss) can reuse the
        same env-eval logic without duplicating it. Refactor-only on Falcor 8's
        vanilla path: vanilla output remains byte-identical.

        @param[in]  path       PathState at miss.
        @param[out] Le         Env radiance along `path.dir` (zero if no contribution).
        @param[out] misWeight  MIS weight (1 if no NEE/MIS combination applies).
        @return    true if the env contribution should be added (computeEnv == true), false otherwise.
    */
    bool evalEnvAtMiss(in const PathState path, out float3 Le, out float misWeight)
    {
        Le = float3(0.f);
        misWeight = 1.f;

        const bool isLightSamplable = path.isLightSamplable();
        bool computeEnv = kUseEnvLight && (!kUseNEE || kUseMIS || !path.isLightSampled() || !isLightSamplable);

        // With RTXDI enabled, we sample the full direct illumination contribution on the primary hit.
        // Skip any additional contribution on the secondary hit unless it comes from a scatter event
        // that RTXDI cannot handle, such as transmission, delta or volume scattering events.
        if (kUseRTXDI && path.getVertexIndex() == 2 && !path.isTransmission() && !path.isDelta()) computeEnv = false;

        if (!computeEnv) return false;

        if (kUseNEE && kUseMIS && path.isLightSampled() && isLightSamplable)
        {
            // If NEE and MIS are enabled, and we've already sampled the env map,
            // then we need to evaluate the MIS weight here to account for the remaining contribution.

            // Evaluate PDF, had it been generated with light sampling.
            float lightPdf = getEnvMapSelectionProbability() * envMapSampler.evalPdf(path.dir);

            // Compute MIS weight by combining this with BSDF sampling.
            // Note we can assume path.pdf > 0.f since we shouldn't have got here otherwise.
            misWeight = evalMIS(1, path.pdf, 1, lightPdf);
        }

        Le = envMapSampler.eval(path.dir);
        return true;
    }

    void handleMiss(inout PathState path)
    {
        // Upon miss:
        // - Compute MIS weight if previous path vertex sampled a light
        // - Evaluate environment map
        // - Write guiding data
        // - Terminate the path

        float3 Le;
        float misWeight;
        const bool computeEnv = evalEnvAtMiss(path, Le, misWeight);
        const bool isLightSamplable = path.isLightSamplable();   // kept for guide-data branch below

        float3 emitterRadiance = 0.f;

        if (computeEnv)
        {
            logPathVertex();

            emitterRadiance = misWeight * Le;
            addToPathContribution(path, emitterRadiance);

            if (kOutputGuideData && path.getVertexIndex() == 2
                && (path.getBounces(BounceType::Specular) == 1
                || path.getBounces(BounceType::Transmission) == 1))
            {
                // Compress dynamic range similar to UE4.
                float3 compressedColor = pow(Le / (Le + 1.0f), 0.454545f);
                path.guideData.setIndirectAlbedo(compressedColor);
                path.guideData.setReflectionPos(path.dir * kEnvMapDepth);
            }
        }

        if (kOutputGuideData && path.getVertexIndex() == 1)
        {
            path.guideData.setGuideNormal(-path.dir);
        }

        if (kOutputNRDData)
        {
            const uint outSampleIdx = params.getSampleOffset(path.getPixel(), sampleOffset) + path.getSampleIdx();
            setNRDSampleHitDist(outputNRD, path, outSampleIdx);
        }

#if defined(DELTA_REFLECTION_PASS)
        if (path.isDeltaReflectionPrimaryHit())
        {
            writeNRDDeltaReflectionGuideBuffers(outputNRD, kUseNRDDemodulation, path.getPixel(), 0.f, path.thp * emitterRadiance, -path.dir, 0.f, kNRDInvalidPathLength, kNRDInvalidPathLength);
        }
        else
        {
            writeNRDDeltaReflectionGuideBuffers(outputNRD, kUseNRDDemodulation, path.getPixel(), 0.f, 0.f, -path.dir, 0.f, kNRDInvalidPathLength, kNRDInvalidPathLength);
        }
#elif defined(DELTA_TRANSMISSION_PASS)
        if (path.isDeltaTransmissionPath())
        {
            writeNRDDeltaTransmissionGuideBuffers(outputNRD, kUseNRDDemodulation, path.getPixel(), 0.f, path.thp * emitterRadiance, -path.dir, 0.f, kNRDInvalidPathLength, path.origin + path.dir * kNRDInvalidPathLength);
        }
        else
        {
            writeNRDDeltaTransmissionGuideBuffers(outputNRD, kUseNRDDemodulation, path.getPixel(), 0.f, 0.f, -path.dir, 0.f, kNRDInvalidPathLength, 0.f);
        }
#endif

        path.terminate();
    }

    /** Write path contribution to output buffer.
    */
    void writeOutput(const PathState path)
    {
        assert(!any(isnan(path.L)));

        // Log path length.
        logPathLength(getTerminatedPathLength(path));

        const uint2 pixel = path.getPixel();
        const uint outIdx = params.getSampleOffset(pixel, sampleOffset) + path.getSampleIdx();

        if (kSamplesPerPixel == 1)
        {
            // Write color directly to frame buffer.
            outputColor[pixel] = float4(path.L, 1.f);
        }
        else
        {
            // Write color to per-sample buffer.
            sampleColor[outIdx].set(path.L);
        }

        if (kOutputGuideData)
        {
            sampleGuideData[outIdx] = path.guideData;
        }

        if (kOutputNRDData)
        {
            // TODO: Optimize this for 1 SPP. It doesn't have to go through resolve pass like the color above.
            NRDRadiance data = {};

            if (path.isDiffusePrimaryHit()) data.setPathType(NRDPathType::Diffuse);
            else if (path.isSpecularPrimaryHit()) data.setPathType(NRDPathType::Specular);
            else if (path.isDeltaReflectionPrimaryHit()) data.setPathType(NRDPathType::DeltaReflection);
            else if (path.isDeltaTransmissionPath()) data.setPathType(NRDPathType::DeltaTransmission);
            else data.setPathType(NRDPathType::Residual);

            data.setRadiance(path.L);

            outputNRD.sampleRadiance[outIdx] = data;
        }
    }
};

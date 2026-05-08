/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/
#include "Scene/SceneDefines.slangh"

import Scene.RaytracingInline;
import Rendering.Lights.EnvMapSampler;
import Rendering.Lights.EmissiveLightSampler;
import Rendering.Lights.EmissiveLightSamplerHelpers;
import Rendering.Lights.LightHelpers;
// [Falcor 8] Material types resolved through scene type conformances — no explicit imports needed.
import Rendering.Materials.Microfacet;
import Rendering.Materials.InteriorListHelpers;
import Rendering.Volumes.HomogeneousVolumeSampler;
import Rendering.Volumes.PhaseFunction;
import Rendering.Utils.PixelStats;
import RenderPasses.Shared.Denoising.NRDBuffers;
import RenderPasses.Shared.Denoising.NRDData;
import RenderPasses.Shared.Denoising.NRDHelpers;
import RenderPasses.Shared.Denoising.NRDConstants;
import NRDHelpers;
import Utils.Color.ColorHelpers;
import Utils.Geometry.GeometryHelpers;
import Utils.Debug.PixelDebug;
import LoadShadingData;
import Falcor8Compat;
import PathBuilder;
import PathReservoir;
import PathReservoirCellPool;

#include "Utils/Math/MathConstants.slangh"

__exported import PathState;
__exported import Params;

uint getAllowedBSDFFlags(bool isSpecularBounce)
{
    // [Falcor 8] LobeType bit layout — specular = 0x66, diffuse = 0x11.
    if (kSeparatePathBSDF) return isSpecularBounce ? 0x66 : 0x11;
    else return 0xff; // LobeType::All
}

/// [Falcor 8] BSDF lobe enumeration via IMaterialInstance.getLobeTypes(sd).
uint getBSDFLobes(const ShadingData sd)
{
    let lod = ExplicitLodTextureSampler(0.0f);
    let mi = gScene.materials.getMaterialInstance(sd, lod);
    return mi.getLobeTypes(sd);
}

struct PathTracer
{
    RestirPathTracerParams params;                  ///< Runtime parameters.
    EnvMapSampler envMapSampler;                    ///< Environment map sampler. Only valid when kUseEnvLight == true.
    EmissiveLightSampler emissiveSampler;           ///< Emissive light sampler. Only valid when kUseEmissiveLights == true.

    Texture2D<PackedHitInfo> vbuffer;               ///< Fullscreen V-buffer for the primary hits.

    NRDBuffers outputNRD;                           ///< Output NRD data.
    RWTexture2D<float4> outputNRDDiffuseRadianceHitDist;    ///< Output resolved diffuse color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.
    RWTexture2D<float4> outputNRDSpecularRadianceHitDist;   ///< Output resolved specular color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.
    RWTexture2D<float4> outputNRDResidualRadianceHitDist;   ///< Output resolved residual color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.

    RWTexture2D<float4> outputColor;                ///< Output color buffer if kSamplesPerPixel == 1.
    RWTexture2D<float4> outputDebug;                ///< Output debug data. Valid if OUTPUT_DEBUG is nonzero.
    RWTexture2D<uint> outputTime;                   ///< Output timing data. Valid if OUTPUT_TIME is nonzero.

    Texture2D<float4> directLighting;                   ///< Output offset into per-sample buffers. Only valid when kSamplesPerPixel == 0.

    RWStructuredBuffer<PathReservoir> outputReservoirs;            ///< Output paths from the path tracing pass.

    /// Optional world-cell-keyed reservoir pool (restirpt_3d, Task #15).
    /// Bound only when params.restirptAddrMode == 1; null otherwise.
    /// One PathReservoirCellSlot per cell (fingerprint + reservoir).
    RWStructuredBuffer<PathReservoirCellSlot> pathReservoirCellPool;
    bool isLastRound;
    bool useDirectLighting;
    int  gSppId;
    int  gNumSpatialRounds;

    /*******************************************************************
                                Static members
    *******************************************************************/

    // Render settings that depend on the scene.
    // TODO: Move into scene defines.
    //static bool kUseEnvLight = USE_ENV_LIGHT;
    //static bool kUseEmissiveLights = USE_EMISSIVE_LIGHTS;
    //static bool kUseAnalyticLights = USE_ANALYTIC_LIGHTS;
    bool kUseEnvLight;
    bool kUseEmissiveLights;
    bool kUseAnalyticLights;

    // Additional specialization.
    static const bool kOutputTime = OUTPUT_TIME != 0;

    /** Types of samplable lights.
    */
    enum class LightSampleType
    {
        EnvMap, //0
        Emissive, //1
        Analytic //2
    };

    /** Describes a light sample.
    */
    struct LightSample
    {
        float3  Li;            ///< Incident radiance at the shading point (unshadowed). This is already divided by the pdf.
        float   pdf;           ///< Pdf with respect to solid angle at the shading point.
        float3  origin;        ///< Ray origin for visibility evaluation (offseted to avoid self-intersection).
        float   distance;      ///< Ray distance for visibility evaluation (shortened to avoid self-intersection).
        float3  dir;           ///< Ray direction for visibility evaluation (normalized).
        uint    lightType;     ///< Light type this sample comes from (LightSampleType casted to uint).
        HitInfo packedHit;     ///< Lin 2026 §6.2.3: light surface hit (Triangle for Emissive; invalid otherwise). Used by addNeeVertex to populate rcVertexHit when force-marking NEE light as rcVertex.
        float3  lightNormalW;  ///< Lin 2026 §6.2.3: light surface normal (only meaningful for Emissive). Used to compute G_src = cos(N_light, -dir) / dist² for force-NEE rcVertex's cachedJacobian.

        Ray getVisibilityRay() { return Ray(origin, dir, 0.f, distance); }
    };

    /** Describes a path vertex.
    */
    struct PathVertex
    {
        uint index;         ///< Vertex index (0 = camera, 1 = primary hit, 2 = secondary hit, etc.).
        float3 pos;         ///< Vertex position.
        float3 normal;      ///< Shading normal at the vertex (zero if not on a surface).
        float3 faceNormal;  ///< Geometry normal at the vertex (zero if not on a surface).

        /** Create a path vertex.
            \param[in] index Vertex index.
            \param[in] pos Vertex position.
            \param[in] normal Shading normal.
            \param[in] faceNormal Geometry normal.
            \return Returns a path vertex.
        */
        static PathVertex create(uint index, float3 pos, float3 normal = float3(0.f), float3 faceNormal = float3(0.f))
        {
            PathVertex v = {};
            v.index = index;
            v.pos = pos;
            v.normal = normal;
            v.faceNormal = faceNormal;
            return v;
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
    };

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

    /** Resolve the reservoir-buffer offset for a given screen pixel.

        Dispatches based on `restirptAddrMode` (Task #12, mirrors VisCache's
        `gWSPoolAddrMode` from WS-ReSTIR DI):
          mode=0 (default): pixel-keyed Morton-tile offset (current behavior).
          mode=1 (3D):      world-cell hash of (primary-hit posA, faceN).

        At mode=0 the load short-circuits and the cost is one branch + the
        existing pixel-keyed offset compute (no perf regression vs the
        previous 1-arg call). At mode=1 a vbuffer fetch + ShadingData decode
        is required; falls back to pixel-keyed if the primary ray missed.

        @param[in] pixel  Screen pixel.
        @return    Reservoir-buffer index.
    */
    // 1-arg form: pixel-only (always 2D pixel-keyed). Used at sites that
    // can't conveniently load primary-hit shading data.
    uint resolveReservoirOffset(const uint2 pixel)
    {
        return params.getReservoirOffset(pixel);
    }

    // 3-arg form: dispatches based on restirptAddrMode using the caller's
    // pre-loaded primary-hit posA/faceN. Avoids the cross-struct
    // loadShadingData/gScene.getVertexData call from inside this method,
    // which triggers DXGI_DEVICE_REMOVED in compute-pass contexts when
    // accessed via ParameterBlock<PathTracer>.
    uint resolveReservoirOffset(const uint2 pixel, const float3 posA, const float3 faceN)
    {
        return params.getReservoirOffset(pixel, posA, faceN);
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
        path.prefixThp = float3(1.f);
        path.rcVertexPathTreeIrradiance = float3(0.f);

        path.LDeltaDirect = float3(0.f);
        path.enableRandomReplay = false;
        path.useHybridShift = ShiftMapping(kShiftStrategy) == ShiftMapping::Hybrid;
        path.isLastVertexClassifiedAsRough = true;
        path.isReplayForHybridShift = false;

        // Load the primary hit info from the V-buffer.
        // If invalid, the path is still active and treated as a miss.
        uint2 pixel = path.getPixel();
        const HitInfo hit = HitInfo(vbuffer[pixel]);

        if (hit.isValid())
        {
            path.setHit(hit);
            //path.setVertexIndex(1);
        }

        // TODO: Support depth-of-field using computeRayThinlens, if aperture size > 0.
        Ray cameraRay = gScene.camera.computeRayPinhole(pixel, params.frameDim);
        path.origin = cameraRay.origin;
        path.dir = cameraRay.dir;

        // Create sample generator.
        static const uint itersPerShaderPass = PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing ? kSamplesPerPixel : kCandidateSamples;

        uint maxSpp = itersPerShaderPass > 0 ? itersPerShaderPass : kMaxSamplesPerPixel;
        path.sg = SampleGenerator(pixel, (itersPerShaderPass + 1 + gNumSpatialRounds) * params.seed + path.getSampleIdx());

        if (kOutputNRDData)
        {
            path.hitDist = 0;
            path.rcPrevVertexWo = 0;
            path.sharedScatterDir = 0;
        }

        path.pathBuilder.init(path.sg);
        path.pathReservoir.init();
    }

    // generate random replay path
    void generateRandomReplayPath(out PathState path, HitInfo hit, Ray ray, uint randomSeed, int randomReplayLength, bool isLastVertexNEE, bool isRcVertexEscapedVertex)
    {
        path = {};
        path.L = 0.f;
        path.setActive();
        path.thp = float3(1.f);
        path.prefixThp = float3(1.f);
        path.rcVertexPathTreeIrradiance = float3(0.f);

        path.enableRandomReplay = true;
        path.useHybridShift = ShiftMapping(kShiftStrategy) == ShiftMapping::Hybrid;
        path.setHit(hit);

        path.origin = ray.origin;
        path.dir = ray.dir;

        path.sg = SampleGenerator(randomSeed); 

        path.randomReplayIsNEE = isLastVertexNEE && !isRcVertexEscapedVertex;
        path.randomReplayIsEscaped = !isLastVertexNEE && !isRcVertexEscapedVertex;
        path.randomReplayLength = randomReplayLength;

        path.pathReservoir.init();
    }


    /** Set up path for logging and debugging.
        \param[in] path Path state.
    */
    void setupPathLogging(const PathState path)
    {
        printSetPixel(path.getPixel());
        logSetPixel(path.getPixel());
    }

    /** Update the path throughouput
        \param[in,out] path Path state.
        \param[in] weight Vertex throughput.
    */
    void updatePathThroughput(inout PathState path, const float3 weight)
    {
        path.thp *= weight;
    }

    void invalidateAndTerminateReplayPath(inout PathState path)
    {
        path.rcPrevVertexHit = HitInfo();
        path.rcPrevVertexWo = float3(0);
        path.L = 0.f;
        path.thp = 0.f;
        path.terminate();
    }

    void setDataBeforeTermination(inout HitInfo rcPrevHit, inout float3 rcPrevHitWo)
    {
        rcPrevHit = HitInfo();
        rcPrevHitWo = float3(0);
    }

    /** Generates a new scatter ray using BSDF importance sampling.
        \param[in] sd Shading data.
        \param[in,out] path The path state.
        \return True if a ray was generated, false otherwise.
    */
    bool generateScatterRay(const ShadingData sd, inout PathState path)
    {
        bool isCurveHit = path.hit.getType() == HitType::Curve;

        // Generate a BSDF sample.
        bool valid;
        BSDFSample_ result;

        // Always importance-sample.
        if (kUseBSDFSampling) valid = sampleBSDF(sd, path.sg, result, true);
        else valid = sampleBSDF_Reference(sd, path.sg, result);

        float pdfAll = result.pdf;
        if (kSeparatePathBSDF) result.pdf = result.pdfSingle;

        // Ignore valid on purpose for now.
        if (kOutputNRDData && path.length == 0)
        {
            path.setDiffusePrimaryHit(result.isLobe(LobeType::Diffuse));
            path.setSpecularPrimaryHit(result.isLobe(LobeType::Specular));
        }

        if (valid)
        {
            // store sampled path type (diffuse or non-diffuse)

            path.dir = result.wi;

            // add to path buffer
            // also multiply pdf

            path.thp *= result.weight;

            // this is pdfAll
            path.pdf = pdfAll;

            // daqi: save the Jacobian for rcVertex
            if (path.length == path.pathBuilder.rcVertexLength)
            {
                // TODO: use component PDF
                path.pathBuilder.cachedJacobian.y = result.pdf;
            }

            path.prevScatterPdf = result.pdf;

            if (result.pdf <= 0.f) // invalid
            {
                return false;
            }

#if _USE_LEGACY_SHADING_CODE
            // Legacy BRDF code sometimes returns infinite PDF values.
            // We clamp them to avoid getting NaNs from the evalMIS function.
            path.pdf = min(path.pdf, 1e30f);
#endif

            path.clearEventFlags();

            // Handle reflection events.

            if (result.isLobe(LobeType::Reflection))
            {
                // We classify specular events as diffuse if the roughness is above some threshold.
                bool isDiffuse = result.isLobe(LobeType::DiffuseReflection) || getRoughness(sd) > params.specularRoughnessThreshold;
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
            if (result.isLobe(LobeType::Delta))
            {
                path.setDelta();
            }

            if (result.isLobe(LobeType::Specular) || result.isLobe(LobeType::Delta))
            {
                path.setSpecularBounce();
            }

            // daqi: record delta and transmission event before/after rcVertex, this is important because such information will be used in computing the Jacobian in shift.slang
            if (path.length == path.pathBuilder.rcVertexLength)
            {
                path.pathBuilder.pathFlags.insertIsDeltaEvent(result.isLobe(LobeType::Delta), false);
                path.pathBuilder.pathFlags.insertIsTransmissionEvent(result.isLobe(LobeType::Transmission), false);
                if (kSeparatePathBSDF)
                    path.pathBuilder.pathFlags.insertIsSpecularBounce(path.isSpecularBounce(), false);
            }

            // Handle transmission events.
            if (result.isLobe(LobeType::Transmission))
            {
                path.incrementBounces(BounceType::Transmission);
                path.setTransmission();

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

            // Save the shading normal. This is needed for MIS.
            path.normal = sd.frame.N;

            // Mark the path as valid only if it has a non-zero throughput.
            valid = any(path.thp > 0.f);
            // Add to the path gaph.
            // TODO: Handle specular/delta/transmission events.
            if (valid)
            {
                if (path.length <= path.pathBuilder.rcVertexLength)
                    path.recordPrefixThp();
            }
        }
        else
        {
            path.thp = 0.f;
        }

        return valid;
    }

    // TODO: support BySampledBSDF replay
    bool generateScatterRayGivenDirection(const ShadingData sd, float3 dir, inout PathState path)
    {
        bool isCurveHit = path.hit.getType() == HitType::Curve;

        // Generate a BSDF sample.
        bool valid = true;
        BSDFSample_ result;

        bool isDeltaEvent = path.pathBuilder.pathFlags.decodeIsDeltaEvent(path.length < 1);
        bool isSpecularBounce = path.pathBuilder.pathFlags.decodeIsSpecularBounce(path.length < 1);

        if (isDeltaEvent) valid = false; // not allowing delta event to be shifted by directional reuse

        if (valid)
        {
            float pdfAll = 0.f; // pdf with all BSDF

            {
                result.wi = dir;

                uint allowedBSDFFlags = getAllowedBSDFFlags(isSpecularBounce);

                result.weight = evalBSDFCosine(sd, dir, allowedBSDFFlags);

                if (kUseBSDFSampling)
                {
                    // this is single pdf
                    result.pdf = evalPdfBSDF(sd, result.wi, pdfAll, allowedBSDFFlags, false);
                }
                else
                {
                    result.pdf = dot(sd.frame.N, result.wi) / M_PI;
                }

                result.weight /= result.pdf;

                if (result.pdf <= 0.f)
                {
                    result.weight = 0.f;
                }
            }

            path.dir = result.wi;

            // add to path buffer
            // also multiply pdf
            path.thp *= result.weight;

            path.pdf = pdfAll;

            if (path.length == path.pathBuilder.rcVertexLength)
            {
                path.pathBuilder.cachedJacobian.y = result.pdf;
            }

            // daqi: record the scatter pdf, we will need to use that later for the cachedJacobian
            path.prevScatterPdf = result.pdf;

#if _USE_LEGACY_SHADING_CODE
            // Legacy BRDF code sometimes returns infinite PDF values.
            // We clamp them to avoid getting NaNs from the evalMIS function.
            path.pdf = min(path.pdf, 1e30f);
#endif

            path.clearEventFlags();

            // daqi: if we use direction reuse, then base and offset path reflection/transmission type is allowed to be different
            bool isTransmissionEvent = dot(sd.frame.N, result.wi) < 0;

            // daqi: set delta/transmission path flags. we don't care about other path flags since our resampling doesn't depend on the sampled BSDF components
            // Handle transmission events.
            if (isTransmissionEvent)
            {
                // Compute ray origin for next ray segment.
                path.origin = sd.computeRayOrigin(false);
                path.setTransmission();

                // Update interior list and inside volume flag.
                if (!sd.mtl.isThinSurface())
                {
                    uint nestedPriority = sd.mtl.getNestedPriority();
                    path.interiorList.handleIntersection(sd.materialID, nestedPriority, sd.frontFacing);
                    path.setInsideDielectricVolume(!path.interiorList.isEmpty());
                }
            }

            if (isSpecularBounce)
            {
                path.setSpecularBounce();
            }

            // Save the shading normal. This is needed for MIS.
            path.normal = sd.frame.N;

            // Mark the path as valid only if it has a non-zero throughput.
            valid = any(path.thp > 0.f);

            // Add to the path gaph.
            // TODO: Handle specular/delta/transmission events.
            if (valid)
            {
                if (path.length <= path.pathBuilder.rcVertexLength)
                    path.recordPrefixThp();
            }
        }

        return valid;
    }



    /** Evaluates the currently configured heuristic for multiple importance sampling (MIS).
        \param[in] n0 Number of samples taken from the first sampling strategy.
        \param[in] p0 Pdf for the first sampling strategy.
        \param[in] n1 Number of samples taken from the second sampling strategy.
        \param[in] p1 Pdf for the second sampling strategy.
        \return Weight for the contribution from the first strategy (p0).
    */
    static float evalMIS(float n0, float p0, float n1, float p1)
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
    bool generateEnvMapSample(const PathVertex vertex, inout SampleGenerator sg, out LightSample ls)
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

        return any(ls.Li > 0.f);
    }

    /** Generates a light sample on the emissive geometry.
        \param[in] vertex Path vertex.
        \param[in] upperHemisphere True if only upper hemisphere (w.r.t. shading normal) should be considered.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateEmissiveSample(const PathVertex vertex, const bool upperHemisphere, inout SampleGenerator sg, out LightSample ls)
    {
        ls = {}; // Default initialization to avoid divergence at returns.
        if (!kUseEmissiveLights) return false;

        TriangleLightSample tls;

        // TODO: when random number replay, this can fails with light BVH that previously returns valid samples, why?
        if (!emissiveSampler.sampleLight(vertex.pos, vertex.normal, upperHemisphere, sg, tls)) return false;

        // Setup returned sample.
        ls.Li = tls.pdf > 0.f ? tls.Le / tls.pdf : float3(0);
        ls.pdf = tls.pdf;
        // Offset shading and light position to avoid self-intersection.
        float3 lightPos = computeRayOrigin(tls.posW, tls.normalW);
        ls.origin = vertex.getRayOrigin(lightPos - vertex.pos);
        float3 toLight = lightPos - ls.origin;
        ls.distance = length(toLight);
        ls.dir = normalize(toLight);

        // Lin 2026 §6.2.3: synthesize a Falcor TriangleHit from the global emissive
        // triangle index so addNeeVertex can store it in rcVertexHit (matching the
        // BSDF-hit-emissive escape-vertex format). MeshLightData.triangleOffset
        // gives the global→(instanceID, localPrimIdx) mapping. Also stash the
        // light surface normal — used by the addNeeVertex caller to compute the
        // source-pixel geometric factor G_src for the force-NEE cachedJacobian.
        MeshLightData mld = gScene.lightCollection.getMeshData(tls.triangleIndex);
        TriangleHit triHit;
        triHit.instanceID = GeometryInstanceID(mld.instanceID, 0);
        triHit.primitiveIndex = tls.triangleIndex - mld.triangleOffset;
        triHit.barycentrics = tls.uv;
        ls.packedHit = HitInfo(triHit);
        ls.lightNormalW = tls.normalW;

        return any(ls.Li > 0.f);
    }

    /** Generates a light sample on the analytic lights.
        \param[in] vertex Path vertex.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateAnalyticLightSample(const PathVertex vertex, inout SampleGenerator sg, out LightSample ls)
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

        return any(ls.Li > 0.f);
    }

    void analyticLightSampleSkipRandomNumber(inout SampleGenerator sg)
    {
        uint lightCount = gScene.getLightCount();
        if (!kUseAnalyticLights || lightCount == 0) return;
        uint lightIndex = min(uint(sampleNext1D(sg) * lightCount), lightCount - 1);

        LightData light = gScene.getLight(lightIndex);

        switch (light.type)
        {
        case LightType::Rect:
        case LightType::Sphere:
        case LightType::Disc:
        case LightType::Distant:
            sampleNext2D(sg);
        default:
        }
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

    float getEnvMapSelectionProbability() { float p[3]; getLightTypeSelectionProbabilities(p); return p[0]; }
    float getEmissiveSelectionProbability() { float p[3]; getLightTypeSelectionProbabilities(p); return p[1]; }
    float getAnalyicSelectionProbability() { float p[3]; getLightTypeSelectionProbabilities(p); return p[2]; }

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

        pdf = 0.f;
        return false;
    }

    /** Samples a light source in the scene.
        This function first stochastically selects a type of light source to sample,
        and then calls that the sampling function for the chosen light type.
        The upper/lower hemisphere is defined as the union of the hemispheres w.r.t. to the shading and face normals.
        \param[in] vertex Path vertex.
        \param[in] sampleUpperHemisphere True if the upper hemisphere should be sampled.
        \param[in] sampleLowerHemisphere True if the lower hemisphere should be sampled.
        \param[in,out] sg Sample generator.
        \param[out] ls Struct describing valid samples.
        \return True if the sample is valid and has nonzero contribution, false otherwise.
    */
    bool generateLightSample(const PathVertex vertex, const bool sampleUpperHemisphere, const bool sampleLowerHemisphere, inout SampleGenerator sg, out LightSample ls)
    {
        ls = {};

        uint lightType;
        float selectionPdf;
        if (!selectLightType(lightType, selectionPdf, sg)) return false;

        bool valid = false;
        if (kUseEnvLight && lightType == (uint)LightSampleType::EnvMap)
        {
            valid = generateEnvMapSample(vertex, sg, ls);
        }
        if (kUseEmissiveLights && lightType == (uint)LightSampleType::Emissive)
        {
            // Emissive light samplers have an option to exclusively sample the upper hemisphere.
            bool upperHemisphere = sampleUpperHemisphere && !sampleLowerHemisphere;

            {
                valid = generateEmissiveSample(vertex, upperHemisphere, sg, ls);
            }
        }
        if (kUseAnalyticLights && lightType == (uint)LightSampleType::Analytic)
        {
            valid = generateAnalyticLightSample(vertex, sg, ls);
        }
        if (!valid) return false;

        // Reject samples in non-requested hemispheres.
        float cosTheta = dot(vertex.normal, ls.dir);
        // Flip the face normal to point in the same hemisphere as the shading normal.
        float3 faceNormal = sign(dot(vertex.normal, vertex.faceNormal)) * vertex.faceNormal;
        float cosThetaFace = dot(faceNormal, ls.dir);
        if (!sampleUpperHemisphere && (max(cosTheta, cosThetaFace) >= -kMinCosTheta)) return false;
        if (!sampleLowerHemisphere && (min(cosTheta, cosThetaFace) <= kMinCosTheta)) return false;

        // Account for light type selection.
        ls.lightType = lightType;
        ls.pdf *= selectionPdf;
        ls.Li /= selectionPdf;

        return true;
    }

    void skipLightSampleRandomNumbers(inout SampleGenerator sg)
    {
        uint lightType;
        float selectionPdf;
        if (!selectLightType(lightType, selectionPdf, sg)) return;

        bool valid = false;
        if (kUseEnvLight && lightType == (uint)LightSampleType::EnvMap)
        {
            if (!kUseEnvLight) valid = false;
            else sampleNext2D(sg);
        }
        if (kUseEmissiveLights && lightType == (uint)LightSampleType::Emissive)
        {
            if (!kUseEmissiveLights) valid = false;
            else emissiveSampler.skipRandomNumber(sg);
        }
        if (kUseAnalyticLights && lightType == (uint)LightSampleType::Analytic)
        {
            analyticLightSampleSkipRandomNumber(sg);
        }
    }

    /** Trace active path to find the next path vertex.
        \param[in,out] path The path state.
    */
    void nextVertex(inout PathState path)
    {
        // Setup ray.
        RayDesc rayDesc = path.getScatterRay();
        Ray ray = Ray(rayDesc.Origin, rayDesc.Direction, rayDesc.TMin, rayDesc.TMax);

        logTraceRay(PixelStatsRayType::ClosestHit);
        float hitT;
        SceneRayQuery<kUseAlphaTest> sceneRayQuery;
        HitInfo hit = sceneRayQuery.traceRay(ray, hitT, RAY_FLAG_NONE, 0xff);
        if (hit.isValid())
        {
            // Store hit info.
            path.setHit(hit);
            path.length++;
            path.sceneLength += float16_t(hitT);
        }
        else
        {
            path.clearHit();
            path.sceneLength = float16_t(kNRDInvalidPathLength);
        }
    }

    /** Trace a visibility ray to evaluate light visibility.
        \param[in] ray Visibility ray.
        \return true if the light is visible, false if occluded.
    */
    bool traceVisibilityRay(const Ray ray)
    {
        logTraceRay(PixelStatsRayType::Visibility);
        SceneRayQuery<kUseAlphaTest> sceneRayQuery;
        return sceneRayQuery.traceVisibilityRay(ray, RAY_FLAG_NONE, 0xff);
    }

    /** Handle scattering in homogeneous volumes.
    \return Returns true if a scattering event took place.
*/
    bool handleHomogeneousVolumeExtinction(inout PathState path, const ShadingData sd)
    {
        if (!path.interiorList.isEmpty())
        {
            const uint materialID = path.interiorList.getTopMaterialID();
            let material = gScene.materials.getMaterial(materialID);
            let vp = material.getHomogeneousVolumeProperties(gScene.materials, materialID);
            const float surfaceDistance = length(path.origin - sd.posW);

            // our implementation doesn't support volume scattering
            {
                // Handle volume extinction.
                updatePathThroughput(path, HomogeneousVolumeSampler::evalTransmittance(vp, surfaceDistance));
            }
        }

        return false;
    }


    /** Handle hits on dielectrics.
        \return True if this is an valid intersection, false if it is rejected.
    */
    bool handleNestedDielectrics(inout ShadingData sd, inout PathState path)
    {
        // Compute relative index of refraction at interface.
        // [Falcor 8] sd.eta (relative IoR) replaced by sd.IoR (outside medium IoR).
        sd.IoR = computeOutsideIoR(path.interiorList, sd.materialID, sd.frontFacing);

        // Check for false intersections.
        uint nestedPriority = sd.mtl.getNestedPriority();
        if (!path.interiorList.isTrueIntersection(nestedPriority))
        {
            if (path.rejectedHits < kMaxRejectedHits)
            {
                path.rejectedHits++;
                path.interiorList.handleIntersection(sd.materialID, nestedPriority, sd.frontFacing);
                path.origin = sd.computeRayOrigin(false);
                path.length--;
            }
            else
            {
                path.terminate();
            }
            return false;
        }

        // Limit specular transmission paths.
        // [Falcor 8] sd.specularTransmission removed; check lobe types instead.
        if (kLimitTransmission && (getBSDFLobes(sd) & (uint)LobeType::Transmission) != 0)
        {
            const uint transmissionBounces = path.getBounces(BounceType::Transmission);
            if (transmissionBounces >= kMaxTransmissionReflectionDepth) sd.mtl.setActiveLobes((uint)LobeType::All & ~((uint)LobeType::DeltaReflection | (uint)LobeType::SpecularReflection));
            if (transmissionBounces >= kMaxTransmissionRefractionDepth) sd.IoR = 1.f;
        }

        return true;
    }

    /** Apply russian roulette to terminate paths early.
        \param[in,out] path Path.
        \return Returns true if path was terminated.
    */
    bool terminatePathByRussianRoulette(inout PathState path)
    {
        // Lin 2026 §6.2.4: RR at initial sample only, never during replay
        // (replay must reproduce the path deterministically).
        if (path.enableRandomReplay) return false;

        const float rrVal = luminance(path.getCurrentThp());
        const float prob = max(0.f, 1.f - rrVal);
        if (sampleNext1D(path.sg) < prob)
        {
            path.terminate();
            return true;
        }

        path.russianRoulettePdf *= 1.f - prob;

        return false;
    }


    void generateReplayPrimaryScatterRay(inout PathState path, ShadingData sd, float3 dir = 0.f)
    {
        // Generate the next path segment or terminate.
        bool valid = true;

        if (all(dir == 0.f))
        {
            valid = generateScatterRay(sd, path);
        }
        else // generate with given direction
        {
            valid = generateScatterRayGivenDirection(sd, dir, path);
        }

        if (!valid)
        {
            path.terminate();
        }
        else
        {
            path.isLastVertexClassifiedAsRough =
                kSeparatePathBSDF ? (!path.isSpecularBounce() || getRoughness(sd) > params.specularRoughnessThreshold) : classifyAsRough(sd, params.specularRoughnessThreshold);
        }
    }

    /** Pure helper: evaluate the MIS weight + lightPdf for an emissive surface hit.

        Mirrors `Falcor/Source/RenderPasses/PathTracer/PathTracer.slang::evalEmissiveMIS`,
        with a dqlin-specific extension: also returns `lightPdf` as out-param
        (used by `pathBuilder.markEscapeVertexAsRcVertex` in handleHit).

        Maintenance contract: when the upstream Falcor 8 helper changes, port
        the diff here. Note: dqlin uses `sd.frontFacing ? sd.faceN : -sd.faceN`
        which is equivalent to Falcor 8's `sd.getOrientedFaceNormal()`.

        @return    misWeight (1.f when no emissive-NEE-MIS combination applies).
    */
    float evalEmissiveMIS(in const PathState path, in const ShadingData sd, bool isPrimaryHit, bool isLightSamplable, bool isTriangleHit, out float lightPdf)
    {
        lightPdf = 0.f;
        if (!(kUseEmissiveLights && kUseNEE && kUseMIS && !isPrimaryHit && path.isLightSampled() && isLightSamplable))
            return 1.f;

        // Prepare hit point struct with data needed for emissive light PDF evaluation.
        TriangleHit triangleHit = path.hit.getTriangleHit();
        TriangleLightHit hit;
        hit.triangleIndex = gScene.lightCollection.getTriangleIndex(triangleHit.instanceID, triangleHit.primitiveIndex);
        hit.posW = sd.posW;
        hit.normalW = sd.frontFacing ? sd.faceN : -sd.faceN;

        // Evaluate PDF at the hit, had it been generated with light sampling.
        bool upperHemisphere = path.isLightSampledUpper() && !path.isLightSampledLower();
        lightPdf = getEmissiveSelectionProbability() * emissiveSampler.evalPdf(path.origin, path.normal, upperHemisphere, hit);

        // Compute MIS weight by combining this with BRDF sampling.
        // Note we can assume path.pdf > 0.f since we shouldn't have got here otherwise.
        return evalMIS(1, path.pdf, 1, lightPdf);
    }

    /** Handle the case when a scatter ray hits the scene.
        After handling the hit, a new scatter ray is generated or the path is terminated.
        \param[in,out] path The path state.
    */
    void handleHit(inout PathState path)
    {
        // Upon hit:
        // - Load vertex/material data
        // - Compute volume absorption
        // - Compute MIS weight if path.length > 0 and emissive hit
        // - Add emitted radiance
        // - Sample light(s) using shadow rays
        // - Sample scatter ray or terminate

        TriangleHit th = path.hit.getTriangleHit();

        bool isCurveHit = path.hit.getType() == HitType::Curve;

        // Load vertex/material attributes. This is a long latency operation.
        ShadingData sd;

        if (kPrimaryLodMode == TexLODMode::RayDiffs && path.length == 0 && path.hit.getType() == HitType::Triangle)
        {
            // Filtered lookups at primary hit
            float2 ddx, ddy;
            computeDerivativesAtPrimaryTriangleHit(path.hit.getTriangleHit(), path.getPixel(), params.frameDim, ddx, ddy);
            sd = loadShadingDataFootprint(path.hit, -path.dir, true, ddx, ddy);
        }
        else
        {
            float lod = path.length > 0 ? params.lodBias : 0.f;
            sd = loadShadingData(path.hit, -path.dir, path.length == 0, lod);
        }

        // Reject false hits in nested dielectrics.

        if (handleHomogeneousVolumeExtinction(path, sd)) return;

        if (!handleNestedDielectrics(sd, path)) return;

        logPathVertex();

        // [Falcor 8] Emission is now in BSDFProperties, not ShadingData.
        float3 emission = getEmission(sd);

        // Optionally disable emissive lights inside volumes.
        if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) emission = float3(0.f);

        // Disable specular lobes if caustics are disabled and path already contains a diffuse vertex.
        if (kDisableCaustics && path.getBounces(BounceType::Diffuse) > 0 && getRoughness(sd) <= params.specularRoughnessThreshold)
        {
            sd.mtl.setActiveLobes((uint)LobeType::Diffuse);
        }

        // Check if the scatter event is samplable by the light sampling technique.
        const bool isLightSamplable = path.isLightSamplable();

        // Check if this is the primary hit.
        const bool isPrimaryHit = path.length == 0;

        // Lin 2026 §4 primary-hit ray-cone footprint: R_pri² = ||x0-x1||² · cos(θ) / (4π).
        // Consumed at reconnection-vertex selection sites.
        if (isPrimaryHit)
        {
            float3 x0 = path.origin;
            float3 x1 = sd.posW;
            float dist2 = dot(x1 - x0, x1 - x0);
            float cosTheta = abs(dot(sd.faceN, path.dir));
            path.pathPrimaryFootprint2 = dist2 * cosTheta * (1.f / (4.f * 3.14159265f));
        }

        // Add emitted radiance.
        // The primary hit is always included, secondary hits only if emissive lights are enabled and the full light contribution hasn't been sampled elsewhere.
        bool computeEmissive = isPrimaryHit || kUseEmissiveLights && (!kUseNEE || kUseMIS || !path.isLightSampled() || !isLightSamplable);

        // Disable all constributions to direct illumination if requested. (but we need LDeltaDirect which cannot be sampled by ReSTIR DI)
        if (kDisableDirectIllumination && path.length == 1 && isLightSamplable) computeEmissive = false;

        if (path.length == 1 && !path.isTransmission() && !path.isDelta()) computeEmissive = false;

        // daqi: when doing random number replay, we will terminate the path when the length reaches the base path length and 
        // when the path types match. In this case, if the base path is a escaped path (as opposed to an NEE path), we should terminate when we 
        // find that offset path can also be an escaped path
        bool terminateRandomReplayForEscape = path.enableRandomReplay && path.length - 1 == path.randomReplayLength && path.randomReplayIsEscaped && path.randomReplayLength >= 1;

        float3 attenuatedEmission = 0.f;

        if (computeEmissive && any(emission > 0.f))
        {
            float lightPdf = 0.f;
            float misWeight = evalEmissiveMIS(path, sd, isPrimaryHit, isLightSamplable, /*isTriangleHit=*/true, lightPdf);
            float3 Lr = 0.f;

            // Accumulate emitted radiance weighted by path throughput and MIS weight.
            if (!kDisableDirectIllumination || !isPrimaryHit || !isLightSamplable)
                Lr = path.getCurrentThp() * emission * misWeight;

            attenuatedEmission = path.getCurrentThp() * emission; //only used for primary hit

            // daqi: Since ScreenSpaceReSTIR cannot handle transmission and delta reflection, we must include the contribution in the color buffer 
            if (!path.enableRandomReplay || terminateRandomReplayForEscape)
            {
                if (!kDisableDirectIllumination || path.length > 1) path.L += Lr;
                // will change this to path.IsDelta() if ScreenSpaceReSTIR can handle transmission
                if (!isLightSamplable && path.length == 1) path.LDeltaDirect += Lr;
            }

            // daqi: here we are adding the path terminated with an escaped vertex
            if ((!path.enableRandomReplay || terminateRandomReplayForEscape) && PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
            {
#if BPR
                if (path.length - 1 > path.pathBuilder.rcVertexLength)
                {
                    path.rcVertexPathTreeIrradiance += path.thp * emission * misWeight;
                }
                bool selectedCurrentPath = path.pathBuilder.addEscapeVertex(params, max(0, path.length - 1), path.dir, Lr,
                    path.length - 1 == path.pathBuilder.rcVertexLength ? path.thp * emission * misWeight : path.rcVertexPathTreeIrradiance,
                    path.useHybridShift, path.russianRoulettePdf, misWeight, lightPdf, (uint)LightSampleType::Emissive, path.pathReservoir, path.enableRandomReplay);
#else
                bool selectedCurrentPath = path.pathBuilder.addEscapeVertex(params, max(0, path.length - 1), path.dir, Lr, path.thp * emission * misWeight,
                    path.useHybridShift, path.russianRoulettePdf, misWeight, lightPdf, (uint)LightSampleType::Emissive, path.pathReservoir, path.enableRandomReplay);
#endif

                // daqi: if current escaped vertex has path.length >= 2, then it can be used as a rcVertex
                if (selectedCurrentPath && path.useHybridShift && path.length >= 2 && path.length < path.pathBuilder.rcVertexLength)
                {
                    // Lin 2026 §4 footprint criterion.
                    float3 dispR = sd.posW - path.origin;
                    float dist2R = dot(dispR, dispR);
                    float cosR = abs(dot(sd.faceN, path.dir));
                    float recipPG = (path.prevScatterPdf > 0.f && cosR > 1e-8f) ? dist2R / (path.prevScatterPdf * cosR) : 1e30f;
                    bool isFarField = recipPG >= 0.02f * path.pathPrimaryFootprint2;
                    bool isLastVertexAcceptableForRcPrev = path.isLastVertexClassifiedAsRough;

                    if (!((params.localStrategyType & (uint)LocalStrategy::DistanceCondition) != 0 && !isFarField || (params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0 && !isLastVertexAcceptableForRcPrev))
                    {
                        if (path.isReplayForHybridShift) // non-invertible case
                        {
                            path.L = 0.f;
                        }
                        else
                        {
                            // we found an RC vertex!
                            // set rcVertexLength to current length (this will make rcVertexLength = reseroivr.pathLength + 1)
                            float3 disp = path.origin - sd.posW;
                            float geometryFactor = abs(dot(sd.faceN, sd.V)) / dot(disp, disp);

                            path.pathBuilder.markEscapeVertexAsRcVertex(params, path.length, path.pathReservoir, path.hit, path.isDelta(), path.isTransmission(), path.isSpecularBounce(), lightPdf, (uint)LightSampleType::Emissive, emission, float3(0.f), path.prevScatterPdf, geometryFactor);
                        }
                    }
                }
            }
        }

        // Terminate after scatter ray on last vertex has been processed.
        if (hasFinishedSurfaceBounces(path) || terminateRandomReplayForEscape)
        {
            path.terminate();
            return;
        }

        // daqi: save as previous path origin to compute distance between vertices
        float3 prevPathOrigin = path.origin;

        // Compute origin for rays traced from this path vertex.
        path.origin = sd.computeRayOrigin();

        // Determine if BSDF supports sampling with next-event estimation.
        // The available lobes depend on the material.
        uint lobes = getBSDFLobes(sd);

        bool supportsNEE = (lobes & (uint)LobeType::NonDelta) != 0;

        // Check if we should apply NEE.
        const bool applyNEE = kUseNEE && supportsNEE;

        // daqi: we don't use the integrated ScreenSpaceReSTIR as inlinepathtracer does, instead, we call ScreenSpaceReSTIRPass
        // therefore, functions with applyScreenSpaceReSTIR as condition are removed
        // Check if sample from screen space ReSTIR should be applied instead of NEE.
        //const bool applyScreenSpaceReSTIR = kUseScreenSpaceReSTIR && isPrimaryHit && !isVolumeHit && supportsNEE;

        // Check if lights should be sampled.
        bool sampleLights = applyNEE;

        // daqi: when doing random number replay, we will terminate the path when the length reaches the base path length and 
        // when the path types match. In this case, if the base path is a NEE path (as opposed to an escaped path), we should terminate when we 
        // find that offset path can also be an NEE path
        bool terminateRandomReplayForNEE = path.enableRandomReplay && path.length == path.randomReplayLength && path.randomReplayIsNEE;

        bool is_rcVertex = false;

        // Lin 2026 §4 footprint criterion.
        float3 dispRC = sd.posW - prevPathOrigin;
        float dist2RC = dot(dispRC, dispRC);
        float invDistRC = rsqrt(max(dist2RC, 1e-20f));
        float3 dirRC = dispRC * invDistRC;
        float cosRC = abs(dot(sd.faceN, dirRC));
        float recipPG_rc = (path.prevScatterPdf > 0.f && cosRC > 1e-8f) ? dist2RC / (path.prevScatterPdf * cosRC) : 1e30f;
        bool isFarField = recipPG_rc >= 0.02f * path.pathPrimaryFootprint2;
        bool isCurrentVertexClassifiedAsRough =
            kSeparatePathBSDF ? hasRoughComponent(sd, params.specularRoughnessThreshold) : classifyAsRough(sd, params.specularRoughnessThreshold);
        bool isLastVertexAcceptableForRcPrev = path.isLastVertexClassifiedAsRough;

        // daqi: if we are not doing a hybrid shift replay, we should check if current vertex satisfy the condition to be used as a rcVertex
        if (!path.isReplayForHybridShift && PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
        {
            bool canConnect = (path.length >= 1 && path.length < path.pathBuilder.rcVertexLength &&
                (!((params.localStrategyType & (uint)LocalStrategy::DistanceCondition) != 0 && !isFarField ||
                        (params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0 && !(isCurrentVertexClassifiedAsRough && isLastVertexAcceptableForRcPrev))));

            if (!path.useHybridShift && path.length == 1 || path.useHybridShift && canConnect)
            {
                is_rcVertex = true;
                path.pathBuilder.rcVertexHit.initFromHitInfo(path.hit);
                // daqi: save the scatter PDF as cachedJacobian
                path.pathBuilder.cachedJacobian.x = path.prevScatterPdf;
                path.pathBuilder.pathFlags.insertIsDeltaEvent(path.isDelta(), true);
                path.pathBuilder.pathFlags.insertIsTransmissionEvent(path.isTransmission(), true);
                if (kSeparatePathBSDF)
                    path.pathBuilder.pathFlags.insertIsSpecularBounce(path.isSpecularBounce(), true);

                float3 disp = prevPathOrigin - sd.posW;

                // daqi: save geometry term as part of cachedJacobian
                path.pathBuilder.cachedJacobian.z = abs(dot(sd.faceN, sd.V)) / dot(disp, disp);

                // daqi: save the current path length as the rcVertex length
                if (canConnect || !path.useHybridShift)
                {
                    path.pathBuilder.rcVertexLength = path.length;
                }
            }
        }
        else if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
        {
            bool invertible = true;
            bool shouldTerminate = false;

            // daqi: check situation where invertibility is violated
            if (path.length >= 1 && path.length <= path.pathBuilder.rcVertexLength - 1)
            {
                if (kSeparatePathBSDF)
                {
                    if ((params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0)
                    {
                        // method 2
                        //non-invertible if this bounce is an NEE bounce for the base path but the current vertex is not connectible in base path but is connectible in offset path
                        if (terminateRandomReplayForNEE && isCurrentVertexClassifiedAsRough && isLastVertexAcceptableForRcPrev) invertible = false;
                        //non-invertible because current vertex will be assigned as a diffuse bounce by connecting to the reconnection vertex
                        if (path.length == path.pathBuilder.rcVertexLength - 1 && isLastVertexAcceptableForRcPrev) invertible = false;

                        if ((params.localStrategyType & (uint)LocalStrategy::DistanceCondition) != 0 && !isFarField) invertible = true;
                    }
                    else
                    {
                        if ((params.localStrategyType & (uint)LocalStrategy::DistanceCondition) != 0 && isFarField) invertible = false;
                    }
                }
                else
                {
                    if (!((params.localStrategyType & (uint)LocalStrategy::DistanceCondition) != 0 && !isFarField ||
                        (params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0 && !(/*supportsNEE &&*/ isCurrentVertexClassifiedAsRough && isLastVertexAcceptableForRcPrev)))
                        invertible = false;
                }
            }

            // daqi: if next vertex is rcVertex and the shift is still invertible, then we should terminate
            if (path.length == path.pathBuilder.rcVertexLength - 1 && invertible)
            {
                // not possible to generate a diffuse bounce
                if ((params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0 &&
                        (kSeparatePathBSDF && (path.pathBuilder.pathFlags.decodeIsSpecularBounce(true) ? getRoughness(sd) <= params.specularRoughnessThreshold : !hasRoughComponent(sd, 1.f)) ||
                        !kSeparatePathBSDF && !isCurrentVertexClassifiedAsRough))
                {
                    // daqi: invalidate the shift
                    invertible = false;
                }
                // daqi: near field rejection case is checked in computeShiftedIntegrandReconnection in shift.slang
                else
                {
                    shouldTerminate = true;
                }
            }

            if (invertible)
            {
                // daqi: if it is invertible and we should terminate, save the hit information to set up a reconnection
                if (shouldTerminate)
                {
                    path.rcPrevVertexHit = path.hit;
                    path.rcPrevVertexWo = sd.V;
                    path.terminate();
                }
            }
            else //daqi: if the shift is not invertible, we should mark the case, which causes the shift to terminate when it goes back to shift.slang
            {
                invalidateAndTerminateReplayPath(path);
            }

            if (!path.isActive()) return;
        }

        path.setLightSampled(false, false);

        // daqi: if we are doing random number replay, we should only sample the light if we are about to terminate
        if (!(kDisableDirectIllumination && isPrimaryHit))
        {
            // generate kNEESamples light samples
            if (sampleLights && (!path.enableRandomReplay || terminateRandomReplayForNEE))
            {
                // cache (NEE sampling) seed for temporal validation (only possible for non early direction reuse since it uses the cachedRandomSeed slot)
                if (path.length == path.pathBuilder.rcVertexLength)
                {
                    path.pathBuilder.cachedRandomSeed = path.sg.rng.state;
                }

                LightSample ls;
                bool validSample = true;
                {
                    // Setup path vertex.
                    PathVertex vertex = PathVertex.create(/*path.getVertexIndex()*/ path.length + 1, sd.posW, sd.frame.N, sd.faceN);

                    // Determine if upper/lower hemispheres need to be sampled.
                    bool sampleUpperHemisphere = ((lobes & (uint)LobeType::NonDeltaReflection) != 0);
                    if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) sampleUpperHemisphere = false;
                    bool sampleLowerHemisphere = ((lobes & (uint)LobeType::NonDeltaTransmission) != 0);

                    // Sample a light.

                    validSample = generateLightSample(vertex, sampleUpperHemisphere, sampleLowerHemisphere, path.sg, ls);

                    path.setLightSampled(sampleUpperHemisphere, sampleLowerHemisphere);
                }

                if (validSample)
                {
                    // Apply MIS weight.
                    float misWeight = 1.f;
                    float scatterPdf = 0.f;

                    if (kUseMIS && ls.lightType != (uint)LightSampleType::Analytic)
                    {
                        scatterPdf = evalPdfBSDF(sd, ls.dir);

                        misWeight *= evalMIS(1, ls.pdf, 1, scatterPdf);
                    }
                    ls.Li *= misWeight;

                    float3 weight = evalBSDFCosine(sd, ls.dir);

                    float3 Lr = weight * ls.Li * path.getCurrentThp();

                    if (any(Lr > 0.f))
                    {
                        const Ray ray = ls.getVisibilityRay();
                        bool visible = traceVisibilityRay(ray);
                        if (visible)
                        {
                            if (!path.enableRandomReplay || terminateRandomReplayForNEE)
                                path.L += Lr;

                            if (ls.lightType == (uint)LightSampleType::Analytic && ls.pdf == 0.f)
                            {
                                ls.pdf = getAnalyicSelectionProbability(); // analytic light doesn't have a solid angle PDF.
                            }

                            // daqi: here we are adding the path terminated with an NEE event
                            // if we have enabled random replay, we know that we are going to use this path

                            if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
                            {
                                if (is_rcVertex)
                                {
                                    weight = 1.f;
                                }
#if BPR
                                if (!is_rcVertex)
                                {
                                    path.rcVertexPathTreeIrradiance += weight * ls.Li * path.thp;
                                }

                                // Lin 2026 §6.2.3 force-NEE plumbing:
                                //   lightLeThp     = Le × thp (no BSDF×cos factor); recovers Le by
                                //                    undoing the `ls.Li *= misWeight` folded earlier:
                                //                    ls.Li × ls.pdf / misWeight = Le.
                                //   forceNeeJacob  = (scatterPdf_at_primary, 0, G_src) for the source's
                                //                    cachedJacobian. scatterPdf is the BSDF pdf at primary
                                //                    for direction ls.dir; G_src = cos(N_light, -ls.dir) / dist²
                                //                    (only meaningful for Emissive — others fall through to
                                //                    existing random-replay shift via the rcVertexHit-invalid
                                //                    gate in PathBuilder).
                                float3 lightLeThp = ls.Li * ls.pdf / max(misWeight, 1e-30f) * path.thp;
                                float forceNeeScatterPdf = (scatterPdf > 0.f) ? scatterPdf : evalPdfBSDF(sd, ls.dir);
                                float forceNeeCosLight = max(dot(ls.lightNormalW, -ls.dir), 0.f);
                                float forceNeeGsrc = (ls.distance > 1e-6f) ? forceNeeCosLight / (ls.distance * ls.distance) : 0.f;
                                float3 forceNeeJacob = float3(forceNeeScatterPdf, 0.f, forceNeeGsrc);
                                bool selected = path.pathBuilder.addNeeVertex(params, path.length, ls.dir, Lr,
                                    is_rcVertex ? weight * ls.Li * path.thp : path.rcVertexPathTreeIrradiance, path.useHybridShift,
                                    path.russianRoulettePdf, misWeight, ls.pdf, ls.lightType, path.pathReservoir, path.enableRandomReplay,
                                    ls.packedHit, lightLeThp, forceNeeJacob);
#else
                                float3 lightLeThp = ls.Li * ls.pdf / max(misWeight, 1e-30f) * path.thp;
                                float forceNeeScatterPdf = (scatterPdf > 0.f) ? scatterPdf : evalPdfBSDF(sd, ls.dir);
                                float forceNeeCosLight = max(dot(ls.lightNormalW, -ls.dir), 0.f);
                                float forceNeeGsrc = (ls.distance > 1e-6f) ? forceNeeCosLight / (ls.distance * ls.distance) : 0.f;
                                float3 forceNeeJacob = float3(forceNeeScatterPdf, 0.f, forceNeeGsrc);
                                bool selected = path.pathBuilder.addNeeVertex(params, path.length, ls.dir, Lr, weight * ls.Li * path.thp, path.useHybridShift,
                                    path.russianRoulettePdf, misWeight, ls.pdf, ls.lightType, path.pathReservoir, path.enableRandomReplay,
                                    ls.packedHit, lightLeThp, forceNeeJacob);
#endif
                            }
                        }
                    }
                }
            }
            else
                // daqi: for random number replay, we should skip the random numbers for NEE if we should not terminate on current bounce
            {
                if (path.enableRandomReplay && sampleLights)
                {
                    bool sampleUpperHemisphere = ((lobes & (uint)LobeType::NonDeltaReflection) != 0);
                    if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) sampleUpperHemisphere = false;
                    bool sampleLowerHemisphere = ((lobes & (uint)LobeType::NonDeltaTransmission) != 0);
                    path.setLightSampled(sampleUpperHemisphere, sampleLowerHemisphere);
                }

                skipLightSampleRandomNumbers(path.sg);
            }
        }

        // daqi: terminate the path if the bounce of random replay reaches the desired bounce and the base path is an NEE path
        if (terminateRandomReplayForNEE)
        {
            path.terminate();
            return;
        }

        // Russian roulette to terminate paths early.
        // TODO: check if this is handled correctly in ReSTIR PT
        if (kUseRussianRoulette && path.length >= 1)
        {
            if (path.enableRandomReplay)
            {
                sampleNext1D(path.sg);
            }
            else
            {
                if (terminatePathByRussianRoulette(path)) return;
            }
        }

        // Temporary keep path throughput from before the scatter event.
        float3 prevThp = path.getCurrentThp();

        if (path.length == 0)
        {
            // daqi: save current random seed, this is required to do random number replay to construct a path
            path.pathReservoir.initRandomSeed = path.sg.rng.state;
        }

        // Generate the next path segment or terminate.
        bool valid = generateScatterRay(sd, path);

        // forbid current vertex being rcVertex
        if (kSeparatePathBSDF && (params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0)
        {
            bool seenAsConnectible = !path.isSpecularBounce() || getRoughness(sd) > params.specularRoughnessThreshold;

            if (path.isReplayForHybridShift && seenAsConnectible && isLastVertexAcceptableForRcPrev && path.length >= 1)
            {
                // check if near field rejection is satisfied
                if (isFarField || (params.localStrategyType & (uint)LocalStrategy::DistanceCondition) == 0)
                {
                    // non-invertible
                    invalidateAndTerminateReplayPath(path);
                }
            }
            else if (!path.isReplayForHybridShift && path.useHybridShift && !seenAsConnectible)
            {
                if (is_rcVertex)
                {
                    is_rcVertex = false; 
                    path.pathBuilder.rcVertexLength = kMaximumPathLength; // reset
                }
            }
            if (path.useHybridShift) isCurrentVertexClassifiedAsRough = seenAsConnectible;
        }

        // cache seed for temporal validation (only possible for non early direction reuse since it uses the cachedRandomSeed slot)
        if (path.length == path.pathBuilder.rcVertexLength)
        {
            path.pathBuilder.cachedRandomSeed = path.sg.rng.state;
        }

        // daqi: save the incoming direction on rcVertex
        if (is_rcVertex && valid && (path.length <= 1 || BPR == 0))
        {
            path.pathBuilder.rcVertexWi[0] = path.dir;
        }

        path.isLastVertexClassifiedAsRough = isCurrentVertexClassifiedAsRough;

        if (kOutputNRDData && !path.enableRandomReplay)
        {
            const uint2 pixel = path.getPixel();
            // [Falcor 8] Obtain BSDFProperties for NRD demodulation.
            let lod = ExplicitLodTextureSampler(0.f);
            let mi = gScene.materials.getMaterialInstance(sd, lod);
            let bsdfProperties = mi.getProperties(sd);

            if (gSppId == 0)
            {
                setNRDPrimaryHitEmission(outputNRD, kUseNRDDemodulation, path, pixel, isPrimaryHit, attenuatedEmission);
                setNRDPrimaryHitReflectance(outputNRD, kUseNRDDemodulation, path, pixel, isPrimaryHit, sd, bsdfProperties);
            }

            setNRDSampleHitDist(path); // this will be overriden if ReSTIR is done
            setNRDSampleEmission(kUseNRDDemodulation, path, isPrimaryHit, attenuatedEmission); // this should be the same for every sample (unless in volume rendering)
            setNRDSampleReflectance(kUseNRDDemodulation, path, isPrimaryHit, sd, bsdfProperties); // this will be overriden in ReSTIR mode
        }

        if (!path.isActive()) return;

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

        Mirrors Falcor 8 PathTracer's `evalEnvAtMiss`: pure (no path/output side
        effects), so the env-eval logic isn't duplicated inline in handleMiss.
        Output `lightPdf` is a dqlin extension used by the path-reuse escape-
        vertex bookkeeping below.

        Maintenance contract: this mirrors
        `Falcor/Source/RenderPasses/PathTracer/PathTracer.slang::evalEnvAtMiss`.
        When that helper changes upstream, port the diff here. dqlin-specific
        deviations are deliberate and called out:
          - `kDisableDirectIllumination && path.length == 0` gate (instead of
            Falcor 8's `kUseRTXDI && getVertexIndex() == 2 && !transmission &&
            !delta`).
          - `lightPdf` exposed as out-param for `pathBuilder.addEscapeVertex()`.

        @return true if the env contribution should be added.
    */
    bool evalEnvAtMiss(in const PathState path, out float3 Le, out float misWeight, out float lightPdf)
    {
        Le = float3(0.f);
        misWeight = 1.f;
        lightPdf  = 0.f;

        const bool isLightSamplable = path.isLightSamplable();
        bool computeEnv = kUseEnvLight && (!kUseNEE || kUseMIS || !path.isLightSampled() || !isLightSamplable);

        // Disable all contributions to direct illumination if requested
        // (dqlin: RTXDI feeds primary direct, ReSTIRPT handles indirect only).
        if (kDisableDirectIllumination && path.length == 0 && isLightSamplable) computeEnv = false;

        if (!computeEnv) return false;

        if (kUseNEE && kUseMIS && path.isLightSampled() && isLightSamplable)
        {
            lightPdf = getEnvMapSelectionProbability() * envMapSampler.evalPdf(path.dir);
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

        // Check if the scatter event is samplable by the light sampling technique.
        const bool isLightSamplable = path.isLightSamplable();

        float3 Le;
        float  misWeight;
        float  lightPdf;
        const bool computeEnv = evalEnvAtMiss(path, Le, misWeight, lightPdf);

        if (computeEnv)
        {
            logPathVertex();
            float3 Lr = path.getCurrentThp() * Le * misWeight;

            // daqi: when doing random number replay, we will terminate the path when the length reaches the base path length and 
            // when the path types match. In this case, if the base path is a escaped path (as opposed to an NEE path), we should terminate when we 
            // find that offset path can also be an escaped path
            bool terminateRandomReplayForEscape = path.enableRandomReplay && path.length == path.randomReplayLength && path.randomReplayIsEscaped
                && path.length >= 1;

            // daqi: Since ScreenSpaceReSTIR cannot handle transmission and delta reflection, we must include the contribution in the color buffer 
            if (!path.enableRandomReplay || terminateRandomReplayForEscape)
            {
                if (!kDisableDirectIllumination || path.length > 0) path.L += Lr;

                // will change this to path.IsDelta() if ScreenSpaceReSTIR can handle transmission
                if (!isLightSamplable && path.length == 0) path.LDeltaDirect += Lr;
            }

            // daqi: here we are adding the path terminated with an escaped vertex
            if ((!path.enableRandomReplay || terminateRandomReplayForEscape) && PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
            {
#if BPR
                if (path.length > path.pathBuilder.rcVertexLength)
                {
                    path.rcVertexPathTreeIrradiance += path.thp * Le * misWeight;
                }
                bool selectedCurrentPath = path.pathBuilder.addEscapeVertex(params, path.length, path.dir, Lr,
                    path.length == path.pathBuilder.rcVertexLength ? path.thp * Le * misWeight : path.rcVertexPathTreeIrradiance,
                    path.useHybridShift, path.russianRoulettePdf, misWeight, lightPdf, (uint)LightSampleType::EnvMap, path.pathReservoir, path.enableRandomReplay);
#else
                bool selectedCurrentPath = path.pathBuilder.addEscapeVertex(params, path.length, path.dir, Lr, path.thp * Le * misWeight,
                    path.useHybridShift, path.russianRoulettePdf, misWeight, lightPdf, (uint)LightSampleType::EnvMap, path.pathReservoir, path.enableRandomReplay);
#endif
                // daqi: if current escaped vertex has path.length >= 2, then it can be used as a rcVertex
                if (selectedCurrentPath && path.useHybridShift && path.length >= 1 && path.length + 1 < path.pathBuilder.rcVertexLength)
                {
                    bool isLastVertexAcceptableForRcPrev = path.isLastVertexClassifiedAsRough;

                    // daqi: in the case of escaped to infinitely far, we always satisfy the far field requirement
                    if (!((params.localStrategyType & (uint)LocalStrategy::RoughnessCondition) != 0 && !isLastVertexAcceptableForRcPrev))
                    {
                        if (path.isReplayForHybridShift) // non-invertible case 
                        {
                            path.L = 0.f;
                        }
                        else
                        {
                            // we found an RC vertex!
                            // set rcVertexLength to current length (this will make rcVertexLength = reseroivr.pathLength + 1)
                            HitInfo dummyHit = HitInfo();
                            path.pathBuilder.markEscapeVertexAsRcVertex(params, path.length + 1, path.pathReservoir, dummyHit, path.isDelta(), path.isTransmission(), path.isSpecularBounce(), lightPdf, (uint)LightSampleType::EnvMap, Le, path.dir, path.prevScatterPdf, 1.f);
                        }
                    }
                }
            }
        }

        if (kOutputNRDData)
        {
            setNRDSampleHitDist(path); // this will be overriden in ReSTIR mode
        }

        path.terminate();
    }

    // function to trace a path using random number replay
    float3 traceRandomReplayPath(HitInfo hit, ShadingData sd, ShadingData srcSd, Ray ray, inout PathReservoir tempPathReservoir)
    {
        PathState path;
        generateRandomReplayPath(path, hit, ray, tempPathReservoir.initRandomSeed, tempPathReservoir.pathFlags.pathLength(), tempPathReservoir.pathFlags.lastVertexNEE(), false);
        path.isReplayForHybridShift = false;

        path.origin = sd.computeRayOrigin();

        // set up the two scatter directions (or half vectors) for reuse

        generateReplayPrimaryScatterRay(path, sd);

        if (path.isActive()) nextVertex(path);

        float randomReplayProb = 1.f;

        while (path.isActive() && path.isHit())
        {
            // Handle surface hit 
            if (path.isActive())
            {
                if (path.isHit())
                {
                    handleHit(path);
                }
            }

            // Move to the next path vertex.
            if (path.isActive() && path.isHit()) nextVertex(path);
        }

        // Handle the miss and terminate path.
        if (path.isActive())
        {
            handleMiss(path);
        }

        // we should copy out the pathReservoir, as it contains information like rcVertex which will be needed for MIS
        tempPathReservoir = path.pathReservoir;

        return path.L;
    }

    float3 traceRandomReplayPathHybridSimple(HitInfo hit, ShadingData sd, Ray ray, ReSTIRPathFlags pathFlags,
        uint initRandomSeed, inout HitInfo rcPrevHit, inout float3 rcPrevHitWo)
    {
        PathState path;
        bool isRcVertexEscapedVertex = pathFlags.pathLength() + 1 == pathFlags.rcVertexLength();
        generateRandomReplayPath(path, hit, ray, initRandomSeed, pathFlags.pathLength(), pathFlags.lastVertexNEE(), isRcVertexEscapedVertex);
        path.useHybridShift = true;
        path.isReplayForHybridShift = true;
        path.pathBuilder.rcVertexLength = pathFlags.rcVertexLength();

        setDataBeforeTermination(rcPrevHit, rcPrevHitWo);

        path.origin = sd.computeRayOrigin();

        // this is also applicable for random number reuse
        path.pathBuilder.pathFlags.flags = 0;
        path.pathBuilder.pathFlags.transferSpecularBounceInformation(pathFlags);

        // set up the two scatter directions (or half vectors) for reuse

        generateReplayPrimaryScatterRay(path, sd);
        if (path.isActive()) nextVertex(path);
        else
        {
            return 0.f;
        }

        while (path.isActive() && path.isHit())
        {
            // Volume scattering is ignored
            // Handle surface hit 
            if (path.isActive())
            {
                if (path.isHit())
                {
                    handleHit(path);
                }
            }

            // Move to the next path vertex.
            if (path.isActive() && path.isHit()) nextVertex(path);
        }

        // Handle the miss and terminate path.
        if (path.isActive())
        {
            handleMiss(path);

            // non-invertible: path length doesn't match
            if (path.length != pathFlags.pathLength())
            {
                return 0.f;
            }
        }

        rcPrevHit = HitInfo();

        float3 L = 1.f;

        if (pathFlags.rcVertexLength() <= pathFlags.pathLength() || isRcVertexEscapedVertex)
        {
            rcPrevHit = path.rcPrevVertexHit;
            rcPrevHitWo = path.rcPrevVertexWo;
            L = path.getCurrentThp();
        }
        else // this branch is the case where rcVertex does not exist (or infinitely far)
        {
            L = path.L;
        }

        return L;
    }

    void traceRandomReplayGetDenoiserData(HitInfo hit, ShadingData sd, Ray ray, ReSTIRPathFlags pathFlags,
        uint initRandomSeed, inout float hitDist, inout NRDPathType pathType, inout float3 sampleReflectance)
    {
        PathState path;
        bool isRcVertexEscapedVertex = pathFlags.pathLength() + 1 == pathFlags.rcVertexLength();
        generateRandomReplayPath(path, hit, ray, initRandomSeed, pathFlags.pathLength(), pathFlags.lastVertexNEE(), isRcVertexEscapedVertex);
        path.useHybridShift = true;
        path.isReplayForHybridShift = true;
        path.pathBuilder.rcVertexLength = pathFlags.rcVertexLength();

        if (path.pathBuilder.rcVertexLength > 1)
        {
            path.origin = sd.computeRayOrigin();

            // this is also applicable for random number reuse
            path.pathBuilder.pathFlags.flags = 0;

            generateReplayPrimaryScatterRay(path, sd);
            if (path.isActive()) nextVertex(path);
            else
            {
                // this shouldn't happen! 
                return;
            }

            hitDist = float(path.sceneLength);
            if (path.isDiffusePrimaryHit()) pathType = NRDPathType::Diffuse;
            else if (path.isSpecularPrimaryHit()) pathType = NRDPathType::Specular;
            else pathType = NRDPathType::Residual;

            // [Falcor 8] Obtain BSDFProperties for NRD reflectance computation.
            {
                let lod = ExplicitLodTextureSampler(0.f);
                let mi = gScene.materials.getMaterialInstance(sd, lod);
                let bsdfProperties = mi.getProperties(sd);
                sampleReflectance = computeSampleReflectance(kUseNRDDemodulation, path.isDiffusePrimaryHit(), path.isSpecularPrimaryHit(), sd, bsdfProperties);
            }

            return;
        }
    }

    void traceTemporalUpdate(ShadingData rcPrevSd, inout PathReservoir tempPathReservoir)
    {
        int rcVertexLength = tempPathReservoir.pathFlags.rcVertexLength();
        ShadingData rcVertexSd = loadShadingDataWithPrevVertexPosition(tempPathReservoir.rcVertexHit.getHitInfo(), rcPrevSd.posW, false);
        PathState path;

        //rcVertex is NEE
        if (tempPathReservoir.pathFlags.lastVertexNEE() && tempPathReservoir.pathFlags.pathLength() == rcVertexLength)
        {
            path = {};
            path.length = (uint16_t)rcVertexLength;
            // call light sampling function
            LightSample ls;
            bool validSample = true;
            {
                uint lobes = getBSDFLobes(rcVertexSd);
                // Setup path vertex.
                PathVertex vertex = PathVertex.create(/*path.getVertexIndex()*/ path.length + 1, rcVertexSd.posW, rcVertexSd.frame.N, rcVertexSd.faceN);

                // Determine if upper/lower hemispheres need to be sampled.
                bool sampleUpperHemisphere = ((lobes & (uint)LobeType::NonDeltaReflection) != 0);
                bool sampleLowerHemisphere = ((lobes & (uint)LobeType::NonDeltaTransmission) != 0);

                path.sg = SampleGenerator(tempPathReservoir.rcRandomSeed);
                validSample = generateLightSample(vertex, sampleUpperHemisphere, sampleLowerHemisphere, path.sg, ls);
            }

            bool visible = true;
            if (validSample)
            {
                const Ray ray = ls.getVisibilityRay();
                visible = traceVisibilityRay(ray);

                if (ls.lightType == (uint)LightSampleType::Analytic && ls.pdf == 0.f)
                {
                    ls.pdf = getAnalyicSelectionProbability(); // analytic light doesn't have a solid angle PDF.
                }
            }

            if (validSample && visible)
            {
                tempPathReservoir.rcVertexWi[0] = ls.dir;
                tempPathReservoir.rcVertexIrradiance[0] = ls.Li * ls.pdf;
                tempPathReservoir.pathFlags.insertLightType(ls.lightType);
                tempPathReservoir.lightPdf = ls.pdf;
            }
            else tempPathReservoir.rcVertexIrradiance[0] = 0.f;
        }
        else
        {
            Ray emptyRay = Ray(float3(0.f), float3(0.f), 0.f, kRayTMax);

            // should always be false in this case
            bool isRcVertexEscapedVertex = false;
            generateRandomReplayPath(path, tempPathReservoir.rcVertexHit.getHitInfo(), emptyRay, tempPathReservoir.rcRandomSeed, tempPathReservoir.pathFlags.pathLength(), tempPathReservoir.pathFlags.lastVertexNEE(), isRcVertexEscapedVertex);
            path.length = (uint16_t)rcVertexLength;
            path.useHybridShift = false;
            path.isReplayForHybridShift = false;

            uint lobes = getBSDFLobes(rcVertexSd);
            bool sampleUpperHemisphere = ((lobes & (uint)LobeType::NonDeltaReflection) != 0);
            if (!kUseLightsInDielectricVolumes && path.isInsideDielectricVolume()) sampleUpperHemisphere = false;
            bool sampleLowerHemisphere = ((lobes & (uint)LobeType::NonDeltaTransmission) != 0);
            path.setLightSampled(sampleUpperHemisphere, sampleLowerHemisphere);

            // start from path length
            float3 scatterDir = tempPathReservoir.rcVertexWi[0];
            path.pathBuilder.rcVertexLength = rcVertexLength;
            path.origin = rcVertexSd.computeRayOrigin(!tempPathReservoir.pathFlags.decodeIsTransmissionEvent(false));

            path.pathBuilder.pathFlags.transferDeltaInformation(tempPathReservoir.pathFlags);
            path.pathBuilder.pathFlags.transferTransmissionInformation(tempPathReservoir.pathFlags);
            path.pathBuilder.pathFlags.transferSpecularBounceInformation(tempPathReservoir.pathFlags);
            path.pathReservoir.rcVertexIrradiance[0] = 0.f;

            generateReplayPrimaryScatterRay(path, rcVertexSd, scatterDir);
            path.sg = SampleGenerator(tempPathReservoir.rcRandomSeed);
            if (path.isActive()) nextVertex(path);

            while (path.isActive() && path.isHit())
            {
                // Volume scattering is ignored
                // Handle surface hit 
                if (path.isActive())
                {
                    if (path.isHit())
                    {
                        handleHit(path);
                    }
                }

                // Move to the next path vertex.
                if (path.isActive() && path.isHit()) nextVertex(path);
            }

            // Handle the miss and terminate path.
            if (path.isActive())
            {
                handleMiss(path);
            }

            // unlike traceRandomReplayPath(), we don't directly copy the path.pathReservoir.
            // this is because we start at path.length == 2, we can also terminate early,
            // so pathReservoir won't record enough information for a complete path reservoir
            // so we need to manually copy some members we need later
            // this cannot be replaced by pathBuilder because of escapedRcVertex not setting pathBuilder.rcVertexHit (TODO: refactor)
            tempPathReservoir.rcVertexIrradiance[0] = path.pathReservoir.rcVertexIrradiance[0];
            tempPathReservoir.lightPdf = path.pathReservoir.lightPdf;
            tempPathReservoir.pathFlags.insertLightType(path.pathReservoir.pathFlags.lightType());
        }
    }

    /** Finalize the path state before writing to the output buffer.
    */
    void finalize(inout PathState path)
    {
        path.pathBuilder.finalize(path.pathReservoir);
    }

    /** Write path contribution to output buffer.
    */
    void writeOutput(PathState path, inout PathReservoir giReservoir, int sampleId)
    {
        // Log path length.
        logPathLength(getTerminatedPathLength(path));

        const uint2 pixel = path.getPixel();

        // 3D mode wiring is currently disabled — calling gScene.getVertexData
        // (or loadShadingData) from this site triggers DXGI_DEVICE_REMOVED
        // intermittently after several frames. Likely a binding / lifetime
        // issue in the cross-pass scene-data access pattern; needs a focused
        // debug session. Until then, mode=1 falls back to pixel-keyed (no-op).
        const uint reservoirIdx = resolveReservoirOffset(pixel);

        static const uint itersPerShaderPass = PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing ? kSamplesPerPixel : kCandidateSamples;

        if (itersPerShaderPass == 1)
        {
            float3 L = 0.f;

            if (useDirectLighting) L += path.LDeltaDirect;

            if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing)
                L += path.L;
            else if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathReuse)
            {
                path.pathReservoir.weight = 1.f;
                if (isLastRound)
                {
                    float3 color = path.pathReservoir.F + path.pathReservoir.cachedJacobian;
                    if (any(isinf(color) || isnan(color))) color = 0.f;
                    L += color;
                }
            }
            else
            {
                path.pathReservoir.finalizeRIS();

                if (isLastRound)
                {
                    float3 color = path.pathReservoir.F * path.pathReservoir.weight;
                    if (any(isinf(color) || isnan(color))) color = 0.f;
                    // Instant-Radiosity-style fallback: if the ReSTIR estimate is much brighter
                    // than the vanilla PT contribution, fall back to PT (both unbiased).
                    float colorLum = luminance(color);
                    float ptLum = luminance(path.L);
                    if (colorLum > 5.f * max(ptLum, 0.01f))
                    {
                        color = path.L;  // fall back to vanilla PT
                    }
                    L += color;
                }
            }

            if (useDirectLighting && (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing || isLastRound))
            {
                L += directLighting[pixel].rgb;
            }

            if (any(isinf(L) || isnan(L))) L = 0.f;

            if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
                L /= kSamplesPerPixel;

            if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing || kSamplesPerPixel == 1 || gSppId == 0 )
                outputColor[pixel] = float4(L, 1.f);
            else
                outputColor[pixel] += float4(L, 1.f);

            if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathTracing)
            {
                // Reservoir-write magnitude safety net (1e10) + Inf/NaN guard.
                if (any(isnan(path.pathReservoir.F) || isinf(path.pathReservoir.F) || path.pathReservoir.F > 1e10f)) path.pathReservoir.F = 0.f;
                if (isnan(path.pathReservoir.weight) || isinf(path.pathReservoir.weight) || path.pathReservoir.weight < 0.f || path.pathReservoir.weight > 1e10f) path.pathReservoir.weight = 0.f;
                outputReservoirs[reservoirIdx] = path.pathReservoir;

                // Mode=1 (3D worldcell-keyed): also try to claim a cell-pool
                // slot and write the reservoir there for cross-pixel reuse.
                // The pixel-keyed write above stays as the per-pixel fallback;
                // reuse passes will read from cell pool first, fall back to
                // pixel buffer on collision miss.
                if (params.restirptAddrMode == 1u)
                {
                    const HitInfo primaryHit = HitInfo(vbuffer[pixel]);
                    if (primaryHit.isValid() && primaryHit.getType() == HitType::Triangle)
                    {
                        const TriangleHit th = primaryHit.getTriangleHit();
                        const VertexData v = gScene.getVertexData(th);
                        // Cell coords (must match Params.slang::getReservoirOffsetWorldCell).
                        const float kCellSize = max(params.sceneRadius * 0.01f, 1e-3f);
                        int3 q = int3(floor(v.posW / kCellSize));
                        uint nb = 0u;
                        float3 an = abs(v.faceNormalW);
                        if (an.x >= an.y && an.x >= an.z) nb = (v.faceNormalW.x >= 0.f) ? 0u : 1u;
                        else if (an.y >= an.z)            nb = (v.faceNormalW.y >= 0.f) ? 2u : 3u;
                        else                              nb = (v.faceNormalW.z >= 0.f) ? 4u : 5u;
                        // Slot index = same hash as getReservoirOffsetWorldCell.
                        uint h = (uint(q.x) * 73856093u) ^ (uint(q.y) * 19349663u) ^ (uint(q.z) * 83492791u) ^ (nb * 2654435761u);
                        uint stride = kScreenTileDim.x * kScreenTileDim.y;
                        uint capacity = max(params.screenTiles.x * params.screenTiles.y * stride, 1u);
                        uint slotIdx = h % capacity;
                        uint fingerprint = prCellFingerprint(q, nb);
                        if (prCellSlotClaim(pathReservoirCellPool, slotIdx, fingerprint))
                        {
                            pathReservoirCellPool[slotIdx].reservoir = path.pathReservoir;
                        }
                    }
                }
            }
        }
        else
        {
            if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing)
            {
                float3 L = 0.f;
                if (sampleId == 0)
                {
                    L = path.L / kSamplesPerPixel;
                }
                else 
                {
                    L = giReservoir.F;
                    L += path.L / kSamplesPerPixel;
                }
                if (useDirectLighting && sampleId == kSamplesPerPixel - 1) L += path.LDeltaDirect;

                if (any(isinf(L) || isnan(L))) L = 0.f;

                if (sampleId == kSamplesPerPixel - 1)
                {
                    if (useDirectLighting)
                    {
                        L += directLighting[pixel].rgb;
                        if (any(isnan(L) || isinf(L))) L = 0.f;
                    }

                    outputColor[pixel] = float4(L, 1.f);
                }
                else giReservoir.F = L;
            }
            else
            {

                if (sampleId == 0)
                {
                    giReservoir = path.pathReservoir; // we are the first one
                }
                else
                {
                    if (giReservoir.mergeInSamplePixel(path.pathReservoir, path.sg))
                    {
                        giReservoir.F = path.pathReservoir.F;
                    }
                }

                if (sampleId == kCandidateSamples - 1) // last sample
                {
                    float3 L = 0.f;
                    if (useDirectLighting) L += path.LDeltaDirect;

                    giReservoir.finalizeRIS();
                    if (isLastRound)
                    {
                        float3 color = giReservoir.F * giReservoir.weight;
                        if (any(isinf(color) || isnan(color))) color = 0.f;
                        L += color;
                    }

                    if (useDirectLighting && isLastRound)
                    {
                        L += directLighting[pixel].rgb;
                        if (any(isnan(L) || isinf(L))) L = 0.f;
                    }

                    L /= kSamplesPerPixel;

                    if (kSamplesPerPixel == 1 || gSppId == 0)
                        outputColor[pixel] = float4(L, 1.f);
                    else
                        outputColor[pixel] += float4(L, 1.f);

                    // Reservoir-write magnitude safety net (1e10) + Inf/NaN guard.
                    if (any(isnan(giReservoir.F) || isinf(giReservoir.F) || giReservoir.F > 1e10f)) giReservoir.F = 0.f;
                    if (isnan(giReservoir.weight) || isinf(giReservoir.weight) || giReservoir.weight < 0.f || giReservoir.weight > 1e10f) giReservoir.weight = 0.f;
                    outputReservoirs[reservoirIdx] = giReservoir;
                }
            }
        }

        if (kOutputNRDData && PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathTracing) 
        {
            float3 diffuseRadiance = 0.f;
            float3 specularRadiance = 0.f;
            float3 residualRadiance = 0.f;
            float hitDist = path.hitDist;

            {
                NRDPathType pathType;
                if (path.isDiffusePrimaryHit()) pathType = NRDPathType::Diffuse;
                else if (path.isSpecularPrimaryHit()) pathType = NRDPathType::Specular;
                else pathType = NRDPathType::Residual;

                float3 radiance = path.L + path.LDeltaDirect;

                if (useDirectLighting)
                {
                    radiance += directLighting[pixel].rgb;
                }

                float3 reflectance = path.sharedScatterDir;
                reflectance = max(0.04f, reflectance);
                float3 emission = path.rcPrevVertexWo;
                float3 demodulatedRadiance = max(0.f, (radiance - emission)) / reflectance;

                switch (pathType)
                {
                case NRDPathType::Diffuse:
                    diffuseRadiance += demodulatedRadiance;
                    break;
                case NRDPathType::Specular:
                    specularRadiance += demodulatedRadiance;
                    break;
                default:
                    // Do not demodulate residual.
                    residualRadiance += radiance;
                    break;
                }
            }

            const uint spp = kSamplesPerPixel;
            const float invSpp = spp > 0 ? 1.f / spp : 1.f; // Setting invSpp to 1.0 if we have no samples to avoid NaNs below.

            if (sampleId == 0)
            {
                outputNRDDiffuseRadianceHitDist[pixel] = float4(invSpp * diffuseRadiance, invSpp * hitDist);
                outputNRDSpecularRadianceHitDist[pixel] = float4(invSpp * specularRadiance, invSpp * hitDist);
                outputNRDResidualRadianceHitDist[pixel] = float4(invSpp * residualRadiance, invSpp * hitDist);
            }
            else
            {
                outputNRDDiffuseRadianceHitDist[pixel] += float4(invSpp * diffuseRadiance, invSpp * hitDist);
                outputNRDSpecularRadianceHitDist[pixel] += float4(invSpp * specularRadiance, invSpp * hitDist);
                outputNRDResidualRadianceHitDist[pixel] += float4(invSpp * residualRadiance, invSpp * hitDist);
            }
        }

    }

};

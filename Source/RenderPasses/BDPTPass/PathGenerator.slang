#include "Utils/Math/MathConstants.slangh"
#include "BitfieldMacros.slangh"
import Scene.RaytracingInline;
import Rendering.Lights.EnvMapSampler;
import Rendering.Lights.EmissiveLightSampler;
import Rendering.Lights.LightHelpers;  // analytic light sampling (sampleLight for LightData)
import Utils.Math.MathHelpers;
import Utils.Geometry.GeometryHelpers;
import Utils.Sampling.SampleGenerator;
import Utils.Color.ColorHelpers;
import Utils.Debug.PixelDebug;
import LoadShadingData;
import HashMap;
import LightVertexCache;
__exported import Params;
__exported import PathReservoir;

cbuffer CB {
    uint gRandomSeed;
    uint gSwapReservoirs;
};

// Static parameters
extension PathGenerator {
    static const bool  gUseEnvLight                   = USE_ENV_LIGHT;
    static const bool  gUseEmissiveLights             = USE_EMISSIVE_LIGHTS;
    static const bool  gUseAnalyticLights             = USE_ANALYTIC_LIGHTS;
    static const bool  gUseViewDir                    = USE_VIEW_DIR;
    static const bool  gSampleDirectLight             = USE_NEE;
    static const bool  gBidirectional                 = USE_BIDIRECTIONAL;
    static const bool  gShiftLightPathsToPixelCenters = SHIFT_LIGHT_PATHS_TO_CENTER;
    static const bool  gLightTraceOnly                = LIGHT_TRACE_ONLY;
    static const bool  gUseResampling                 = USE_RESAMPLING;
    static const bool  gUseReconnectionMIS            = USE_RECONNECTION_MIS;
    static const bool  gShiftSuffixes                 = SHIFT_SUFFIXES;
    static const bool  gUseBsdfImportanceSampling     = USE_BSDF_IMPORTANCE_SAMPLING;
    static const bool  gDebugBPT                      = DEBUG_BPT;
    static const bool  gDebugHeatmap                  = DEBUG_HEATMAP;
    static const float gMISPowerExponent              = MIS_POWER_EXPONENT;
    static const bool  gDisableCameraConnection       = DISABLE_CAMERA_CONNECTION;
    static const bool  gDisableEarlyReconnection      = DISABLE_EARLY_RECONNECTION;
    static const bool  gDisableLVC                    = DISABLE_LVC;
    static const bool  gDisableVC                     = DISABLE_VC;
}

struct LightTraceReservoir {
    PathSample path;
    float W;
};

struct PathGenerator {
    PathGeneratorParams mParams;

    EnvMapSampler        mEnvMapSampler;
    EmissiveLightSampler mEmissiveSampler;

    LightVertexCache mLightVertexCache;
    LightVertexCache        mPhotonMap;

    RWByteAddressBuffer mAtomicRadiance;
    RWTexture2D<float4> mOutputRadiance;
    RWByteAddressBuffer mOutputCounterData;

    RWStructuredBuffer<PathReservoir> mPathReservoirs0;
    RWStructuredBuffer<PathReservoir> mPathReservoirs1;
    RWStructuredBuffer<PathReservoir> mCausticReservoirs;
    HashMap<LightTraceReservoir>      mLightTraceReservoirs;
    HashMap<PathReservoir>            mCausticReservoirMap;

    Texture2D<PackedHitInfo> mVbuffer;
    Texture2D<float3>        mViewDir;
    Texture2D<float2>        mMotionVectors;

    StructuredBuffer<PathReservoir> mLastReservoirs;
    RWStructuredBuffer<PathReservoir> mLastCausticReservoirs;
    Texture2D<float3>               mLastViewDir;
    Texture2D<PackedHitInfo>        mLastVbuffer;
}
ParameterBlock<PathGenerator> gPathGenerator;

///////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////// Path vertex interface //////////////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////

struct ReflectanceEvalData {
    float3 mReflectance = 0;
    float mFwdPdfW = 0;
    float mRevPdfW = 0;
};
struct DirectionSampleData {
    float3 mDirection = 0;
    float3 mReflectance = 0;
    float  mFwdPdfW = 0;
    float  mRevPdfW = 0;
    uint   mLobeType = 0;

    bool IsLobe(const LobeType lobe) { return (mLobeType & uint(lobe)) != 0; }

    [mutating]
    void SetReflectance(const ReflectanceEvalData r) {
        mReflectance = r.mReflectance;
        mFwdPdfW = r.mFwdPdfW;
        mRevPdfW = r.mRevPdfW;
    }
};

struct PathVertex {
    PackedPathVertex  mVertex;
    ShadingData       mShadingData;
    IMaterialInstance mMaterial;

    __init(const PackedPathVertex v) {
        mVertex = v;
        if (v.IsFinite()) {
            HitInfo hit = HitInfo(v.mPackedHit);

            let lod = ExplicitLodTextureSampler(0.f);
            mShadingData = loadShadingData(hit, v.mRayOrigin, v.mRayDirection, lod);

            let hints = getMaterialInstanceHints(hit, false);
            mMaterial = gScene.materials.getMaterialInstance(mShadingData, lod, hints);
        }
    }

    PathVertex Reversed(const float3 dir) {
        PathVertex vertex;
        vertex.mVertex = mVertex;
        vertex.mVertex.mRayDirection = -vertex.mVertex.mRayDirection;

        let lod = ExplicitLodTextureSampler(0.f);

        //*
        VertexData v;
        v.posW = mShadingData.posW;
        v.normalW = mShadingData.frame.N;
        v.tangentW = float4(mShadingData.frame.T, sign(dot(mShadingData.frame.B, cross(mShadingData.frame.N, mShadingData.frame.T))));
        v.texC = mShadingData.uv;
        v.faceNormalW = mShadingData.faceN;
        v.curveRadius = mShadingData.curveRadius;
        v.coneTexLODValue = 0.f;
        // [Falcor 8] prepareShadingData no longer takes ITextureSampler.
        vertex.mShadingData = gScene.materials.prepareShadingData(v, mShadingData.materialID, dir);
        /*/
        vertex.mShadingData = mShadingData;
        vertex.mShadingData.V = dir;
        vertex.mShadingData.frontFacing = dot(vertex.mShadingData.faceN, dir) > 0.f;
        //*/

        HitInfo hit = HitInfo(mVertex.mPackedHit);

        let hints = getMaterialInstanceHints(hit, false);
        vertex.mMaterial = gScene.materials.getMaterialInstance(vertex.mShadingData, lod, hints);

        return vertex;
    }

    PackedPathVertex Pack() { return mVertex; }

    bool IsFinite() { return mVertex.IsFinite(); }

    float3 GetPosition() { return mShadingData.posW; }
    // points away from vertex
    float3 GetDirIn() { return mShadingData.V; }

    bool HasFaceNormal() { return IsFinite(); }
    float3 GetFaceNormal() { return mShadingData.getOrientedFaceNormal(); }
    float GetCosN(const float3 dir) {
        if (HasFaceNormal())
            return abs(dot(mShadingData.faceN, dir));
        else
            return 1;
    }

    bool HasLobe(const LobeType l) { return (mMaterial.getLobeTypes(mShadingData) & uint(l)) != 0; }

    bool UpperHemisphereOnly() { return HasFaceNormal() && !HasLobe(LobeType::NonDeltaTransmission); }

    float3 GetEmission() {
        if (IsFinite()) {
            if (mShadingData.frontFacing) {
                return mMaterial.getProperties(mShadingData).emission;
            } else {
                return 0;
            }
        } else {
            return gScene.envMap.eval(mVertex.mRayDirection, 0);
        }
    }

    float3 ComputeRayOrigin(const float3 dir) {
        return computeRayOrigin(mShadingData.posW, dot(dir, mShadingData.faceN) >= 0.f ? mShadingData.faceN : -mShadingData.faceN);
    }

    bool IsConnectable() {
        if (!IsFinite())
            return false;

        if (HasLobe(LobeType::Diffuse))
            return true;

        if (HasLobe(LobeType::Specular) && mMaterial.getProperties(mShadingData).roughness >= gPathGenerator.mParams.mReconnectionRoughness)
            return true;

        return false;
    }

    float GetContinuationProbability() {
        if (!IsConnectable())
            return 1.f;

        return 1.f - gPathGenerator.mParams.mTerminationProbability * mMaterial.getProperties(mShadingData).roughness;
    }

    float GetAdjointCorrection(const float3 dirOut, const bool etaCorrection = false) {
        if (!HasFaceNormal()) return 1;

        let properties = mMaterial.getProperties(mShadingData);

        float factor = 1.f;

        {
            const float cosOut = dot(GetFaceNormal(), dirOut);
            const float cosIn  = dot(GetFaceNormal(), GetDirIn());

            const float3 shadingNormal = properties.guideNormal;
            const float cosInShading  = dot(shadingNormal, GetDirIn());
            const float cosOutShading = dot(shadingNormal, dirOut);

            // Account for asymmetry in the BSDF due to the use of shading normals (Veach 5.3)
            const float num   = abs(cosInShading * cosOut);
            const float denom = abs(cosOutShading * cosIn);
            if (denom >= kMinCosTheta)
                factor *= num / denom;
        }

        if (etaCorrection) {
            // Account for asymmetry in the BSDF due to refraction (Veach 5.2)
            // [Falcor 8 TODO] BSDFProperties.eta removed; use sd.IoR-based estimate
            // or skip refraction-correction. For now: identity (eta=1). This is
            // incorrect on dielectric interfaces — caustic/rough-glass paths
            // will be slightly biased until we wire IoR through properly.
            // factor /= sqr(properties.eta);
        }

        return factor;
    }

    ReflectanceEvalData EvaluateReflectance(inout SampleGenerator sg, const float3 dirOut, const bool adjoint) {
        ReflectanceEvalData r = {};
        r.mReflectance = mMaterial.eval(mShadingData, dirOut, sg);
        if (adjoint) r.mReflectance *= GetAdjointCorrection(dirOut);

        r.mFwdPdfW = mMaterial.evalPdf(mShadingData, dirOut, gPathGenerator.gUseBsdfImportanceSampling);

        const PathVertex revVertex = Reversed(dirOut);
        r.mRevPdfW = revVertex.mMaterial.evalPdf(revVertex.mShadingData, GetDirIn(), gPathGenerator.gUseBsdfImportanceSampling);

        const float contProb = GetContinuationProbability();
        r.mRevPdfW *= contProb;
        r.mFwdPdfW *= contProb;

        return r;
    }
    DirectionSampleData SampleDirection(inout SampleGenerator sg, const bool adjoint) {
        DirectionSampleData r = {};
        BSDFSample s;
        if (!mMaterial.sample(mShadingData, sg, s, gPathGenerator.gUseBsdfImportanceSampling))
            return r;

        r.mDirection = s.wo;
        r.mReflectance = s.weight;
        r.mLobeType = s.lobeType;
        if (adjoint) r.mReflectance *= GetAdjointCorrection(r.mDirection, s.isLobe(LobeType::DeltaTransmission) || s.isLobe(LobeType::SpecularTransmission));

        r.mFwdPdfW = s.pdf;

        // cancel divide by pdf performed by material sampling.
        if (s.pdf > 0) r.mReflectance *= s.pdf;

        if (r.IsLobe(LobeType::Delta)) {
            // rev  pdf should be the same as the fwdf pdf for delta lobes
            r.mRevPdfW = r.mFwdPdfW;
        } else {
            const PathVertex revVertex = Reversed(r.mDirection);
            r.mRevPdfW = revVertex.mMaterial.evalPdf(revVertex.mShadingData, GetDirIn(), gPathGenerator.gUseBsdfImportanceSampling);

            // get unweighted BSDF
            // TODO: modify the material sampling code to return the unweighted BSDF
            r.mReflectance = EvaluateReflectance(sg, r.mDirection, adjoint).mReflectance;
        }

        const float contProb = GetContinuationProbability();
        r.mFwdPdfW *= contProb;
        r.mRevPdfW *= contProb;

        return r;
    }
};

///////////////////////////////////////////////////////////////////////////////////////////
///////////////////////////////////// Helper functions ////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////

extension PathGenerator {
    void DebugSetPixel(const uint2 id) {
        printSetPixel(id);
        #if DEBUG_HEATMAP
        gPixelDebugPixel = id;
        #endif
    }

    void IncrementCounter(const DebugCounterType type, const uint increment = 1) {
        #if DEBUG_HEATMAP
        if ((uint(type) & uint(mParams.mDebugCounter)) != 0 && all(gPixelDebugPixel < mParams.mOutputDim)) {
            const uint addr = (1 + gPixelDebugPixel.y * mParams.mOutputDim.x + gPixelDebugPixel.x) * sizeof(uint);
            uint prevValue;
            mOutputCounterData.InterlockedAdd(addr, increment, prevValue);
            uint val = prevValue + increment;
            if ((~uint(0)) - prevValue < increment) {
                // clamp on overflow
                val = (~uint(0));
                mOutputCounterData.InterlockedMax(addr, val);
            }
            mOutputCounterData.InterlockedMax(0, val);
        }
        #endif
    }

    PackedPathVertex TraceRay(const Ray ray) {
        IncrementCounter(DebugCounterType::eRays);
        // [Falcor 8] traceSceneRay returns HitInfo; UseAlphaTest is int (1=true).
        float dist;
        HitInfo hit = traceSceneRay<1>(ray, dist, 0, 0xFFFFFFFF);
        return PackedPathVertex(ray, hit, dist);
    }
    bool Occluded(const Ray ray) {
        IncrementCounter(DebugCounterType::eOcclusionRays);
        return !traceSceneVisibilityRay<true>(ray, 0, 0xFFFFFFFF);
    }

    float Mis(float a) {
        if (gMISPowerExponent == 0.f)
            return a > 0 ? 1 : 0;
        else if (gMISPowerExponent == 1.f)
            return abs(a);
        else if (gMISPowerExponent == 2.f)
            return a * a;
        else
            return pow(abs(a), gMISPowerExponent);
    }
    float Mis(float a, float b) {
        a = Mis(a);
        return SafeDivide(a, a + Mis(b));
    }

    void StableONB(const float3 n, out float3 t, out float3 b) {
        const float3 u = (1 - abs(n.y) < kMinCosTheta) ? float3(1, 0, 0) : float3(0, 1, 0);
        t = normalize(cross(n, u));
        b = normalize(cross(n, t));
    }

    // Disable MIS when we are only rendering a single technique
    bool DebugDisableMIS() {
        return (gDebugBPT && mParams.mDebugLightVertices != -1);
    }
    bool DebugDisablePath(const uint bounces, const uint lightVertices, const uint prefixBounces, const bool merged) {
        if (!gDebugBPT) return false;
        return (mParams.mDebugTotalVertices != -1 && mParams.mDebugTotalVertices != bounces + 2)
            || (mParams.mDebugLightVertices != -1 && mParams.mDebugLightVertices != lightVertices)
            || (mParams.mDebugPrefixBounces != -1 && mParams.mDebugPrefixBounces != prefixBounces);
    }

    float GetImageToSolidAngleFactor(const float3 dir, out float cosCamera) {
        cosCamera = dot(dir, normalize(gScene.camera.data.cameraW));
        const float imagePlaneDist = mParams.mOutputDim.y * (gScene.camera.data.focalLength / gScene.camera.data.frameHeight);
        const float imagePointToCameraDist = imagePlaneDist / cosCamera;
        return (imagePointToCameraDist * imagePointToCameraDist) / cosCamera;
    }
    float GetPrevImageToSolidAngleFactor(const float3 dir, out float cosCamera) {
        // [Falcor 8 TODO] CameraData.prevCameraW removed. Approximate using current
        // cameraW — correct for static cameras, biases temporal-shift weights
        // when the camera moves. Derive from CameraData.prevViewMat when needed.
        cosCamera = dot(dir, normalize(gScene.camera.data.cameraW));
        const float imagePlaneDist = mParams.mOutputDim.y * (gScene.camera.data.focalLength / gScene.camera.data.frameHeight);
        const float imagePointToCameraDist = imagePlaneDist / cosCamera;
        return (imagePointToCameraDist * imagePointToCameraDist) / cosCamera;
    }

    int2 GetPixelCoord(const float3 pos) {
        float4 clip = mul(gScene.camera.data.viewProjMatNoJitter, float4(pos, 1));
        clip.y = -clip.y;
        return int2(((clip.xy / clip.w) * .5 + .5) * mParams.mOutputDim);
    }
    int2 GetPrevPixelCoord(const float3 pos) {
        float4 clip = mul(gScene.camera.data.prevViewProjMatNoJitter, float4(pos, 1));
        clip.y = -clip.y;
        return int2(((clip.xy / clip.w) * .5 + .5) * mParams.mOutputDim);
    }

    // IO helpers

    PackedPathVertex LoadPrimaryVertex(const uint2 id) {
        if (any(id > mParams.mOutputDim))
            return {};

        Ray cameraRay = gScene.camera.computeRayPinhole(id, mParams.mOutputDim);
        if (gUseViewDir) cameraRay.dir = -mViewDir[id];
        return PackedPathVertex(cameraRay, HitInfo(mVbuffer[id]), cameraRay.tMax);
    }
    PackedPathVertex LoadPrevPrimaryVertex<let bInPrevFrame : bool>(const uint2 id) {
        if (any(id > mParams.mOutputDim))
            return {};

        // if we are tracing with the previous frame's data, then gScene.camera is last frame's camera
        // but we stil need to use mLastVbuffer and mLastViewDir
        // [Falcor 8 TODO] Camera::computeRayPinholePrevFrame removed. Fall back to
        // current-frame pinhole — correct for static cameras only.
        Ray cameraRay = gScene.camera.computeRayPinhole(id, mParams.mOutputDim);
        if (gUseViewDir) cameraRay.dir = -mLastViewDir[id];
        return PackedPathVertex(cameraRay, HitInfo(mLastVbuffer[id]), cameraRay.tMax);
    }

    PathReservoir LoadPrevReservoir(const uint2 index) {
        if (!gUseResampling) return {};
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        return mLastReservoirs[flatIndex];
    }
    PathReservoir LoadInputReservoir(const uint2 index) {
        if (!gUseResampling) return {};
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        if (gSwapReservoirs != 0)
            return mPathReservoirs1[flatIndex];
        else
            return mPathReservoirs0[flatIndex];
    }
    PathReservoir LoadOutputReservoir(const uint2 index) {
        if (!gUseResampling) return {};
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        if (gSwapReservoirs != 0)
            return mPathReservoirs0[flatIndex];
        else
            return mPathReservoirs1[flatIndex];
    }
    void StoreReservoir(const uint2 index, const PathReservoir r) {
        if (!gUseResampling) return;
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        if (gSwapReservoirs != 0)
            mPathReservoirs0[flatIndex] = r;
        else
            mPathReservoirs1[flatIndex] = r;
    }

    PathReservoir LoadPrevCausticReservoir(const uint2 index) {
        if (!gUseResampling) return {};
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        return mLastCausticReservoirs[flatIndex];
    }
    PathReservoir LoadCausticReservoir(const uint2 index) {
        if (!gUseResampling) return {};
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        return mCausticReservoirs[flatIndex];
    }
    void StoreCausticReservoir(const uint2 index, const PathReservoir r) {
        if (!gUseResampling) return;
        const uint flatIndex = index.y * mParams.mOutputDim.x + index.x;
        mCausticReservoirs[flatIndex] = r;
    }

    // ---------------------------------------------------------------------------------------------------------
    // ------------------------------------------- Emission sampling -------------------------------------------
    // ---------------------------------------------------------------------------------------------------------

    float3 SampleCosHemisphere(float2 u) {
        const float2 d = sample_disk_concentric(u);
        return float3(d, sqrt(max(0.f, 1.f - dot(d, d))));
    }
    float CosHemispherePdfW(float cosDir) {
        return cosDir * M_1_PI;
    }
    static const float gConcentricDiscPdfA = M_1_PI;

    void GetLightSamplePdf(const PathVertex vertex, const float3 prevPos, const float3 prevNormal, const bool upperOnly, out float emissionPdfW, out float directPdfW, out float directPdfA) {
        emissionPdfW = 0;
        directPdfW = 0;
        directPdfA = 0;

        if (vertex.IsFinite()) {
            if (gUseEmissiveLights) {
                HitInfo hit = HitInfo(vertex.mVertex.mPackedHit);
                if (hit.getType() == HitType::Triangle) {
                    const float cosIn = dot(vertex.GetFaceNormal(), vertex.GetDirIn());
                    if (cosIn > kMinCosTheta) {
                        const TriangleHit triHit = hit.getTriangleHit();
                        const uint triangleIndex = gScene.lightCollection.getTriangleIndex(triHit.instanceID, triHit.primitiveIndex);
                        if (triangleIndex != LightCollection::kInvalidIndex) {
                            directPdfA = 1.f / gScene.lightCollection.getTriangle(triangleIndex).area;
                            directPdfA *= mEmissiveSampler.evalTriangleSelectionPdf(prevPos, prevNormal, upperOnly, triangleIndex);

                            if (gUseEnvLight) directPdfA *= 1 - mParams.mEnvMapProb;

                            emissionPdfW = directPdfA * CosHemispherePdfW(cosIn);
                            directPdfW   = directPdfA * sqr(vertex.mVertex.mRayDistance) / cosIn;
                        }
                    }
                }
            }
        } else {
            if (gUseEnvLight) {
                directPdfA = mEnvMapSampler.evalPdf(vertex.mVertex.mRayDirection);

                if (gUseEmissiveLights) directPdfA *= mParams.mEnvMapProb;

                emissionPdfW = directPdfA * gConcentricDiscPdfA / sqr(mParams.mSceneSphere.w);
                directPdfW = directPdfA;
            }
        }
    }
}

///////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////// MIS weight helpers ////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////

#if DISABLE_VC

extension RecursiveMisState {
    // N_LT * p_rev / p_fwd
    property float alpha {
        get { return dVC; }
        set { dVC = newValue; }
    }

    // pA_rev(x_k) / pA_fwd(x_k)
    property float ratio_k {
        get { return dVM; }
        set { dVM = newValue; }
    }

    property bool isFirstPT {
        get { return (bool)EXTRACT_BITS(1, 0, flag); }
        set { flag = PACK_BITS(1, 0, flag, (uint)newValue); }
    }
    property bool isFirstLT {
        get { return (bool)EXTRACT_BITS(1, 1, flag); }
        set { flag = PACK_BITS(1, 1, flag, (uint)newValue); }
    }
    property bool lastDelta {
        get { return (bool)EXTRACT_BITS(1, 2, flag); }
        set { flag = PACK_BITS(1, 2, flag, (uint)newValue); }
    }

    __init(const PathVertex vertex) {
        float cosAtCamera;
        const float cameraPdfW = gPathGenerator.GetImageToSolidAngleFactor(-vertex.GetDirIn(), cosAtCamera);

        const float cosIn = vertex.GetCosN(vertex.GetDirIn());
        const float3 d = gScene.camera.getPosition() - vertex.GetPosition();
        const float cameraPdfA = cameraPdfW * cosIn / dot(d, d);

        alpha = gPathGenerator.Mis(gPathGenerator.mParams.mLightSubpathCount / cameraPdfA);
        ratio_k = 0;
        dVCM = 0;
        flag = 0;
        isFirstPT = true;
    }

    __init(const bool finiteEmitter, const float directPdfA, const float emissionPdfW, const float cosLight) {
        alpha = gPathGenerator.Mis(cosLight / (emissionPdfW * gPathGenerator.mParams.mLightSubpathCount));
        ratio_k = gPathGenerator.Mis(directPdfA / cosLight);
        dVCM = 0;
        flag = 0;
        isFirstLT = true;
    }

    [mutating]
    void ProcessDirection(const DirectionSampleData r, const float cosOut, const bool connectable) {
        if (connectable && !r.IsLobe(LobeType::Delta)) {
            alpha *= gPathGenerator.Mis(1 / r.mFwdPdfW);
            // p_rev(x_0) = 0
            if (!isFirstPT) alpha *= gPathGenerator.Mis(r.mRevPdfW);
            if (isFirstLT) ratio_k *= gPathGenerator.Mis(1 / r.mRevPdfW);
            lastDelta = false;
        } else {
            if (isFirstPT) alpha = 0;
            if (isFirstLT) ratio_k = 0;
            lastDelta = true;
        }
        alpha *= gPathGenerator.Mis(cosOut);
        isFirstPT = false;
        isFirstLT = false;
    }

    [mutating]
    void ProcessRay(const float dist, const float cosIn, const bool prevFinite = true) {
        alpha /= gPathGenerator.Mis(cosIn);
        if (isFirstLT) ratio_k *= gPathGenerator.Mis(sqr(dist));
    }


    float EvalDirectLightMIS(const float directPdfW, const float emissionPdfW, const ReflectanceEvalData f, const float cosOut, const float cosLight) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS())
            return misWeight;

        // p_rev(x_k-1)
        float p_rev_k1 = (emissionPdfW * cosOut) / (directPdfW * cosLight);

        float w_pt = gPathGenerator.Mis(f.mFwdPdfW / directPdfW);
        float w_lt = alpha * gPathGenerator.Mis(p_rev_k1);
        if (!isFirstPT) w_lt *= gPathGenerator.Mis(f.mRevPdfW);
        misWeight = 1 / (1 + w_pt + w_lt);

        return misWeight;
    }

    float EvalVertexConnectionMIS(const RecursiveMisState v, const ReflectanceEvalData r, const ReflectanceEvalData f, const float cosCam, const float cosLight, const float invDist2) {
        return 0;
    }

    float EvalVertexMergingMIS(const RecursiveMisState v, const ReflectanceEvalData f) {
        return 0;
    }

    float EvalLightTraceMIS(const float scatterRevPdfW, const float cameraPdfA) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS() || gPathGenerator.gLightTraceOnly)
            return misWeight;

        float ratio = ratio_k;
        if (isFirstLT) ratio *= gPathGenerator.Mis(1 / scatterRevPdfW);

        float w_pt = alpha * gPathGenerator.Mis(cameraPdfA * scatterRevPdfW);
        float w_nee = w_pt * (1 + ratio);
        misWeight = 1 / (1 + w_pt + w_nee);

        return misWeight;
    }

    float EvalCameraTraceMIS(const float scatterFwdPdfW, const float directPdfA, const float directPdfW, const float emissionPdfW) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS()) return misWeight;

        float w_lt = alpha * gPathGenerator.Mis(emissionPdfW);
        float w_nee = lastDelta ? 0 : gPathGenerator.Mis(directPdfW / scatterFwdPdfW);
        misWeight = 1 / (1 + w_lt + w_nee);

        return misWeight;
    }
}

extension ReconnectionMisState {
    property float alpha_r { get { return prod_ratio; } set { prod_ratio = newValue; } }
    property float alpha_k { get { return prod_dVCM; } set { prod_dVCM = newValue; } }

    [mutating]
    void Update(
        const RecursiveMisState mis,
        const float pdfFwd,
        const float pdfRev,
        const float cosIn,
        const float cosOut,
        const float dist,
        const int idx) {
        if (idx == 0) alpha_r = mis.alpha * gPathGenerator.Mis(cosIn / cosOut);
        if (idx >= 0) alpha_k = mis.alpha;
    }

    void Apply(inout RecursiveMisState mis_r, float pdfFwd_r, float pdfRev_r, bool singleBounce) {
        mis_r.alpha *= SafeDivide(alpha_k, alpha_r) * gPathGenerator.Mis(pdfRev_r / pdfFwd_r);
    }
}

#else

extension RecursiveMisState {
    __init(const PathVertex vertex) {
        if (gPathGenerator.gBidirectional) {
            float cosAtCamera;
            const float cameraPdfW = gPathGenerator.GetImageToSolidAngleFactor(-vertex.GetDirIn(), cosAtCamera);
            dVCM = gPathGenerator.Mis(gPathGenerator.mParams.mLightSubpathCount / cameraPdfW);
            dVC = 0;

            const float cosIn = vertex.GetCosN(vertex.GetDirIn());
            const float3 d = gScene.camera.getPosition() - vertex.GetPosition();
            dVCM *= gPathGenerator.Mis(dot(d,d) / cosIn);

            if (gPathGenerator.gDisableCameraConnection)
                dVCM = 0;
        }
    }

    __init(const bool finiteEmitter, const float directPdfA, const float emissionPdfW, const float cosLight) {
        dVCM = gPathGenerator.Mis(directPdfA / emissionPdfW);
        dVC = finiteEmitter ? gPathGenerator.Mis(cosLight / emissionPdfW) : 0;
    }

    [mutating]
    void ProcessDirection(const DirectionSampleData r, const float cosOut, const bool connectable) {
        // update mis quantities
        if (gPathGenerator.gBidirectional) {
            if (connectable && !r.IsLobe(LobeType::Delta)) {
                // SmallVCM tech. rep. (34)-(36)
                const float invPdf = 1.f / r.mFwdPdfW;
                dVC = gPathGenerator.Mis(cosOut * invPdf) * (dVC * gPathGenerator.Mis(r.mRevPdfW) + dVCM);
                dVCM = gPathGenerator.Mis(invPdf);
            } else {
                // SmallVCM tech. rep. (53)-(55)
                dVC *= gPathGenerator.Mis(cosOut);
                dVCM = 0.f;
            }
        }
    }

    [mutating]
    void ProcessRay(const float dist, const float cosIn, const bool prevFinite = true) {
        // update mis quantities
        if (gPathGenerator.gBidirectional && dist < FLT_MAX) {
            if (prevFinite)
                dVCM *= gPathGenerator.Mis(sqr(dist));
            const float invCosIn = 1 / gPathGenerator.Mis(cosIn);
            dVCM *= invCosIn;
            dVC  *= invCosIn;
        }
    }


    float EvalDirectLightMIS(const float directPdfW, const float emissionPdfW, const ReflectanceEvalData f, const float cosOut, const float cosLight) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS()) return misWeight;

        if (gPathGenerator.gBidirectional) {
            const float wLight  = gPathGenerator.Mis(f.mFwdPdfW / directPdfW);
            const float wCamera = gPathGenerator.Mis(emissionPdfW * abs(cosOut) / (directPdfW * cosLight)) * (dVCM + dVC * gPathGenerator.Mis(f.mRevPdfW));
            misWeight = 1 / (wLight + 1 + wCamera);
        } else {
            // NEE MIS
            misWeight = gPathGenerator.Mis(directPdfW, f.mFwdPdfW);
        }
        return misWeight;
    }

    float EvalVertexConnectionMIS(const RecursiveMisState v, const ReflectanceEvalData r, const ReflectanceEvalData f, const float cosCam, const float cosLight, const float invDist2) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS()) return misWeight;

        const float cameraBsdfDirPdfA = f.mFwdPdfW * cosLight * invDist2;
        const float lightBsdfDirPdfA  = r.mFwdPdfW * cosCam   * invDist2;
        const float wLight  = gPathGenerator.Mis(cameraBsdfDirPdfA) * (v.dVCM + v.dVC * gPathGenerator.Mis(r.mRevPdfW));
        const float wCamera = gPathGenerator.Mis(lightBsdfDirPdfA)  * (  dVCM +   dVC * gPathGenerator.Mis(f.mRevPdfW));
        misWeight = 1 / (wLight + 1 + wCamera);

        return misWeight;
    }

    float EvalLightTraceMIS(const float scatterRevPdfW, const float cameraPdfA) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS() || gPathGenerator.gLightTraceOnly)
            return misWeight;

        const float wLight = gPathGenerator.Mis(cameraPdfA / gPathGenerator.mParams.mLightSubpathCount) * (dVCM + dVC * gPathGenerator.Mis(scatterRevPdfW));
        misWeight = 1 / (wLight + 1);

        return misWeight;
    }

    float EvalCameraTraceMIS(const float scatterFwdPdfW, const float directPdfA, const float directPdfW, const float emissionPdfW) {
        float misWeight = 1;
        if (gPathGenerator.DebugDisableMIS()) return misWeight;

        if (gPathGenerator.gBidirectional) {
            const float wCamera = gPathGenerator.Mis(directPdfA) * dVCM + gPathGenerator.Mis(emissionPdfW) * dVC;
            misWeight = 1 / (1 + wCamera);
        } else if (gPathGenerator.gSampleDirectLight) {
            // NEE MIS
            misWeight = scatterFwdPdfW > 0 ? gPathGenerator.Mis(scatterFwdPdfW, directPdfW) : 1;
        }

        return misWeight;
    }
}

extension ReconnectionMisState {
    // no vertex merging for now
    property float sumProd_eta { get { return 0; } }

    [mutating]
    void Update(
        const RecursiveMisState mis,
        const float pdfFwd,
        const float pdfRev,
        const float cosIn,
        const float cosOut,
        const float dist,
        const uint idx) {
        const bool isDelta = mis.dVCM == 0;
        if (idx == 0) {
            invFwdG_r = (dist*dist) / cosIn;
            sumProd_dVCM = 0;
            prod_dVCM    = 0;
            //sumProd_eta  = 0;
            last_invPdf  = 1;
            prod_ratio = gPathGenerator.Mis(cosOut / cosIn);
        }
        if (idx == 1)
            prod_dVCM = isDelta ? 0 : 1;

        // update sum products

        if (idx > 1) {
            float r = gPathGenerator.Mis(pdfRev * last_invPdf);
            prod_ratio *= gPathGenerator.Mis(last_invPdf);
            prod_dVCM  *= r;
            //sumProd_eta  *= r;
            sumProd_dVCM *= r;
            if (!isDelta) {
                //sumProd_eta  += r;
                sumProd_dVCM += end_dVCM;
            }
        }
        if (idx > 0) {
            if (!isDelta)
                prod_ratio *= gPathGenerator.Mis(pdfRev);
        }

        // update last_invPdf for next bounce

        float r = cosOut / cosIn;
        if (pdfFwd > 0)
            r /= pdfFwd;
        if (idx > 0) {
            last_invPdf = r;
        }

        end_coeff = gPathGenerator.Mis(r);
        end_dVCM = mis.dVCM;
    }

    void Apply(inout RecursiveMisState mis_r, float pdfFwd_r, float pdfRev_r, bool singleBounce) {
        float invPdf = 1 / pdfFwd_r;
        float ratio_r = gPathGenerator.Mis(invPdf) * prod_ratio;

        if (singleBounce) {
            // vertex after rcv is last vertex
            mis_r.dVC = ratio_r * (
                mis_r.dVCM
                +
                mis_r.dVC * gPathGenerator.Mis(pdfRev_r));
            mis_r.dVCM = gPathGenerator.Mis(invPdf * invFwdG_r);
        } else {
            mis_r.dVC = end_coeff * (
                mis_r.dVCM * ratio_r + gPathGenerator.Mis(invPdf * invFwdG_r) * prod_dVCM + sumProd_dVCM
                +
                mis_r.dVC * ratio_r * gPathGenerator.Mis(pdfRev_r));

            mis_r.dVCM = end_dVCM;
        }
    }
}

#endif

///////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////// Path tracing implementation ///////////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////

SampleGenerator MakeSampleGenerator(const uint2 id, const uint seed) { return SampleGenerator(id, seed); }

extension PathGenerator {
    // stores information about the previous vertex along the path
    struct CachedVertexData {
        float3            position       = 0;
        float             scatterFwdPdfW = 0;
        float3            normal         = 0;
        float             scatterRevPdfW = 0;
        RecursiveMisState mis = {};
        uint              flags = 0;

        property bool upperHemisphereOnly {
            get { return (bool)BF_GET(flags, 0, 1); }
            set { BF_SET(flags, (uint)newValue, 0, 1); }
        }
        property bool connectable {
            get { return (bool)BF_GET(flags, 1, 1); }
            set { BF_SET(flags, (uint)newValue, 1, 1); }
        }

        bool HasNormal() { return any(normal != 0); }
    };

    struct PathState<let bShift : bool> {
        SampleGenerator sg;     // sample generator for everything but BSDF sampling
        SampleGenerator sgBsdf; // sample generator for BSDF sampling

        float3 throughput = 0;
        float  pdfW = 0;

        PathId id;
        uint packedBounces = 0;
        uint packedDiffuseBounces = 0;

        CachedVertexData lastVertex = {};

        RecursiveMisState mis = {};
        #if USE_RECONNECTION_MIS
        ReconnectionMisState rcvMis = {};
        #endif

        PackedPathVertex rcv = {};
        float3 throughputAtRcv = 0;
        float  pdfAtRcv = 0;
        float3 rcvDirOut;
        float  prefixPdf = 0;
        float  rcvCos = 0;
        float  rcvDist = 0;

        PathId        lightSubpathId;
        PackedHitInfo lightSubpathVertex = {};

        property uint bounces {
            get { return BF_GET(packedBounces,    0, 15); }
            set { BF_SET(packedBounces, newValue, 0, 15); }
        }
        property uint prefixBounces {
            get { return BF_GET(packedBounces,    15, 15); }
            set { BF_SET(packedBounces, newValue, 15, 15); }
        }
        property uint diffuseBounces {
            get { return BF_GET(packedDiffuseBounces, 0, 16); }
            set { BF_SET(packedDiffuseBounces, newValue, 0, 16); }
        }
        property uint rcvDiffuseBounces {
            get { return BF_GET(packedDiffuseBounces, 16, 16); }
            set { BF_SET(packedDiffuseBounces, newValue, 16, 16); }
        }
        property bool isLightPath {
            get { return (bool)BF_GET(packedBounces,    30, 1); }
            set { BF_SET(packedBounces, (uint)newValue, 30, 1); }
        }
        property bool deltaRcv {
            get { return (bool)BF_GET(packedBounces,    31, 1); }
            set { BF_SET(packedBounces, (uint)newValue, 31, 1); }
        }
        property bool rcvFound {
            get { return prefixPdf > 0; }
        }

        [mutating]
        void Terminate() {
            throughput = 0;
        }
    };

    LightSubpathVertex PackLightSubpathVertex<let bShift : bool>(const PathState<bShift> s, const PathVertex vertex) {
        LightSubpathVertex v = {};
        v.mLightSubpath = LightSubpathData::Create(
            s.lightSubpathVertex,
            s.id,
            s.bounces + 2,
            s.diffuseBounces,
            s.pdfW
        );
        v.mVertex = vertex.Pack();
        v.mThroughput = s.throughput;
        v.mis = s.mis;
        return v;
    }

    // Merges a canonical sample into the pixel's reservoir
    void ProcessSample(inout PathReservoir r, inout SampleGenerator sg, PathSample ps, float weight) {
        if (gUseResampling) {
            r.Merge(sampleNext1D(sg), ps, weight * ps.GetTargetPdf(), 0);
        } else if (ps.IsValid() && weight > 0) {
            print("Found path. contrib:", ps.mContribution);
            print("\tLight subpath vertices:", ps.mSuffix.mLightSubpath.mVertexCount);
            print("\tPrefix bounces:", ps.mPrefixBounces);
            r.mSample.mContribution += ps.mContribution * (ps.mMisWeight * weight);
        }
    }


    // ---------------------------------------------------------------------------------------------------------
    // ----------------------------------------- Connection stategies ------------------------------------------
    // ---------------------------------------------------------------------------------------------------------

    PathSample ConnectToLight       <let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, out float integrationWeight) {
        integrationWeight = 0;

        PathSample result = {};

        if (DebugDisablePath(s.bounces + 1, 1, s.rcvFound ? s.prefixBounces : s.bounces, false)) {
            if (bShift) print("Shift failed: disabled", 0);
            return result;
        }

        // Sample emissive path vertex

        const PathId lightPathId = bShift ? s.lightSubpathId : PathId(s.sg.next(), uint2(s.sg.next(), s.sg.next()));
        SampleGenerator sg = MakeSampleGenerator(lightPathId.mId, lightPathId.mSeed);

        float directPdfA = 0;
        float directPdfW = 0;
        float emissionPdfW = 0;
        PackedPathVertex l = {};
        float cosLight = 1;
        float3 le = 0;
        {
            const bool useEnvMap = sampleNext1D(sg) < mParams.mEnvMapProb;
            const float2 uv = sampleNext2D(sg);

            if (gUseEnvLight && (!gUseEmissiveLights || useEnvMap)) {
                EnvMapSample envSample;
                if (!mEnvMapSampler.sample(uv, envSample)) {
                    if (bShift) print("Shift failed: invalid sample", 0);
                    return result;
                }

                if (gUseEmissiveLights) envSample.pdf *= mParams.mEnvMapProb;

                le = envSample.Le;
                if (!any(le > 0)) {
                    if (bShift) print("Shift failed: zero le", 0);
                    return result;
                }

                l = PackedPathVertex(Ray(vertex.ComputeRayOrigin(envSample.dir), envSample.dir), HitInfo(0), FLT_MAX);

                directPdfA = envSample.pdf;
                directPdfW = envSample.pdf;
                emissionPdfW = directPdfW * gConcentricDiscPdfA / sqr(mParams.mSceneSphere.w);
            } else if (gUseEmissiveLights && !(gUseEnvLight && useEnvMap)) {
                const bool upperOnly = vertex.UpperHemisphereOnly();
                const float3 vertexNormal = upperOnly ? vertex.GetFaceNormal() : 0;
                float selectionPdf;
                uint triangleIndex;
                float3 barycentrics;
                if (bShift) {
                    const TriangleHit triHit = HitInfo(s.lightSubpathVertex).getTriangleHit();
                    triangleIndex = gScene.lightCollection.getTriangleIndex(triHit.instanceID, triHit.primitiveIndex);
                    if (triangleIndex != LightCollection::kInvalidIndex) {
                        selectionPdf = mEmissiveSampler.evalTriangleSelectionPdf(vertex.GetPosition(), vertexNormal, upperOnly, triangleIndex);
                        barycentrics = float3(1 - triHit.barycentrics.x - triHit.barycentrics.y, triHit.barycentrics);
                    }
                } else {
                    // [Falcor 8] sampleLight now returns TriangleLightSample.
                    // Extract triangleIndex + uv→barycentrics; query selection
                    // pdf separately so downstream BDPT MIS math (which splits
                    // triangle-selection from area-uv pdfs) stays intact.
                    TriangleLightSample ls;
                    if (mEmissiveSampler.sampleLight(vertex.GetPosition(), vertexNormal, upperOnly, sg, ls)) {
                        triangleIndex = ls.triangleIndex;
                        selectionPdf = mEmissiveSampler.evalTriangleSelectionPdf(vertex.GetPosition(), vertexNormal, upperOnly, triangleIndex);
                        // [Falcor 8 bug fix] TriangleLightSample.uv is the RAW 2D random
                        // numbers (the u that drove the sample), NOT barycentric coordinates.
                        // The Falcor-7 port treated it as bary directly which biases the
                        // sample distribution (causes ~35% dim on VeachAjar — task #14).
                        barycentrics = sample_triangle(ls.uv);
                    } else {
                        triangleIndex = LightCollection::kInvalidIndex;
                        selectionPdf = 0;
                        barycentrics = 0;
                    }
                }

                if (triangleIndex == LightCollection::kInvalidIndex) {
                    if (bShift) print("Shift failed: invalid triangle", triangleIndex);
                    return result;
                }

                if (gUseEnvLight) selectionPdf *= 1 - mParams.mEnvMapProb;

                let tri = gScene.lightCollection.getTriangle(triangleIndex);

                le = gScene.materials.evalEmissive(tri.materialID, tri.getTexCoord(barycentrics));
                if (!any(le > 0)) {
                    if (bShift) print("Shift failed: zero le", le);
                    return result;
                }

                directPdfA = selectionPdf / tri.area;

                const float3 triPos = computeRayOrigin(tri.getPosition(barycentrics), tri.normal);
                const float3 rayOrigin = vertex.ComputeRayOrigin(triPos - vertex.GetPosition());
                float3 toLight = triPos - rayOrigin;
                const float dist = length(toLight);
                toLight /= dist;

                cosLight = -dot(tri.normal, toLight);
                if (cosLight < kMinCosTheta) {
                    if (bShift) print("Shift failed: cosLight < kMinCosTheta", cosLight);
                    return result;
                }

                const MeshLightData meshData = gScene.lightCollection.getMeshData(triangleIndex);

                TriangleHit triHit = {};
                triHit.instanceID     = { meshData.instanceID };
                triHit.primitiveIndex = triangleIndex - meshData.triangleOffset;
                triHit.barycentrics = barycentrics.yz;

                l = PackedPathVertex(Ray(rayOrigin, toLight), HitInfo(triHit), dist);

                directPdfW   = directPdfA * sqr(dist) / cosLight;
                emissionPdfW = directPdfA * CosHemispherePdfW(cosLight);
            } else {
                return result;
            }
        }

        const float cosOut = vertex.GetCosN(l.mRayDirection);
        if (cosOut < kMinCosTheta)
            return result;

        ReflectanceEvalData f = vertex.EvaluateReflectance(s.sg, l.mRayDirection, false);

        if (gBidirectional && gDisableCameraConnection && !s.isLightPath) {
            if (s.bounces == 0)
                emissionPdfW = 0;
            else if (s.bounces == 1)
                f.mRevPdfW = 0;
        }

        const float3 contrib = s.throughput * f.mReflectance * le;
        const float samplePdf = s.pdfW * directPdfW;
        if (!any(contrib > 0) || !(samplePdf > 0))
            return result;

        if (Occluded(Ray(l.mRayOrigin, l.mRayDirection, 0, l.mRayDistance)))
            return result;

        // divide by pdf
        integrationWeight = 1.f / samplePdf;

        // compute mis weight
        const float misWeight = s.mis.EvalDirectLightMIS(directPdfW, emissionPdfW, f, cosOut, cosLight);
        MisEvalData misEvalArgs = {};
        #if USE_RECONNECTION_MIS
        misEvalArgs.reconnectionMis = s.rcvMis;
        misEvalArgs.directPdfW = directPdfW;
        misEvalArgs.emissionPdfW = emissionPdfW;
        misEvalArgs.cameraScatterFwdPdfW = f.mFwdPdfW;
        misEvalArgs.cameraScatterRevPdfW = f.mRevPdfW;
        misEvalArgs.cosCam = cosOut;
        misEvalArgs.cosLight = cosLight;
        #endif

        float3 suffixContrib;
        float3 suffixDir;
        float suffixPdf = directPdfW;
        const bool hasRcv = s.rcvFound;
        if (hasRcv) {
            // use rcv found earlier along the camera subpath
            if (s.bounces == s.prefixBounces + 1) {
                // the light vertex is the 2nd vertex in the suffix
                suffixContrib = le;
                suffixDir = l.mRayDirection;
                suffixPdf = directPdfW;
            } else {
                // the light vertex is after the 2nd suffix vertex
                suffixContrib = SafeDivide(contrib, s.throughputAtRcv);
                suffixDir = s.rcvDirOut;
                suffixPdf = directPdfW * (s.pdfW / s.pdfAtRcv);
            }
        } else {
            // light vertex is the first vertex in the suffix
            suffixContrib = le;
            suffixDir = 0;
            suffixPdf = directPdfA;
        }

        const LightSubpathData lightSubpath = LightSubpathData::Create(
            l.mPackedHit,
            lightPathId,
            1,
            0,
            directPdfA
        );

        const PathSuffix suffix = PathSuffix::Create(
            suffixContrib,
            suffixPdf,
            hasRcv ? s.rcv : l,
            suffixDir,
            hasRcv ? s.rcvDist : l.mRayDistance,
            hasRcv ? s.rcvCos : cosLight,
            misEvalArgs,
            lightSubpath
        );

        result = PathSample::Create(
            contrib,
            misWeight,
            s.bounces + 1,
            hasRcv ? s.prefixPdf         : s.pdfW,
            hasRcv ? s.prefixBounces     : s.bounces,
            hasRcv ? s.rcvDiffuseBounces : s.diffuseBounces,
            s.id,
            suffix,
            PathFlags::eNone
        );

        return result;
    }

    // [Bug #3 fix] Connect to an analytic light (PointLight, DirectionalLight,
    // SpotLight, etc.). BDPT's original ConnectToLight only samples emissive
    // triangles + env map; analytic lights are silently skipped. Added as a
    // parallel NEE call from SampleCanonicalPaths' loop. For delta-position
    // lights (point/dir/spot), only NEE can sample them — BSDF importance
    // sampling has probability zero of landing on the delta light direction,
    // so misWeight = 1.
    PathSample ConnectToAnalyticLight<let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, out float integrationWeight) {
        integrationWeight = 0;
        PathSample result = {};

        if (!gUseAnalyticLights) return result;

        const uint lightCount = gScene.getLightCount();
        if (lightCount == 0) return result;

        // Uniform light selection.
        SampleGenerator sgLocal = s.sg;  // local copy so we don't disturb caller
        const uint lightIndex = min(uint(sampleNext1D(sgLocal) * lightCount), lightCount - 1);
        const float lightSelectionPdf = 1.0f / float(lightCount);

        AnalyticLightSample als;
        if (!sampleLight(vertex.GetPosition(), gScene.getLight(lightIndex), sgLocal, als)) return result;
        if (!any(als.Li > 0)) return result;

        // Receiver-side cosine + occlusion.
        const float cosOut = vertex.GetCosN(als.dir);
        if (cosOut < kMinCosTheta) return result;

        ReflectanceEvalData f = vertex.EvaluateReflectance(s.sg, als.dir, false);
        if (!any(f.mReflectance > 0)) return result;

        const float3 rayOrigin = vertex.ComputeRayOrigin(als.dir);
        if (Occluded(Ray(rayOrigin, als.dir, 0, als.distance))) return result;

        // Falcor's AnalyticLightSample.Li is "Le / pdf" form (sample weight)
        // for the WITHIN-light sample only — the per-light selection pdf
        // (1/lightCount) is NOT included. So the proper-form contribution is
        // BRDF * cos * als.Li / lightSelectionPdf  (=  BRDF * cos * Le * lightCount / pdf).
        // misWeight = 1 since delta-position lights can't be sampled by BSDF strategy.
        const float3 contrib = s.throughput * f.mReflectance * als.Li;
        if (!any(contrib > 0)) return result;
        if (!(s.pdfW > 0)) return result;

        // Integration weight encodes the inverse-light-selection-pdf so the
        // light-count factor flows in correctly via ProcessSample's weight.
        integrationWeight = 1.0f / (s.pdfW * lightSelectionPdf);
        const float misWeight = 1.0f;  // delta lights: only NEE can sample them

        // Build a minimal valid PathSample so ProcessSample accepts it.
        // No light subpath / no rcv data — this is an isolated NEE contribution.
        const float samplePdf = s.pdfW * lightSelectionPdf;
        PathSuffix suffix = PathSuffix::Create(
            als.Li,
            samplePdf,
            PackedPathVertex(Ray(rayOrigin, als.dir, 0, als.distance), HitInfo(0), als.distance),
            0,
            als.distance,
            1,  // cosLight: 1 for delta (no surface)
            MisEvalData(),
            LightSubpathData::Create({}, {}, 1, 0, lightSelectionPdf)
        );

        result = PathSample::Create(
            contrib,
            misWeight,
            s.bounces + 1,
            s.pdfW,
            s.bounces,
            s.diffuseBounces,
            s.id,
            suffix,
            PathFlags::eNone
        );

        return result;
    }

    PathSample ConnectToLightSubpath<let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, const LightSubpathVertex v, out float integrationWeight) {
        integrationWeight = 0;

        PathSample result = {};

        const uint bounces = s.bounces + v.mBounces + 2;
        if (bounces > mParams.mMaxBounces || s.diffuseBounces + v.mDiffuseBounces + 2 > mParams.mMaxDiffuseBounces || DebugDisablePath(bounces, v.mLightSubpath.mVertexCount, s.rcvFound ? s.prefixBounces : s.bounces, false))
            return result;

        // evaluate the bsdf at the light subpath vertex
        float cosLight, dist;
        float3 toLight;
        Ray visibilityRay;
        ReflectanceEvalData r;
        {
            const PathVertex lightVertex = PathVertex(v.mVertex);
            toLight = lightVertex.GetPosition() - vertex.GetPosition();
            dist = length(toLight);
            toLight /= dist;

            cosLight = lightVertex.GetCosN(toLight);
            if (cosLight < kMinCosTheta)
                return result;

            r = lightVertex.EvaluateReflectance(s.sg, -toLight, true);
            r.mReflectance /= cosLight;

            if (gBidirectional && gDisableCameraConnection && !s.isLightPath && s.bounces == 0)
                r.mFwdPdfW = 0;

            const float3 rayOrigin = vertex.ComputeRayOrigin(toLight);
            visibilityRay = Ray(rayOrigin, lightVertex.ComputeRayOrigin(-toLight) - rayOrigin, 0, 0);
            visibilityRay.tMax = length(visibilityRay.dir);
            visibilityRay.dir /= visibilityRay.tMax;
        }
        if (!any(r.mReflectance > 0)) {
            if (bShift) print("Subpath reconnection failed: !any(r.mReflectance > 0)", r.mReflectance);
            return result;
        }

        // evaluate the bsdf at the camera subpath vertex
        const float cosCam = vertex.GetCosN(toLight);
        if (cosCam < kMinCosTheta)
            return result;

        ReflectanceEvalData f = vertex.EvaluateReflectance(s.sg, toLight, false);
        if (!any(f.mReflectance > 0)) {
            if (bShift) print("Subpath reconnection failed: !any(f.mReflectance > 0)", f.mReflectance);
            return result;
        }

        if (gBidirectional && gDisableCameraConnection && !s.isLightPath && s.bounces == 1)
            f.mRevPdfW = 0;

        const float3 contrib = (s.throughput * v.mThroughput) * (f.mReflectance * r.mReflectance);

        if (!any(contrib > 0) || any(contrib < 0)) {
            if (bShift) print("Subpath reconnection failed: any(contrib > 0) || any(contrib < 0)", contrib);
            return result;
        }

        if (Occluded(visibilityRay)) {
            if (bShift) print("Subpath reconnection failed: Occluded", 0);
            return result;
        }

        float lightSubpathPdfW = v.mLightSubpath.mPdf * (sqr(dist) / cosLight);

        integrationWeight = 1 / (s.pdfW * lightSubpathPdfW);

        const float invDist2 = 1 / sqr(dist);

        const float misWeight = s.mis.EvalVertexConnectionMIS(v.mis, r, f, cosCam, cosLight, invDist2);
        MisEvalData misEvalArgs = {};
        #if USE_RECONNECTION_MIS
        misEvalArgs.reconnectionMis = s.rcvMis;
        misEvalArgs.lightSubpathMis = v.mis;
        misEvalArgs.lightScatterFwdPdfW = r.mFwdPdfW;
        misEvalArgs.lightScatterRevPdfW = r.mRevPdfW;
        misEvalArgs.cameraScatterFwdPdfW = f.mFwdPdfW;
        misEvalArgs.cameraScatterRevPdfW = f.mRevPdfW;
        misEvalArgs.cosCam = cosCam;
        misEvalArgs.cosLight = cosLight;
        misEvalArgs.invDist2 = invDist2;
        #endif

        float3 suffixContrib;
        float3 suffixDir;
        float suffixPdf;
        const bool hasRcv = s.rcvFound;
        if (hasRcv) {
            // use rcv found earlier along the camera subpath
            if (s.bounces == s.prefixBounces + 1) {
                // the light vertex is the 2nd vertex in the suffix
                suffixContrib = v.mThroughput * r.mReflectance;
                suffixDir = toLight;
                suffixPdf = lightSubpathPdfW;
            } else {
                // the light vertex is after the 2nd suffix vertex
                suffixContrib = SafeDivide(contrib, s.throughputAtRcv);
                suffixDir = s.rcvDirOut;
                suffixPdf = lightSubpathPdfW * (s.pdfW / s.pdfAtRcv);
            }
        } else {
            // use the light subpath vertex as the rcv
            suffixContrib = v.mThroughput;
            suffixDir = v.GetDirIn();
            suffixPdf = v.mLightSubpath.mPdf;
        }

        const PathSuffix suffix = PathSuffix::Create(
            suffixContrib,
            suffixPdf,
            hasRcv ? s.rcv : v.mVertex,
            suffixDir,
            hasRcv ? s.rcvDist : dist,
            hasRcv ? s.rcvCos : cosLight,
            misEvalArgs,
            v.mLightSubpath
        );

        result = PathSample::Create(
            contrib,
            misWeight,
            bounces,
            hasRcv ? s.prefixPdf         : s.pdfW,
            hasRcv ? s.prefixBounces     : s.bounces,
            hasRcv ? s.rcvDiffuseBounces : s.diffuseBounces,
            s.id,
            suffix,
            PathFlags::eNone);

        return result;
    }
    PathSample ConnectToCamera      <let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, out int2 pixelCoord, out float integrationWeight, const bool checkVisibility = true, const bool usePrevCamera = false) {
        integrationWeight = 0;
        pixelCoord = -1;
        PathSample result = {};

        if (DebugDisablePath(s.bounces + 1, s.bounces + 2, 0, false))
            return result;

        const float3 cameraPos = usePrevCamera ? gScene.camera.data.prevPosW : gScene.camera.data.posW;
        const float3 rayOrigin = vertex.ComputeRayOrigin(cameraPos - vertex.GetPosition());
        float3 toCamera = cameraPos - rayOrigin;
        const float dist = length(toCamera);
        toCamera /= dist;

        float cosAtCamera;
        const float imageToSolidAngleFactor = GetImageToSolidAngleFactor(-toCamera, cosAtCamera);

        pixelCoord = usePrevCamera ? GetPrevPixelCoord(vertex.GetPosition()) : GetPixelCoord(vertex.GetPosition());
        if (any(pixelCoord < 0) || any(pixelCoord >= mParams.mOutputDim) || cosAtCamera <= 0)
            return result;

        const float cosOut = vertex.GetCosN(toCamera);
        if (cosOut < kMinCosTheta)
            return result;

        ReflectanceEvalData f = vertex.EvaluateReflectance(s.sg, toCamera, true);
        f.mReflectance /= cosOut;

        // Compute pdf conversion factor from image plane area to surface area
        const float cameraPdfA = imageToSolidAngleFactor * cosOut / sqr(dist);

        const float cosIn = vertex.GetCosN(vertex.GetDirIn());

        const float3 contrib = s.throughput * f.mReflectance;
        if (!any(contrib > 0))
            return result;

        const float samplePdf = s.pdfW * (1 / cameraPdfA);
        if (!(samplePdf > 0))
            return result;
        if (checkVisibility) {
            if (Occluded(Ray(rayOrigin, toCamera, 0, dist)))
                return result;
        }

        integrationWeight = 1.f / samplePdf;

        if (!gUseResampling) integrationWeight /= mParams.mLightSubpathCount;

        bool caustic = s.deltaRcv || s.rcvDist < mParams.mReconnectionDistance;

        const float misWeight = s.mis.EvalLightTraceMIS(f.mRevPdfW, cameraPdfA);
        MisEvalData misEvalArgs = {};
        #if USE_RECONNECTION_MIS
        misEvalArgs.reconnectionMis = s.rcvMis;
        misEvalArgs.lightSubpathMis = caustic ? s.mis : s.lastVertex.mis;
        #endif

        /*{
            const uint2 cached = gPixelDebugPixel;
            printSetPixel(pixelCoord);
            print("     ConnectToCamera:", float4(f.mFwdPdfW, f.mRevPdfW, s.lastVertex.scatterFwdPdfW, s.lastVertex.scatterRevPdfW));
            printSetPixel(cached);
        }*/

        PathSuffix suffix = {};
        if (caustic) {
            // if the rcv is unconnectable, this is a caustic light path and we store the primary vertex as the rcv instead.
            suffix = PathSuffix::Create(
                s.throughput,
                1 / cameraPdfA,
                vertex.Pack(),
                vertex.GetDirIn(),
                dist,
                cosIn,
                misEvalArgs,
                LightSubpathData::Create(
                    s.lightSubpathVertex,
                    s.id,
                    s.bounces + 2,
                    s.diffuseBounces + 1,
                    s.pdfW
                ),
            );
        } else {
            suffix = PathSuffix::Create(
                s.throughputAtRcv,
                1,
                s.rcv,
                s.rcvDirOut,
                s.rcvDist,
                cosIn,
                misEvalArgs,
                LightSubpathData::Create(
                    s.lightSubpathVertex,
                    s.id,
                    s.bounces + 2,
                    s.diffuseBounces + 1,
                    s.pdfAtRcv
                )
            );
        }

        result = PathSample::Create(
            contrib,
            misWeight,
            s.bounces + 1,
            1,
            0,
            0,
            s.id,
            suffix,
            caustic ? PathFlags::eCausticLightPath : PathFlags::eNonCausticLightPath);

        return result;
    }

    PathSample EvalLightContribution<let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, out float integrationWeight) {
        integrationWeight = 0;
        PathSample result = {};

        if (DebugDisablePath(s.bounces, 0, s.rcvFound ? s.prefixBounces : s.bounces, false))
            return result;

        const float3 le = vertex.GetEmission();
        const float3 contrib = s.throughput * le;
        if (!any(contrib > 0))
            return result;

        // calculate mis weight
        float emissionPdfW = 0;
        float directPdfW = 0;
        float directPdfA = 0;
        if (gBidirectional || gSampleDirectLight)
            GetLightSamplePdf(vertex, s.lastVertex.position, s.lastVertex.normal, s.lastVertex.upperHemisphereOnly, emissionPdfW, directPdfW, directPdfA);

        // divide by pdf
        integrationWeight = 1 / s.pdfW;

        float misWeight = s.mis.EvalCameraTraceMIS(s.lastVertex.scatterFwdPdfW, directPdfA, directPdfW, emissionPdfW);
        MisEvalData misEvalArgs = {};
        #if USE_RECONNECTION_MIS
        misEvalArgs.reconnectionMis = s.rcvMis;
        misEvalArgs.cameraScatterFwdPdfW = s.lastVertex.scatterFwdPdfW;
        misEvalArgs.directPdfA = directPdfA;
        misEvalArgs.directPdfW = directPdfW;
        misEvalArgs.emissionPdfW = emissionPdfW;
        #endif

        PathSuffix suffix = {};
        const bool hasRcv = s.rcvFound;
        if (hasRcv) {
            // finalize the existing rcv
            float suffixPdf;
            float3 suffixContrib;
            if (s.bounces == s.prefixBounces + 1) {
                // rcv is the last vertex
                suffixPdf = 1;
                suffixContrib = le;
            } else {
                suffix.mDirOut = s.rcvDirOut;
                suffixPdf = s.pdfW / s.pdfAtRcv;
                suffixContrib = SafeDivide(contrib, s.throughputAtRcv);
            }

            suffix = PathSuffix::Create(
                suffixContrib,
                suffixPdf,
                s.rcv,
                s.rcvDirOut,
                s.rcvDist,
                s.rcvCos,
                misEvalArgs,
                LightSubpathData::Create(
                    {},
                    {},
                    0,
                    0,
                    0
                ) );
        }

        result = PathSample::Create(
            contrib,
            misWeight,
            s.bounces,
            hasRcv ? s.prefixPdf : s.pdfW,
            hasRcv ? s.prefixBounces : s.bounces,
            hasRcv ? s.rcvDiffuseBounces : s.diffuseBounces,
            s.id,
            suffix,
            PathFlags::eNone );
        return result;

    }

    // ---------------------------------------------------------------------------------------------------------
    // -------------------------------------------- Path generation --------------------------------------------
    // ---------------------------------------------------------------------------------------------------------

    PathState<bShift> InitializeCameraPath<let bShift : bool>(const PathId id, const PathVertex vertex) {
        PathState<bShift> s = {};
        s.id = id;
        s.isLightPath = false;

        s.sg     = MakeSampleGenerator(s.id.mId, s.id.mSeed);
        s.sgBsdf = MakeSampleGenerator(s.id.mId, -s.id.mSeed);

        s.bounces = 0;
        s.diffuseBounces = 0;
        s.prefixBounces = 0;
        s.rcvDiffuseBounces = 0;
        s.throughput = 1;
        s.throughputAtRcv = 0;
        s.prefixPdf = 0;
        s.rcvDirOut = 0;
        s.pdfW = 1;
        s.mis = RecursiveMisState(vertex);
        return s;
    }
    PathState<bShift> InitializeLightPath<let bShift : bool, let bSetPrimary : bool>( const PathId id, out PathVertex vertex, PackedHitInfo firstVertex = {}, const PackedPathVertex newPrimaryHit = {}) {
        PathState<bShift> s = {};
        s.id = id;
        s.isLightPath = true;

        s.throughput = 0;
        s.pdfW = 0;
        s.throughputAtRcv = 0;
        s.rcvDirOut = 0;

        s.sg     = MakeSampleGenerator(s.id.mId, s.id.mSeed);
        s.sgBsdf = MakeSampleGenerator(s.id.mId, -s.id.mSeed);

        vertex.mVertex = {};

        float cosLight = 0;
        float directPdfA = 0;
        float emissionPdfW = 0;
        Ray ray = {};
        PackedPathVertex l = {};
        {
            const bool useEnvMap = sampleNext1D(s.sg) < mParams.mEnvMapProb;
            const float4 sampleU = sampleNext4D(s.sg);

            if (gUseEnvLight && (!gUseEmissiveLights || useEnvMap || (bShift && !HitInfo(firstVertex).isValid()))) {
                EnvMapSample envSample;
                if (!mEnvMapSampler.sample(sampleU.xy, envSample))
                    return s;

                if (gUseEmissiveLights) envSample.pdf *= mParams.mEnvMapProb;

                if (bSetPrimary) {
                    float3 p = PathVertex(newPrimaryHit).ComputeRayOrigin(envSample.dir);
                    ray = Ray(p + mParams.mSceneSphere.w * envSample.dir, -envSample.dir);
                    ray.tMax = mParams.mSceneSphere.w*0.99;
                } else {
                    float3 t, b;
                    StableONB(envSample.dir, t, b);
                    const float2 uv = sample_disk_concentric(sampleU.zw);

                    ray = Ray(mParams.mSceneSphere.xyz + mParams.mSceneSphere.w * (t * uv.x + b * uv.y + envSample.dir), -envSample.dir);
                }
                l = PackedPathVertex(ray, HitInfo(0), FLT_MAX);
                s.throughput = envSample.Le;
                cosLight = 1;

                directPdfA = envSample.pdf;
                emissionPdfW = directPdfA * gConcentricDiscPdfA / sqr(mParams.mSceneSphere.w);
            } else if (gUseEmissiveLights && !(gUseEnvLight && useEnvMap)) {
                float selectionPdf;
                uint triangleIndex;
                float3 barycentrics;
                if (bShift) {
                    TriangleHit triHit = HitInfo(firstVertex).getTriangleHit();
                    triangleIndex = gScene.lightCollection.getTriangleIndex(triHit.instanceID, triHit.primitiveIndex);
                    if (triangleIndex != LightCollection::kInvalidIndex) {
                        // [Falcor 8] evalTriangleSelectionPdf now takes (pos, normal, upperOnly, triIdx).
                        // Power/Uniform samplers ignore the geometric args; LightBVH uses them.
                        // Light-subpath context has no shading point — pass neutral defaults.
                        selectionPdf = mEmissiveSampler.evalTriangleSelectionPdf(float3(0), float3(0, 0, 1), false, triangleIndex);
                        barycentrics = float3(1 - triHit.barycentrics.x - triHit.barycentrics.y, triHit.barycentrics);
                    }
                } else {
                    // [Falcor 8] sampleLight signature unified; only takes
                    // (pos, normal, upperOnly, sg, ls) overload now.
                    TriangleLightSample ls;
                    if (mEmissiveSampler.sampleLight(float3(0), float3(0, 0, 1), false, s.sg, ls)) {
                        triangleIndex = ls.triangleIndex;
                        selectionPdf = mEmissiveSampler.evalTriangleSelectionPdf(float3(0), float3(0, 0, 1), false, triangleIndex);
                        // [Falcor 8 bug fix] TriangleLightSample.uv is the RAW 2D random
                        // numbers (the u that drove the sample), NOT barycentric coordinates.
                        // The Falcor-7 port treated it as bary directly which biases the
                        // sample distribution (causes ~35% dim on VeachAjar — task #14).
                        barycentrics = sample_triangle(ls.uv);
                    } else {
                        triangleIndex = LightCollection::kInvalidIndex;
                        selectionPdf = 0;
                        barycentrics = 0;
                    }
                }

                if (triangleIndex == LightCollection::kInvalidIndex)
                    return s;

                if (gUseEnvLight) selectionPdf *= 1 - mParams.mEnvMapProb;

                let tri = gScene.lightCollection.getTriangle(triangleIndex);
                directPdfA = selectionPdf / tri.area;

                float dirPdfW;

                if (bSetPrimary) {
                    const float3 rayOrigin = computeRayOrigin(tri.getPosition(barycentrics), tri.normal);

                    PathVertex newVertex = PathVertex(newPrimaryHit);
                    float3 rayDir = newVertex.ComputeRayOrigin(rayOrigin - newVertex.GetPosition()) - rayOrigin;
                    const float dist = length(rayDir);
                    rayDir /= dist;

                    cosLight = dot(tri.normal, rayDir);
                    if (cosLight < kMinCosTheta) {
                        print("cosLight < kMinCosTheta", cosLight);
                        return s;
                    }
                    dirPdfW = CosHemispherePdfW(cosLight);
                    ray = Ray(rayOrigin, rayDir, 0, dist);
                } else {
                    const float3 localDir = sample_cosine_hemisphere_concentric(sampleU.zw, dirPdfW);
                    cosLight = localDir.z;

                    if (cosLight < kMinCosTheta)
                        return s;

                    float3 t, b;
                    StableONB(tri.normal, t, b);
                    const float3 rayDir = normalize(localDir.x * t + localDir.y * b + localDir.z * tri.normal);
                    const float3 rayOrigin = computeRayOrigin(tri.getPosition(barycentrics), tri.normal);
                    ray = Ray(rayOrigin, rayDir);
                }

                const MeshLightData meshData = gScene.lightCollection.getMeshData(triangleIndex);

                TriangleHit triHit = {};
                triHit.instanceID = { meshData.instanceID };
                triHit.primitiveIndex = triangleIndex - meshData.triangleOffset;
                triHit.barycentrics = barycentrics.yz;
                l = PackedPathVertex(ray, HitInfo(triHit), FLT_MAX);

                s.throughput = gScene.materials.evalEmissive(tri.materialID, tri.getTexCoord(barycentrics)) * cosLight;

                emissionPdfW = directPdfA * dirPdfW;
            } else {
                return s;
            }
        }

        const bool finiteEmitter = l.IsFinite();

        s.lightSubpathVertex = l.mPackedHit;
        s.lightSubpathId = s.id;

        s.pdfW = emissionPdfW;
        s.bounces = 0;
        s.diffuseBounces = 0;
        s.prefixBounces = 0;
        s.rcvDiffuseBounces = 0;

        s.mis = RecursiveMisState(finiteEmitter, directPdfA, emissionPdfW, cosLight);
        s.lastVertex.mis = s.mis;

        // set initial vertex as rcv
        s.rcv = l;
        s.rcv.mRayDirection = -s.rcv.mRayDirection;
        s.throughputAtRcv = s.throughput / cosLight;
        s.pdfAtRcv = directPdfA;
        s.rcvCos = cosLight;

        if (bSetPrimary) {
            if (Occluded(ray)) {
                print("Occluded", 0);
                s.Terminate();
                return s;
            }
            vertex = PathVertex(PackedPathVertex(ray, HitInfo(newPrimaryHit.mPackedHit), ray.tMax));
        } else
            vertex = PathVertex(TraceRay(ray));

        if (vertex.IsFinite()) {
            const float cosIn = vertex.GetCosN(ray.dir);
            if (cosIn < kMinCosTheta) {
                s.Terminate();
                return s;
            }

            s.mis.ProcessRay(vertex.mVertex.mRayDistance, cosIn, finiteEmitter);

            s.rcvDist = vertex.mVertex.mRayDistance;
        } else
            s.Terminate();

        return s;
    }

    void UpdateReconnectionData<let bShift : bool>(inout PathState<bShift> s, const PathVertex vertex, const bool connectable, const float lastPdfW) {
        if (gDisableEarlyReconnection)
            return;

        float cosIn = vertex.GetCosN(vertex.GetDirIn());

        // set vertex as rcv if one hasn't been found yet.
        if (!s.rcvFound && connectable) {
            s.rcv = vertex.Pack();
            if (!vertex.IsFinite()) s.rcv.mRayDistance = FLT_MAX;
            s.rcvCos = cosIn;
            s.rcvDist = s.rcv.mRayDistance;
            s.prefixBounces = s.bounces - 1;
            s.rcvDiffuseBounces = s.diffuseBounces - 1;
            s.prefixPdf = lastPdfW;
            // throughputAtRcv and rcvDirOut are assigned next iteration after a direction is sampled
        }

        // update rcvDirOut and throughputAtRcv if this vertex was selected as the rcv last iteration
        if (s.rcvFound && s.bounces == s.prefixBounces + 2) {
            if (s.lastVertex.connectable) {
                s.rcvDirOut = vertex.mVertex.mRayDirection;
                s.throughputAtRcv = s.throughput;
                s.pdfAtRcv = s.pdfW;
            } else {
                // rcv became unconnectable after BSDF sampling (sampled a delta lobe)
                s.prefixPdf = 0;
                s.prefixBounces = 0;
            }
        }

        #if USE_RECONNECTION_MIS
        if (gUseReconnectionMIS && s.rcvFound) {
            const float cosOut = s.lastVertex.HasNormal() ? abs(dot(s.lastVertex.normal, vertex.GetDirIn())) : 1;
            s.rcvMis.Update( s.mis,
                s.lastVertex.scatterFwdPdfW, s.lastVertex.scatterRevPdfW,
                cosIn, cosOut, vertex.mVertex.mRayDistance,
                int(s.bounces) - int(s.prefixBounces + 2) );
        }
        #endif
    }

    // Sample the BSDF and trace a ray to find the next vertex.
    // Updates throughput, pdfW, bounces, MIS quantities, and reconnection data
    // returns sampled LobeType
    uint AdvanceVertex<let bShift : bool, let bSetNext : bool>(inout PathState<bShift> s, inout PathVertex vertex, const PathVertex nextVertex) {
        // russian roulette
        const float contProb = vertex.GetContinuationProbability();
        const float rrU = sampleNext1D(s.sg);
        if (!bShift && contProb < 1 && rrU > contProb) {
            s.Terminate();
            return 0;
        }

        // sample direction
        DirectionSampleData r = vertex.SampleDirection(s.sgBsdf, s.isLightPath);

        if (bSetNext) {
            r.mDirection = nextVertex.mVertex.mRayDirection;
            r.SetReflectance(vertex.EvaluateReflectance(s.sg, r.mDirection, s.isLightPath));
            r.mLobeType = vertex.mMaterial.getLobeTypes(vertex.mShadingData) & ~uint(LobeType::Delta);
        }

        if (gBidirectional && gDisableCameraConnection && !s.isLightPath && s.bounces == 1)
            r.mRevPdfW = 0;

        // cache this vertex
        s.lastVertex.position            = vertex.GetPosition();
        s.lastVertex.normal              = vertex.HasFaceNormal() ? vertex.GetFaceNormal() : 0;
        s.lastVertex.upperHemisphereOnly = vertex.UpperHemisphereOnly();
        s.lastVertex.scatterFwdPdfW      = r.IsLobe(LobeType::Delta) ? 0 : r.mFwdPdfW;
        s.lastVertex.scatterRevPdfW      = r.mRevPdfW;
        s.lastVertex.mis = s.mis;
        const float lastPdfW = s.pdfW;

        // modify throughput and pdfW
        s.throughput *= r.mReflectance;
        if (r.mFwdPdfW > 0)
            s.pdfW *= r.mFwdPdfW;

        const float cosOut = vertex.GetCosN(r.mDirection);

        if (cosOut < kMinCosTheta || !any(s.throughput > 0) || any(s.throughput != s.throughput) || !(s.pdfW > 0)) {
            s.Terminate();
            return 0;
        }

        const bool connectable = r.IsLobe(LobeType::Diffuse) || (r.IsLobe(LobeType::Specular) && vertex.mMaterial.getProperties(vertex.mShadingData).roughness >= mParams.mReconnectionRoughness);
        s.lastVertex.connectable = connectable;

        // diffuse bounce limit
        if (connectable && s.diffuseBounces == mParams.mMaxDiffuseBounces) {
            s.Terminate();
            return 0;
        }

        // update mis quantities
        s.mis.ProcessDirection(r, cosOut, connectable);

        // trace ray to find next vertex
        if (bSetNext) {
            vertex = nextVertex;
        } else {
            vertex = PathVertex(TraceRay(Ray(vertex.ComputeRayOrigin(r.mDirection), r.mDirection)));
        }
        s.bounces++;
        if (connectable)
            s.diffuseBounces++;

        const float cosIn = vertex.GetCosN(vertex.GetDirIn());

        if (cosIn < kMinCosTheta) {
            s.Terminate();
            return 0;
        }

        s.mis.ProcessRay(vertex.mVertex.mRayDistance, cosIn);

        if (!s.isLightPath) {
            const bool canReconnect = connectable && vertex.mVertex.mRayDistance >= mParams.mReconnectionDistance && (vertex.IsConnectable() || any(vertex.GetEmission() > 0));
            UpdateReconnectionData(s, vertex, canReconnect, lastPdfW);
        }

        return r.mLobeType;
    }

    uint SampleNextVertex<let bShift : bool>(inout PathState<bShift> s, inout PathVertex vertex) {
        PathVertex tmp;
        return AdvanceVertex<bShift, false>(s, vertex, tmp);
    }

    // Does everything SampleNextVertex does, but discards the sampled direction and instead sets the next vertex explicitly
    void SetNextVertex<let bShift : bool>( inout PathState<bShift> s, inout PathVertex vertex, const PathVertex nextVertex ) {
        AdvanceVertex<bShift, true>(s, vertex, nextVertex);
    }
}

// ---------------------------------------------------------------------------------------------------------
// ----------------------------------------------- Top-level -----------------------------------------------
// ---------------------------------------------------------------------------------------------------------

extension PathGenerator {
    // Sample a light subpath. Updates the LVC/photon map. Connects connectable vertices to the camera directly.
    void SampleLightPath(const PathId id) {
        if (mParams.mMaxBounces == 0 || mParams.mMaxDiffuseBounces == 0)
            return;

        if (gDisableLVC) mLightVertexCache.lightVertexCount[id.mId.y * mParams.mOutputDim.x + id.mId.x] = 0;

        PathVertex vertex;
        PathState<false> s = InitializeLightPath<false, false>(id, vertex);

        while (any(s.throughput > 0) && s.pdfW > 0 && vertex.IsFinite() && s.bounces + 1 <= mParams.mMaxBounces && s.diffuseBounces + 1 <= mParams.mMaxDiffuseBounces) {
            const bool connectable = vertex.IsConnectable();
            if (connectable) {
                // store light vertex for subpath connection
                if (!gLightTraceOnly && !gDisableVC) {
                    const LightSubpathVertex v = PackLightSubpathVertex(s, vertex);

                    if (s.bounces + 2 <= mParams.mMaxBounces) {
                        uint i;
                        if (gDisableLVC) {
                            i = id.mId.y * mParams.mOutputDim.x + id.mId.x;

                            const uint b = mLightVertexCache.lightVertexCount[i];
                            mLightVertexCache.lightVertexCount[i] = b + 1;

                            i += b * mParams.mOutputDim.x * mParams.mOutputDim.y;
                            // [Slang 2024.14] __subscript set is no longer an l-value here; write through the underlying RWStructuredBuffer.
                            mLightVertexCache.lightVertices[i] = v;
                        } else {
                            i = mLightVertexCache.Insert(v);
                        }
                    }
                }

                // form a full path by connecting camera vertex to the camera
                if (!gDisableCameraConnection) {
                    float weight = 0;
                    int2 pixelCoord;
                    const PathSample ps = ConnectToCamera(s, vertex, pixelCoord, weight);
                    if (ps.IsValid() && weight > 0 && all(pixelCoord >= 0) && all(pixelCoord < mParams.mOutputDim)) {
                        DebugSetPixel(pixelCoord);
                        if (!gUseResampling)
                        {
                            print("Found path. contrib:", luminance(ps.mContribution) * ps.mMisWeight);
                            print("\tW:", weight);
                            print("\tLight subpath vertices:", ps.mSuffix.mLightSubpath.mVertexCount);
                            print("\tPrefix bounces:", ps.mPrefixBounces);
                            print("\trcv dist:", s.rcvDist);
                            print("\tcaustic:", ps.HasFlag(PathFlags::eCausticLightPath));
                        }
                        DebugSetPixel(-1);

                        const uint flatId = pixelCoord.y * mParams.mOutputDim.x + pixelCoord.x;
                        if (gUseResampling) {
                            // store path reservoirs for each pixel in a hash map
                            // these reservoirs are merged into each pixel's reservoir in a later pass
                            LightTraceReservoir r = {};
                            r.path = ps;
                            r.W = weight;
                            mLightTraceReservoirs.Insert(flatId, r);
                        } else {
                            // splat radiance onto output directly, instead of using reservoirs
                            // [Falcor 8 port] InterlockedAddF32 needs NVAPI which is not
                            // built in this tree. Use CAS-based float atomic-add instead.
                            const float3 v = ps.mContribution * (weight * ps.mMisWeight);
                            const uint base = flatId * 12u; // 3*sizeof(float)
                            for (int c = 0; c < 3; ++c) {
                                const uint addr = base + uint(c) * 4u;
                                uint origU = mAtomicRadiance.Load(addr);
                                [allow_uav_condition] for (uint iter = 0; iter < 16u; ++iter) {
                                    const uint cmpU = origU;
                                    const float sum = asfloat(cmpU) + v[c];
                                    mAtomicRadiance.InterlockedCompareExchange(addr, cmpU, asuint(sum), origU);
                                    if (origU == cmpU) break;
                                }
                            }
                        }
                    }
                }
            }

            if (s.bounces + 1 == mParams.mMaxBounces)
                break;

            // for light paths: rcv is always the 2nd to last vertex
            s.rcv = vertex.Pack();
            s.rcvDirOut = vertex.GetDirIn();
            s.throughputAtRcv = s.throughput;
            s.pdfAtRcv = s.pdfW;
            s.prefixPdf = s.pdfW;
            s.prefixBounces = 0;
            s.rcvDiffuseBounces = 0;

            SampleNextVertex(s, vertex);

            s.rcvCos = abs(dot(s.lastVertex.normal, vertex.mVertex.mRayDirection));
            s.rcvDist = vertex.mVertex.mRayDistance;
            s.deltaRcv = !s.lastVertex.connectable;
        }
    }

    // Samples a canonical camera path by connecting to lights, light subpath vertices, and merging with photons.
    PathReservoir SampleCanonicalPaths(const PathId id) {
        PathVertex vertex = PathVertex(LoadPrimaryVertex(id.mId));

        // directly output primary radiance
        mOutputRadiance[id.mId] = float4(vertex.GetEmission(), 1);

        if (gLightTraceOnly || !vertex.IsFinite())
            return {};

        PathReservoir r = {};
        r.mM = mParams.mCanonicalSpp;

        for (uint i = 0; i < mParams.mCanonicalSpp; i++) {
            if (i > 0) vertex = PathVertex(LoadPrimaryVertex(id.mId));

            PathState<false> s = InitializeCameraPath<false>(PathId(id.mSeed + i, id.mId), vertex);

            while (s.bounces < mParams.mMaxBounces && any(s.throughput > 0) && s.pdfW > 0 && vertex.IsFinite()) {
                if (vertex.IsConnectable() && s.diffuseBounces < mParams.mMaxDiffuseBounces) {
                    if ((gBidirectional || gSampleDirectLight)) {
                        // connect to a random light (env / emissive)
                        float weight = 0;
                        const PathSample ps = ConnectToLight(s, vertex, weight);
                        ProcessSample(r, s.sg, ps, weight);

                        // [Bug #3 fix] also connect to a random analytic light
                        // (point / directional / spot). BDPT's ConnectToLight
                        // doesn't sample analytic lights at all — separate call.
                        if (gUseAnalyticLights) {
                            float analWeight = 0;
                            const PathSample analPs = ConnectToAnalyticLight(s, vertex, analWeight);
                            ProcessSample(r, s.sg, analPs, analWeight);
                        }
                    }

                    if (gBidirectional) {
                        if (gBidirectional && !gDisableVC) {
                            if (gDisableLVC) {
                                uint i = id.mId.y * mParams.mOutputDim.x + id.mId.x;
                                const uint count = mLightVertexCache.lightVertexCount[i];
                                //*
                                // pick a random light vertex and weight it by 'count'
                                const uint b = min(uint(sampleNext1D(s.sg) * count), count - 1);
                                /*/
                                // connect to light subpath vertices
                                for (uint b = 0; b < count; b++)
                                //*/
                                {
                                    const LightSubpathVertex v = mLightVertexCache[i + b*mParams.mOutputDim.x * mParams.mOutputDim.y];
                                    float weight = 0;
                                    PathSample ps = ConnectToLightSubpath(s, vertex, v, weight);
                                    ProcessSample(r, s.sg, ps, weight * count);
                                }
                            } else {
                                // connect to a random light subpath vertex in the LVC
                                const uint count = mLightVertexCache.size();
                                if (count > 0) {
                                    const LightSubpathVertex v = mLightVertexCache[min(uint(sampleNext1D(s.sg) * count), count - 1)];

                                    float weight = 0;
                                    PathSample ps = ConnectToLightSubpath(s, vertex, v, weight);
                                    ProcessSample(r, s.sg, ps, weight * (count / (float)mParams.mLightSubpathCount));
                                }
                            }
                        }
                    }
                }

                // sample direction and trace ray
                SampleNextVertex(s, vertex);

                // add emission from new vertex
                {
                    float weight = 0;
                    const PathSample ps = EvalLightContribution(s, vertex, weight);
                    if (ps.IsValid())
                        ProcessSample(r, s.sg, ps, weight);
                }
            }
        }

        r.mW /= mParams.mCanonicalSpp;

        if (!gUseResampling) {
            mOutputRadiance[id.mId].rgb += r.mSample.mContribution / mParams.mCanonicalSpp;
        }

        r.FinalizeMerge();
        return r;
    }
}

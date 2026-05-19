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
#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "Utils/Debug/PixelDebug.h"
#include "Utils/Sampling/SampleGenerator.h"
#include "Rendering/Lights/LightBVHSampler.h"
#include "Rendering/Lights/EmissivePowerSampler.h"
#include "Rendering/Lights/EnvMapSampler.h"
#include "Rendering/Materials/TexLODTypes.slang"
#include "Rendering/Utils/PixelStats.h"
#include "Rendering/RTXDI/RTXDI.h"

#include "Params.slang"

using namespace Falcor;

/** Fast path tracer.
*/
class ReSTIRDIPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ReSTIRDIPass, "ReSTIRDIPass", "Reference path tracer.");

    static ref<ReSTIRDIPass> create(ref<Device> pDevice, const Properties& props) { return make_ref<ReSTIRDIPass>(pDevice, props); }

    ReSTIRDIPass(ref<Device> pDevice, const Properties& props);

    virtual void setProperties(const Properties& props) override;
    virtual Properties getProperties() const override;
    virtual RenderPassReflection reflect(const CompileData& compileData) override;
    virtual void setScene(RenderContext* pRenderContext, const ref<Scene>& pScene) override;
    virtual void execute(RenderContext* pRenderContext, const RenderData& renderData) override;
    virtual void renderUI(Gui::Widgets& widget) override;
    virtual bool onMouseEvent(const MouseEvent& mouseEvent) override;
    virtual bool onKeyEvent(const KeyboardEvent& keyEvent) override { return false; }

    PixelStats& getPixelStats() { return *mpPixelStats; }

    void reset();

    static void registerBindings(pybind11::module& m);

private:
    struct TracePass
    {
        std::string name;
        std::string passDefine;
        ref<Program> pProgram;
        ref<RtBindingTable> pBindingTable;
        ref<RtProgramVars> pVars;

        TracePass(ref<Device> pDevice, const std::string& name, const std::string& passDefine, const ref<Scene>& pScene, const DefineList& defines, const TypeConformanceList& globalTypeConformances);
        static std::unique_ptr<TracePass> create(ref<Device> pDevice, const std::string& name, const std::string& passDefine, const ref<IScene>& pScene, const DefineList& defines, const TypeConformanceList& globalTypeConformances)
        {
            if (auto scene = dynamic_ref_cast<Scene>(pScene))
                return std::make_unique<TracePass>(std::move(pDevice), name, passDefine, std::move(scene), defines, globalTypeConformances);
            return {};
        }

        void prepareProgram(ref<Device> pDevice, const DefineList& defines);
    };

    void parseProperties(const Properties& props);
    void validateOptions();
    void resetPrograms();
    void updatePrograms();
    void setFrameDim(const uint2 frameDim);
    void prepareResources(RenderContext* pRenderContext, const RenderData& renderData);
    void prepareReSTIRDIPass(const RenderData& renderData);
    void resetLighting();
    void prepareMaterials(RenderContext* pRenderContext);
    bool prepareLighting(RenderContext* pRenderContext);
    void prepareRTXDI(RenderContext* pRenderContext);
    void setNRDData(const ShaderVar& var, const RenderData& renderData) const;
    void bindShaderData(const ShaderVar& var, const RenderData& renderData, bool useLightSampling = true) const;
    bool renderRenderingUI(Gui::Widgets& widget);
    bool renderDebugUI(Gui::Widgets& widget);
    void renderStatsUI(Gui::Widgets& widget);
    bool beginFrame(RenderContext* pRenderContext, const RenderData& renderData);
    void endFrame(RenderContext* pRenderContext, const RenderData& renderData);
    void generatePaths(RenderContext* pRenderContext, const RenderData& renderData);
    void tracePass(RenderContext* pRenderContext, const RenderData& renderData, TracePass& tracePass);
    void resolvePass(RenderContext* pRenderContext, const RenderData& renderData);

    /** Static configuration. Changing any of these options require shader recompilation.
    */
    struct StaticParams
    {
        // Rendering parameters
        uint32_t    samplesPerPixel = 1;                        ///< Number of samples (paths) per pixel, unless a sample density map is used.
        uint32_t    maxSurfaceBounces = 0;                      ///< Max number of surface bounces (diffuse + specular + transmission), up to kMaxPathLenth. This will be initialized at startup.
        uint32_t    maxDiffuseBounces = 3;                      ///< Max number of diffuse bounces (0 = direct only), up to kMaxBounces.
        uint32_t    maxSpecularBounces = 3;                     ///< Max number of specular bounces (0 = direct only), up to kMaxBounces.
        uint32_t    maxTransmissionBounces = 10;                ///< Max number of transmission bounces (0 = none), up to kMaxBounces.

        // Sampling parameters
        uint32_t    sampleGenerator = SAMPLE_GENERATOR_TINY_UNIFORM; ///< Pseudorandom sample generator type.
        bool        useBSDFSampling = true;                     ///< Use BRDF importance sampling, otherwise cosine-weighted hemisphere sampling.
        bool        useRussianRoulette = false;                 ///< Use russian roulette to terminate low throughput paths.
        bool        useNEE = true;                              ///< Use next-event estimation (NEE). This enables shadow ray(s) from each path vertex.
        bool        useMIS = true;                              ///< Use multiple importance sampling (MIS) when NEE is enabled.
        MISHeuristic misHeuristic = MISHeuristic::Balance;      ///< MIS heuristic.
        float       misPowerExponent = 2.f;                     ///< MIS exponent for the power heuristic. This is only used when 'PowerExp' is chosen.
        EmissiveLightSamplerType emissiveSampler = EmissiveLightSamplerType::LightBVH;  ///< Emissive light sampler to use for NEE.
        bool        useRTXDI = false;                           ///< Use RTXDI for direct illumination.
        bool        useRestirPT = false;                        ///< Enable ReSTIR-PT path-reservoir reuse (restirpt_2d). v1: per-pixel addressing, parity target = Source/RenderPasses/ReSTIRPTPass/.

        // Bias correction mode for temporal+spatial reservoir merges.
        // 0 = Bitterli basic (M-weighted) — current default; cheap but
        //     unstable when merging across surfaces with mismatched pHat.
        // 1 = Pairwise MIS (Boksansky 2022 / RTXDI BiasCorrection::Pairwise) —
        //     adds Talbot m_j weight using stored neighbour pHat; load-
        //     bearing for cell reservoir reuse.
        uint32_t    biasCorrection = 0;

        // Category-quota K-RIS candidate counts (RTXDI parity:
        // RTXDI_SampleLightsForSurface splits its initial budget across
        // 4 dedicated sub-reservoirs — local emissive / infinite analytic /
        // environment map / BRDF — instead of routing one shared candidate
        // stream through uniform selectLightType). When any of these is
        // non-zero, generateInitialCandidatesFresh() runs ADDITIONAL
        // dedicated loops on top of the gInitialCandidates uniform stream,
        // matching RTXDI's defaults: 8 env + 8 inf + 1 BRDF.
        //
        // Defaults are 0 to preserve legacy F-K_pool baselines. To match
        // RTXDI K=41 exactly, set initialCandidates=0 (skip uniform stream)
        // + envCandidates=8 + infiniteCandidates=8 + brdfCandidates=1 +
        // cellPoolDrawK=24.
        //
        // Bistro/Sponza rmse gap analysis (2026-05-15): scenes with env-map
        // + directional sun trail RTXDI rmse by 6–21% under F17P24. Uniform
        // selectLightType (1/3 prob per category) gives ~6 env + ~6 inf
        // samples vs RTXDI's 8 each — undersampled by 33%, plus we lack
        // BRDF sampling. See .agents/handoff entry 2026-05-15.
        uint32_t    envCandidateCount      = 0;
        uint32_t    infiniteCandidateCount = 0;
        uint32_t    brdfCandidateCount     = 0;

        // Material parameters
        bool        useAlphaTest = true;                        ///< Use alpha testing on non-opaque triangles.
        bool        adjustShadingNormals = false;               ///< Adjust shading normals on secondary hits.
        uint32_t    maxNestedMaterials = 2;                     ///< Maximum supported number of nested materials.
        bool        useLightsInDielectricVolumes = false;       ///< Use lights inside of volumes (transmissive materials). We typically don't want this because lights are occluded by the interface.
        bool        disableCaustics = false;                    ///< Disable sampling of caustics.
        TexLODMode  primaryLodMode = TexLODMode::Mip0;          ///< Use filtered texture lookups at the primary hit.

        // Scheduling parameters
        bool        useSER = true;                              ///< Enable SER (Shader Execution Reordering).

        // Output parameters
        ColorFormat colorFormat = ColorFormat::LogLuvHDR;       ///< Color format used for internal per-sample color and denoiser buffers.

        // Denoising parameters
        bool        useNRDDemodulation = true;                  ///< Global switch for NRD demodulation.

        DefineList getDefines(const ReSTIRDIPass& owner) const;
    };

    // Configuration
    PathTracerParams                mParams;                    ///< Runtime path tracer parameters.
    StaticParams                    mStaticParams;              ///< Static parameters. These are set as compile-time constants in the shaders.
    mutable LightBVHSampler::Options mLightBVHOptions;          ///< Current options for the light BVH sampler.
    RTXDI::Options                  mRTXDIOptions;              ///< Current options for the RTXDI sampler.

    bool                            mEnabled = true;            ///< Switch to enable/disable the path tracer. When disabled the pass outputs are cleared.
    RenderPassHelpers::IOSize       mOutputSizeSelection = RenderPassHelpers::IOSize::Default;  ///< Selected output size.
    uint2                           mFixedOutputSize = { 512, 512 };                            ///< Output size in pixels when 'Fixed' size is selected.

    bool                            mSERSupported = false;      ///< True if the device supports SER.

    // Internal state
    ref<IScene>                     mpScene;                    ///< The current scene, or nullptr if no scene loaded.
    ref<SampleGenerator>            mpSampleGenerator;          ///< GPU pseudo-random sample generator.
    std::unique_ptr<EnvMapSampler>  mpEnvMapSampler;            ///< Environment map sampler or nullptr if not used.
    std::unique_ptr<EmissiveLightSampler> mpEmissiveSampler;    ///< Emissive light sampler or nullptr if not used.
    std::unique_ptr<RTXDI>          mpRTXDI;                    ///< RTXDI sampler for direct illumination or nullptr if not used.
    std::unique_ptr<PixelStats>     mpPixelStats;               ///< Utility class for collecting pixel stats.
    std::unique_ptr<PixelDebug>     mpPixelDebug;               ///< Utility class for pixel debugging (print in shaders).

    sigs::Connection                mUpdateFlagsConnection; ///< Connection to the UpdateFlags signal.
    /// SceneUpdateFlags accumulated since last `beginFrame()`
    IScene::UpdateFlags             mUpdateFlags = IScene::UpdateFlags::None;

    ref<ParameterBlock>             mpPathTracerBlock;          ///< Parameter block for the path tracer.

    bool                            mRecompile = false;         ///< Set to true when program specialization has changed.
    bool                            mVarsChanged = true;        ///< This is set to true whenever the program vars have changed and resources need to be rebound.
    bool                            mOptionsChanged = false;    ///< True if the config has changed since last frame.
    bool                            mGBufferAdjustShadingNormals = false; ///< True if GBuffer/VBuffer has adjusted shading normals enabled.
    bool                            mFixedSampleCount = true;   ///< True if a fixed sample count per pixel is used. Otherwise load it from the pass sample count input.
    bool                            mCellPoolFillOnly = false; ///< §9.4 Step (b): when true, this PathTracer instance only fills the
                                                                 ///< WS cell pool (K-RIS + insert) and skips shading. Used as a pre-pass
                                                                 ///< before the main render PathTracer instance reads the populated pool.
    bool                            mOutputGuideData = false;   ///< True if guide data should be generated as outputs.
    bool                            mOutputNRDData = false;     ///< True if NRD diffuse/specular data should be generated as outputs.
    bool                            mOutputNRDAdditionalData = false;   ///< True if NRD data from delta and residual paths should be generated as designated outputs rather than being included in specular NRD outputs.

    ref<ComputePass>                mpGeneratePaths;            ///< Fullscreen compute pass generating paths starting at primary hits.
    ref<ComputePass>                mpResolvePass;              ///< Sample resolve pass.
    ref<ComputePass>                mpReflectTypes;             ///< Helper for reflecting structured buffer types.

    std::unique_ptr<TracePass>      mpTracePass;                ///< Main trace pass.
    std::unique_ptr<TracePass>      mpTraceDeltaReflectionPass; ///< Delta reflection trace pass (for NRD).
    std::unique_ptr<TracePass>      mpTraceDeltaTransmissionPass;   ///< Delta transmission trace pass (for NRD).

    ref<Texture>                    mpSampleOffset;             ///< Output offset into per-sample buffers to where the samples for each pixel are stored (the offset is relative the start of the tile). Only used with non-fixed sample count.
    ref<Buffer>                     mpSampleColor;              ///< Compact per-sample color buffer. This is used only if spp > 1.
    ref<Buffer>                     mpSampleGuideData;          ///< Compact per-sample denoiser guide data.
    ref<Buffer>                     mpSampleNRDRadiance;        ///< Compact per-sample NRD radiance data.
    ref<Buffer>                     mpSampleNRDHitDist;         ///< Compact per-sample NRD hit distance data.
    ref<Buffer>                     mpSampleNRDPrimaryHitNeeOnDelta;///< Compact per-sample NEE on delta primary vertices data.
    ref<Buffer>                     mpSampleNRDEmission;        ///< Compact per-sample NRD emission data.
    ref<Buffer>                     mpSampleNRDReflectance;     ///< Compact per-sample NRD reflectance data.

    // VisCache integration — hash table + cbuffer from InternalDictionary.
    ref<Buffer> mpVHFTable;      ///< RWStructuredBuffer<VHFEntry> — the hash table
    ref<Buffer> mpVHFParamsCB;   ///< cbuffer VisCacheParams — bound directly to keep struct in sync
    bool mVisCacheAvailable = false;
    bool mVisCacheVisibilityCheck = false;  ///< CV+RRR gating for shadow rays
    bool mVisCacheLightSelection = false;   ///< §9.1 cached μ in NEE target p̂ (composes with WS-ReSTIR)
    bool mVisCacheDirDistAddr = false;      ///< G: dir+dist addressing (vs endpoint pairs)
    uint32_t mVisCacheBayerN = 1;           ///< Bayer N×N gate (1=full frame, 2=2×2/4 subframes, 4=4×4/16 subframes); see Falcor/LOCAL_FIXES.md #14

    // Cached cbuffer values — bound per-member because Falcor 8 ParameterBlock
    // doesn't support whole-buffer cbuffer binding.
    struct { uint32_t tableCapacity=0, bootThreshold=0, matureThreshold=0; float varThreshold=0, pMin=0, fireflyBudget=0;
             uint32_t numLevels=0, flags=1;
             float posACoarse=0, posAFine=0, posBCoarse=0, posBFine=0;
             float dirBCoarse=0, dirBFine=0, distBCoarse=0, distBFine=0;
             float normalACoarse=0;
             float bootThresholdFactorFootprintPx=0;
             uint32_t forceDescendFootprintPx=0;
             uint32_t cascadeWindowForward=12;
             float stderrThreshold=0;
             uint32_t enableHierarchicalConsistency=0;
             float hierarchicalMuTolerance=0.2f;
             float accelDecayDisagreeThresh=0;
             uint32_t mlAlphaFloorN=0;
             uint32_t bootThresholdFine=0;
             float jitterFilter=0, jitterCell=0;
             uint32_t frameCount=0, spp=1;
             float cameraPosX=0, cameraPosY=0, cameraPosZ=0;
             float pixelSize1=0.001f;
             uint32_t bayerN=1, warmupFirst=0, warmupRun=0;
             // §9.4 WS-ReSTIR DI cbuffer fields
             uint32_t enable=0;
             uint32_t cellLevelJitter=0u;
             uint32_t capacity=0;
             float    mCap=30.f;
             uint32_t spatialNeighbours=4;
             float    lightMuMin=0.01f;
             uint32_t initialCandidates=8;
             // (jitter* removed — shares VisCache's gJitterFilter / gJitterCell)
             uint32_t visInPHat=1;
             // §9.4 WS-cascade ReGIR cell pool
             uint32_t cellPoolCapacity=0;
             uint32_t cellPoolDrawK=0;
             uint32_t spatialPixelsK=4;
             uint32_t spatialPixelsRadius=32;
             uint32_t poolAddrMode=0;
             uint32_t poolTileSize=16;
             uint32_t cellPoolMode=0;        // 0 = P3d, 1 = PR3d
             float    dirSolidAngleScale=1.0f;
             float    distSolidAngleScale=1.0f;
             uint32_t cellReservoirMerge=0;
             uint32_t cellPoolFootprintPx=0;
             uint32_t cellReservoirFootprintPx=0;
             uint32_t retraceOnReuseMode=0; } mVCParams;

    // §9.4 WS-ReSTIR DI buffers (sourced from VisCache via dict).
    ref<Buffer> mpVHFReservoirs;
    ref<Buffer> mpVHFPixelReservoirs;          ///< Per-pixel temporal reservoir buffer.
    ref<Buffer> mpVHFCellPools;              ///< Multi-light cell pool — header (fingerprint, count).
    ref<Buffer> mpVHFCellPoolSlots;          ///< Multi-light cell pool — flat slot buffer (split for DXC at N=1024).
    uint32_t    mVHFPixelDimX = 0u;
    uint32_t    mVHFPixelDimY = 0u;
    bool        mVisCacheReservoirs = false; ///< Master gate read from dict.

    // VisCache diagnostics — bound at root var level (PixelStats pattern) so all
    // RT stages (raygen/closestHit/miss/anyHit) can write per-pixel heatmap data.
    bool mVisCacheDiagnostics = false;
    ref<Texture> mpVCAccumMeanVarMatCount, mpVCFrameMeanVarMatSamplesRaw, mpVCFrameLevelProbesSamplesCold, mpVCFrameHashAHashBHashABRays;
    ref<Texture> mpVCAccumSaved, mpVCAccumTotal, mpVCAccumRaysNoiseErrorCold;
};

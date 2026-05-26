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
#include <fstream>

#include "Params.slang"

using namespace Falcor;

/** Vanilla bidirectional path tracer.

    Extracted from ReSTIRBDPTPass as a baseline analogous to Falcor's
    built-in PathTracer (which is the baseline for ReSTIRPTPass /
    ReSTIRDIPass). Forces the ReSTIR resampling / temporal / caustic
    layers off so only the BDPT estimator runs: light subpaths +
    camera subpaths + deterministic MIS-weighted vertex connections.
*/
class BDPT : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(BDPT, "BDPT", "Vanilla bidirectional path tracer (extracted from ReSTIR-BDPT).");

    static ref<BDPT> create(ref<Device> pDevice, const Properties& props) { return make_ref<BDPT>(pDevice, props); }

    BDPT(ref<Device> pDevice, const Properties& props);

    virtual void setProperties(const Properties& props) override;
    virtual Properties getProperties() const override;
    virtual RenderPassReflection reflect(const CompileData& compileData) override;
    virtual void setScene(RenderContext* pRenderContext, const ref<Scene>& pScene) override;
    virtual void execute(RenderContext* pRenderContext, const RenderData& renderData) override;
    virtual void renderUI(Gui::Widgets& widget) override;
    virtual bool onMouseEvent(const MouseEvent& mouseEvent) override;
    virtual bool onKeyEvent(const KeyboardEvent& keyEvent) override;

    void reset();

    static void registerBindings(pybind11::module& m);

private:
    void parseProperties(const Properties& props);
    void validateOptions();
    void resetPrograms();
    void updatePrograms();
    void setFrameDim(const uint2 frameDim);
    void prepareResources(RenderContext* pRenderContext, const RenderData& renderData);
    void resetLighting();
    void prepareMaterials(RenderContext* pRenderContext);
    bool prepareLighting(RenderContext* pRenderContext);
    void bindShaderData(const ShaderVar& var, const RenderData& renderData) const;
    void preparePass(RenderContext* pRenderContext, const RenderData& renderData, ComputePass& pass) const;
    bool renderRenderingUI(Gui::Widgets& widget);
    bool renderDebugUI(Gui::Widgets& widget);
    bool beginFrame(RenderContext* pRenderContext, const RenderData& renderData);
    void endFrame(RenderContext* pRenderContext, const RenderData& renderData);

    /** Static configuration. Changing any of these options require shader recompilation.
    */
    struct StaticParams
    {
        // Sampling parameters
        uint32_t    sampleGenerator = SAMPLE_GENERATOR_TINY_UNIFORM;
        float       misPowerExponent = 2;
        bool        useBsdfImportanceSampling = true;
        bool        useNEE = true;                    ///< Use next-event estimation (NEE). This enables shadow ray(s) from each path vertex.
        bool        useBPT = true;                    ///< Use bidirectional path tracing. Automatically enables NEE.
        bool        lightTraceOnly = false;
        bool        disableCameraConnection = false;
        bool        debugBPT = false;
        bool        debugHeatmap = false;
        bool        disableVC = false;
        bool        disableLVC = false;
        // [strip-ReSTIR task #21] Removed ReSTIR-only fields:
        //   useResampling, useTemporalReuse, unbiasedTemporalReuse,
        //   useCausticReservoirs, useCausticShift, shiftSuffixes,
        //   shiftSuffixesSpatial, spatialReusePasses, spatialRMIS,
        //   shiftLightPathsToPixelCenters, debugCausticReservoirs,
        //   disableEarlyReconnection, reconnectionMIS.
        // Those live in ReSTIRBDPTPass::StaticParams.

        EmissiveLightSamplerType emissiveSampler = EmissiveLightSamplerType::Power;

        DefineList getDefines(const BDPT& owner) const;
    };

    // Configuration
    PathGeneratorParams             mParams;                    ///< Runtime path tracer parameters.
    StaticParams                    mStaticParams;              ///< Static parameters. These are set as compile-time constants in the shaders.
    mutable LightBVHSampler::Options mLightBVHOptions;          ///< Current options for the light BVH sampler.

    bool                            mEnabled = true;            ///< Switch to enable/disable the path tracer. When disabled the pass outputs are cleared.
    bool                            mPauseRendering  = false;
    bool                            mRenderOnce      = false;
    bool                            mRenderOnceSceneUpdated = false;
    bool                            mKeepFrameIndex = false;
    bool                            mFreezeHistory = false;

    uint                            mFrameCount = 0;
    uint                            mFixedSeed = 0;
    bool                            mUseFixedSeed = false;
    bool                            mSwapReservoirs = false;
    bool                            mUsePerFrameSeed = false;
    uint                            mCurrentSeed = 0;
    bool                            mResetTemporalHistory = false;

    std::filesystem::path           mCameraPosOutputFile;
    std::ofstream                   mCameraPosOutputStream;

    // Internal state
    ref<Scene>                      mpScene;                     ///< The current scene, or nullptr if no scene loaded.
    ref<SampleGenerator>            mpSampleGenerator;           ///< GPU pseudo-random sample generator.
    std::unique_ptr<EnvMapSampler>  mpEnvMapSampler;             ///< Environment map sampler or nullptr if not used.
    std::unique_ptr<EmissiveLightSampler> mpEmissiveSampler;     ///< Emissive light sampler or nullptr if not used.
    std::unique_ptr<PixelDebug>     mpPixelDebug;                ///< Utility class for pixel debugging (print in shaders).

    bool                            mRecompile = false;          ///< Set to true when program specialization has changed.
    bool                            mVarsChanged = true;         ///< This is set to true whenever the program vars have changed and resources need to be rebound.
    bool                            mOptionsChanged = false;     ///< True if the config has changed since last frame.

    ref<ComputePass>                mpReflectTypes;              ///< Helper for reflecting structured buffer types.
    ref<ComputePass>                mpSampleCameraPathsPass;     ///< Camera trace pass.
    ref<ComputePass>                mpSampleLightPathsPass;      ///< Light trace pass.
    ref<ComputePass>                mpCopyRadiancePass;          ///< Fullscreen compute pass writing camera-trace reservoir + light-trace atomic image to output.

    ref<Buffer>                     mpLightImage;                ///< Light trace image. Light subpath contributions are atomically added to this.
    ref<Buffer>                     mpLightVertices;             ///< Light sub-path vertices.
    ref<Buffer>                     mpLightVertexCount;          ///< Light vertex counter.
    ref<Buffer>                     mpPixelCounterData;          ///< Debug-heatmap counter.
};

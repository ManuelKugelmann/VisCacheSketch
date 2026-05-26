#include "BDPT.h"
#include "RenderGraph/RenderPassHelpers.h"
#include "RenderGraph/RenderPassStandardFlags.h"
#include "Rendering/Lights/EmissiveUniformSampler.h"

namespace
{
    const std::string kBDPTPassFilename           = "RenderPasses/BDPTPass/BDPT.cs.slang";
    const std::string kReflectTypesFile          = "RenderPasses/BDPTPass/ReflectTypes.cs.slang";

    // Render pass inputs and outputs.
    const std::string kInputVBuffer       = "vbuffer";
    const std::string kInputMotionVectors = "mvec";
    const std::string kInputViewDir       = "viewW";

    const Falcor::ChannelList kInputChannels =
    {
        { kInputVBuffer,       "gVBuffer",       "Visibility buffer in packed format" },
        { kInputMotionVectors, "gMotionVectors", "Motion vector buffer (float format)", true /* optional */ },
        { kInputViewDir,       "gViewW",         "World-space view direction (xyz float format)", true /* optional */ },
    };

    const std::string kOutputColor = "color";

    const Falcor::ChannelList kOutputChannels =
    {
        { kOutputColor, "", "Output color (linear)", true /* optional */, ResourceFormat::RGBA32Float },
    };

    // Scripting options.
    const std::string kMaxBounces            = "maxBounces";
    const std::string kSampleGenerator       = "sampleGenerator";
    const std::string kFixedSeed             = "fixedSeed";
    const std::string kUseNEE                = "useNEE";
    const std::string kUseBPT                = "useBPT";
    const std::string kNumLightSubpaths      = "numLightSubpaths";
    const std::string kMISPowerExponent      = "misPowerExponent";
    const std::string kEmissiveSampler       = "emissiveSampler";
    const std::string kLightBVHOptions       = "lightBVHOptions";

    const std::string kUseResampling         = "useResampling";
    const std::string kNumInitialCandidates  = "numInitialCandidates";
    const std::string kMCap                  = "Mcap";
    const std::string kUnbiasedTemporalReuse = "unbiasedTemporalReuse";
    const std::string kUseReconnectionMis    = "useReconnectionMis";
    const std::string kUseSuffixShift        = "useSuffixShift";
    const std::string kUseCausticShift       = "useCausticShift";
    const std::string kUseCausticReservoirs  = "useCausticReservoirs";
    const std::string kUseTemporalResampling = "useTemporalResampling";
    const std::string kSpatialPasses         = "spatialResamplingPasses";
    const std::string kSpatialCandidates     = "spatialResamplingCandidates";
    const std::string kSpatialRadius         = "spatialReuseRadius";
    const std::string kDisableVC             = "disableVC";
    const std::string kRoughnessThreshold    = "rcvRoughness";
}

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, BDPT>();
    ScriptBindings::registerBinding(BDPT::registerBindings);
}

void BDPT::registerBindings(pybind11::module& m)
{
    pybind11::class_<BDPT, RenderPass, ref<BDPT>> pass(m, "BDPT");
    pass.def("reset", &BDPT::reset);
}

BDPT::BDPT(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    if (!mpDevice->isShaderModelSupported(ShaderModel::SM6_5))
        FALCOR_THROW("BDPT requires Shader Model 6.5 support.");
    if (!mpDevice->isFeatureSupported(Device::SupportedFeatures::RaytracingTier1_1))
        FALCOR_THROW("BDPT requires Raytracing Tier 1.1 support.");

    parseProperties(props);
    // Vanilla BDPT: force all ReSTIR/temporal/caustic layers off so this
    // pass is a deterministic BDPT estimator (light subpaths + camera
    // subpaths + MIS-weighted connections). Properties on these knobs are
    // accepted but overridden. useBPT is intentionally NOT re-pinned so
    // callers can opt into PT-only mode (useBPT=False) for decomposition
    // tests / PT-comparison validation.
    // longer exist on StaticParams; nothing to re-pin.

    validateOptions();

    // Create sample generator.
    mpSampleGenerator = SampleGenerator::create(mpDevice, mStaticParams.sampleGenerator);

    // Note: The other programs are lazily created in updatePrograms() because a scene needs to be present when creating them.

    mpPixelDebug = std::make_unique<PixelDebug>(mpDevice, 1000);
}

void BDPT::setProperties(const Properties& props)
{
    parseProperties(props);
    validateOptions();
    if (auto lightBVHSampler = dynamic_cast<LightBVHSampler*>(mpEmissiveSampler.get()))
        lightBVHSampler->setOptions(mLightBVHOptions);
    mRecompile = true;
    mOptionsChanged = true;
}

void BDPT::parseProperties(const Properties& props)
{
    for (const auto& [key, value] : props)
    {
        // Rendering parameters
        if (key == kMaxBounces) mParams.mMaxBounces = value;

        // Sampling parameters
        else if (key == kSampleGenerator) mStaticParams.sampleGenerator = value;
        else if (key == kFixedSeed) { mFixedSeed = value; mUseFixedSeed = true; }
        else if (key == kUseNEE) mStaticParams.useNEE = value;
        else if (key == kUseBPT) mStaticParams.useBPT = value;
        else if (key == kNumLightSubpaths) mParams.mLightSubpathCount = value;
        else if (key == kMISPowerExponent) mStaticParams.misPowerExponent = value;
        else if (key == kEmissiveSampler) mStaticParams.emissiveSampler = value;
        else if (key == kNumInitialCandidates) mParams.mCanonicalSpp = value;
        else if (key == kMCap) mParams.mMCap = value;
        else if (key == kLightBVHOptions) mLightBVHOptions = value;
        else if (key == kDisableVC) mStaticParams.disableVC = value;
        else if (key == kRoughnessThreshold) mParams.mReconnectionRoughness = value;

        else logWarning("Unknown property '{}' in BDPT properties.", key);
    }
}

void BDPT::validateOptions()
{
    mParams.mMaxBounces = std::min(mParams.mMaxBounces, PathGeneratorParams::kMaxBounces);
    mParams.mMaxDiffuseBounces = std::min(mParams.mMaxDiffuseBounces, mParams.mMaxBounces);

    if (mParams.mReconnectionRoughness < 0.f || mParams.mReconnectionRoughness > 1.f)
    {
        logWarning("'mReconnectionRoughness' has invalid value. Clamping to range [0,1].");
        mParams.mReconnectionRoughness = std::clamp(mParams.mReconnectionRoughness, 0.f, 1.f);
    }

    if (mStaticParams.useBPT && mStaticParams.emissiveSampler == EmissiveLightSamplerType::LightBVH)
    {
        logWarning("LightBVH unsupported when using bidirectional path tracing.");
        mStaticParams.emissiveSampler = EmissiveLightSamplerType::Power;
    }

    // those fields no longer exist on StaticParams.
}

Properties BDPT::getProperties() const
{
    if (auto lightBVHSampler = dynamic_cast<LightBVHSampler*>(mpEmissiveSampler.get()))
    {
        mLightBVHOptions = lightBVHSampler->getOptions();
    }

    Properties props;

    // Rendering parameters
    props[kMaxBounces] = mParams.mMaxBounces;

    // Sampling parameters
    props[kSampleGenerator] = mStaticParams.sampleGenerator;
    if (mUseFixedSeed) props[kFixedSeed] = mFixedSeed;
    props[kUseNEE] = mStaticParams.useNEE;
    props[kUseBPT] = mStaticParams.useBPT;
    props[kNumLightSubpaths] = mParams.mLightSubpathCount;
    props[kMISPowerExponent] = mStaticParams.misPowerExponent;
    props[kEmissiveSampler] = mStaticParams.emissiveSampler;
    if (mStaticParams.emissiveSampler == EmissiveLightSamplerType::LightBVH) props[kLightBVHOptions] = mLightBVHOptions;
    props[kNumInitialCandidates] = mParams.mCanonicalSpp;
    props[kMCap] = mParams.mMCap;
    props[kDisableVC] = mStaticParams.disableVC;
    props[kRoughnessThreshold] = mParams.mReconnectionRoughness;

    return props;
}

RenderPassReflection BDPT::reflect(const CompileData& compileData)
{
    RenderPassReflection reflector;
    const uint2 sz = RenderPassHelpers::calculateIOSize(RenderPassHelpers::IOSize::Default, { 512, 512 }, compileData.defaultTexDims);

    addRenderPassInputs(reflector, kInputChannels);
    addRenderPassOutputs(reflector, kOutputChannels, ResourceBindFlags::UnorderedAccess, sz);
    return reflector;
}

void BDPT::setFrameDim(const uint2 mOutputDim)
{
    auto prevFrameDim = mParams.mOutputDim;

    mParams.mOutputDim = mOutputDim;

    if (any(mParams.mOutputDim != prevFrameDim))
    {
        mVarsChanged = true;
    }
}

void BDPT::setScene(RenderContext* pRenderContext, const ref<Scene>& pScene)
{
    mpScene = pScene;
    mFrameCount = 0;
    mParams.mOutputDim = {};

    resetPrograms();
    resetLighting();

    if (mpScene)
    {
        if (pScene->hasGeometryType(Scene::GeometryType::Custom))
        {
            logWarning("BDPT: This render pass does not support custom primitives.");
        }

        validateOptions();
    }
}

void BDPT::execute(RenderContext* pRenderContext, const RenderData& renderData)
{
    if (!beginFrame(pRenderContext, renderData)) return;

    // Update shader program specialization.
    updatePrograms();

    // Prepare resources.
    prepareResources(pRenderContext, renderData);

    // Clear resources
    {
        if (mStaticParams.useBPT)
        {
            pRenderContext->clearUAV(mpLightVertexCount->getUAV().get(), uint4(0));
            // Light-trace atomic-add output buffer.
            pRenderContext->clearUAV(mpLightImage->getUAV().get(), float4(0.f));
        }

        if (mStaticParams.debugHeatmap)
        {
            pRenderContext->clearUAV(mpPixelCounterData->getUAV().get(), uint4(0));
        }
    }

    // Canonical sampling
    {
        // Trace light sub-paths.
        if (mStaticParams.useBPT)
        {
            FALCOR_PROFILE(pRenderContext, "Initial light trace");
            // one thread per light subpath
            FALCOR_ASSERT(mpSampleLightPathsPass);
            preparePass(pRenderContext, renderData, *mpSampleLightPathsPass);
            mpSampleLightPathsPass->execute(pRenderContext, mParams.mOutputDim.x, (mParams.mLightSubpathCount + mParams.mOutputDim.x-1) / mParams.mOutputDim.x);
            mCurrentSeed++;
        }

        FALCOR_PROFILE(pRenderContext, "Initial camera trace");
        // Trace camera sub-paths.
        FALCOR_ASSERT(mpSampleCameraPathsPass);
        preparePass(pRenderContext, renderData, *mpSampleCameraPathsPass);
        mpSampleCameraPathsPass->execute(pRenderContext, mParams.mOutputDim.x, mParams.mOutputDim.y);
        mCurrentSeed += mParams.mCanonicalSpp;
    }


    // Copy light-trace contribution from atomic buffer into camera-trace
    // output. Only needed when BPT light subpaths were traced.
    if (mStaticParams.useBPT)
    {
        FALCOR_ASSERT(mpCopyRadiancePass);
        preparePass(pRenderContext, renderData, *mpCopyRadiancePass);
        mpCopyRadiancePass->addDefine("DEBUG_CAUSTIC_RESERVOIRS", "0");
        mpCopyRadiancePass->execute(pRenderContext, mParams.mOutputDim.x, mParams.mOutputDim.y);
    }

    endFrame(pRenderContext, renderData);
}

void BDPT::renderUI(Gui::Widgets& widget)
{
    bool dirty = false;

    // Rendering options.
    dirty |= renderRenderingUI(widget);

    // Stats and debug options.
    dirty |= renderDebugUI(widget);

    if (widget.group("Resource Usage (kb)")) {
        size_t totalSize = 0;
        if (mStaticParams.useBPT && mpLightVertices)
        {
            size_t lvcSize = 0;
            lvcSize += mpLightVertices->getSize();
            lvcSize += mpLightVertexCount->getSize();
            totalSize += lvcSize;
            widget.text("LVC: " + std::to_string(lvcSize/1024));
            widget.text("stride: " + std::to_string(mpLightVertices->getStructSize()));
            if (mpLightImage)
                totalSize += mpLightImage->getSize();
        }

        widget.separator();
        widget.text("Total: " + std::to_string(totalSize/1024));
    }

    if (widget.button("Output camera path")) {
        FileDialogFilterVec filters;
        filters.push_back({"csv", "CSV Files"});
        std::filesystem::path path;
        if (saveFileDialog(filters, path)) {
            mCameraPosOutputFile = path;
            mCameraPosOutputStream = std::ofstream(mCameraPosOutputFile, std::ios::trunc);
        }
    }
    if (!mCameraPosOutputFile.empty()) {
        widget.text(mCameraPosOutputFile.string(), true);
        if (widget.button("x")) {
            mCameraPosOutputFile.clear();
            mCameraPosOutputStream.close();
        }
    }

    if (dirty)
    {
        validateOptions();
        mOptionsChanged = true;
    }
}

bool BDPT::renderRenderingUI(Gui::Widgets& widget)
{
    bool dirty = false;
    bool runtimeDirty = false;

    dirty |= widget.checkbox("Enabled", mEnabled);
    widget.separator();

    if (auto group = widget.group("Path tracing options", true))
    {
        if (group.dropdown("Sample generator", SampleGenerator::getGuiDropdownList(), mStaticParams.sampleGenerator))
        {
            mpSampleGenerator = SampleGenerator::create(mpDevice, mStaticParams.sampleGenerator);
            dirty = true;
        }

        runtimeDirty |= group.var("Samples per pixel", mParams.mCanonicalSpp, 1u);
        group.tooltip("Maximum number of samples per pixel.");

        runtimeDirty |= group.var("Max bounces", mParams.mMaxBounces, 0u, PathGeneratorParams::kMaxBounces);
        group.tooltip("Maximum number of bounces.\n1 = direct only\n2 = one indirect bounce etc.");

        runtimeDirty |= group.var("Max diffuse bounces", mParams.mMaxDiffuseBounces, 0u, mParams.mMaxBounces);
        group.tooltip("Maximum number of diffuse bounces.");

        runtimeDirty |= group.var("Termination probability", mParams.mTerminationProbability, 0.f, 1.f);
        group.tooltip("Termination probability at each vertex.\nThis is multiplied by the roughness of the vertex.");

        dirty |= group.checkbox("BSDF importance sampling", mStaticParams.useBsdfImportanceSampling);
        group.tooltip("Use importance sampling for BSDFs.");

        dirty |= group.checkbox("Bidirectional path tracing (BPT)", mStaticParams.useBPT);
        group.tooltip("Use bidirectional path tracing.\nThis option automatically enables NEE.");

        if (mStaticParams.useBPT)
        {
            runtimeDirty |= group.var("Light sub-path count", mParams.mLightSubpathCount, 1u, 10000000u);
            group.tooltip("Number of light sub-paths to trace when BPT is enabled.");

            dirty |= group.checkbox("Light trace only", mStaticParams.lightTraceOnly);
            group.tooltip("Only use light tracing.\nThis option causes camera paths to be discarded.");

            if (!mStaticParams.lightTraceOnly)
            {
                dirty |= group.checkbox("Disable camera connection", mStaticParams.disableCameraConnection);
                group.tooltip("Don't connect light subpaths to the camera.");

                dirty |= group.checkbox("Disable vertex connection (VC)", mStaticParams.disableVC);
                group.tooltip("Only use PT, LT, and NEE");
            }
        }
        else
        {
            dirty |= group.checkbox("Next-event estimation (NEE)", mStaticParams.useNEE);
            group.tooltip("Use next-event estimation.\nThis option enables direct illumination sampling at each path vertex.");
        }

        if (mStaticParams.useNEE || mStaticParams.useBPT) {
            runtimeDirty |= group.var("Connection roughness threshold", mParams.mReconnectionRoughness, 0.f, 1.f);
            group.tooltip("Minimum roughness for considering connection techniques\nBPT/NEE/VM is only performed on vertices rougher than this.");
        }

        if (mStaticParams.useNEE || mStaticParams.useBPT)
        {
            dirty |= group.var("MIS power exponent", mStaticParams.misPowerExponent, 0.f, 10.f);

            if (mpScene && mpScene->useEmissiveLights())
            {
                if (group.dropdown("Emissive sampler", mStaticParams.emissiveSampler))
                {
                    resetLighting();
                    dirty = true;
                }
                group.tooltip("Selects which light sampler to use for importance sampling of emissive geometry.", true);

                if (mpEmissiveSampler)
                {
                    if (mpEmissiveSampler->renderUI(group)) mOptionsChanged = true;
                }
            }
        }

    }


    if (dirty) mRecompile = true;
    return dirty || runtimeDirty;
}

bool BDPT::renderDebugUI(Gui::Widgets& widget)
{
    bool dirty = false;

    if (auto group = widget.group("Debugging"))
    {
        bool recompile = false;

        group.checkbox("Pause rendering", mPauseRendering);
        if (mPauseRendering)
        {
            if (group.button("Render frame"))
            {
                mRenderOnce = true;
                mKeepFrameIndex = true;
            }
            if (group.button("Render frame & advance", true))
            {
                mRenderOnce = true;
            }
            group.var("Frame index", mFrameCount);
        }

        dirty |= group.checkbox("Use fixed seed", mUseFixedSeed);
        group.tooltip("Forces a fixed random seed for each frame.\n\n"
            "This should produce exactly the same image each frame, which can be useful for debugging.");
        if (mUseFixedSeed)
        {
            dirty |= group.var("Seed", mFixedSeed);
        }

        if (mStaticParams.useBPT) {
            recompile |= group.checkbox("Disable LVC", mStaticParams.disableLVC);
            group.tooltip("Trace 1 light subpath per pixel, connecting\ncamera subpath vertices to the whole light subpath.", true);
        }


        dirty |= group.checkbox("Fix seed per-frame", mUsePerFrameSeed);
        group.tooltip("Calculate the random seed from the frame index.");

        recompile |= group.checkbox("Debug BPT", mStaticParams.debugBPT);
        if (mStaticParams.debugBPT)
        {
            dirty |= group.var("Total vertex count", mParams.mDebugTotalVertices, -1);
            group.tooltip("Only render paths with this many segments.");
            dirty |= group.var("Light vertex count", mParams.mDebugLightVertices, -1);
            group.tooltip("Only render paths with this many light vertices.");

            dirty |= group.var("Prefix bounces", mParams.mDebugPrefixBounces, -1);
            group.tooltip("Only render paths with this many prefix bounces.");
        }

        recompile |= group.checkbox("Visualize counter data", mStaticParams.debugHeatmap);
        if (mStaticParams.debugHeatmap)
        {
            dirty |= group.dropdown("Counter type", mParams.mDebugCounter);
            group.tooltip("Debug counter to visualize.");
        }

        dirty      |= recompile;
        mRecompile |= recompile;
    }

    if (auto group = widget.group("Pixel debug"))
    {
        mpPixelDebug->renderUI(group);
    }

    return dirty;
}

bool BDPT::onMouseEvent(const MouseEvent& mouseEvent)
{
    return mpPixelDebug->onMouseEvent(mouseEvent);
}
bool BDPT::onKeyEvent(const KeyboardEvent& keyEvent)
{
    if (keyEvent.type == KeyboardEvent::Type::KeyPressed)
    {
        switch (keyEvent.key) {
        case Input::Key::H:
        case Input::Key::T:
            mResetTemporalHistory = true;
            return true;
        case Input::Key::K:
            mPauseRendering = !mPauseRendering;
            return true;
        case Input::Key::Left:
            if (mPauseRendering) {
                if (mFrameCount > 0)
                    mFrameCount--;
                else
                    mResetTemporalHistory = true;
                mRenderOnce = true;
                mKeepFrameIndex = true;
                return true;
            }
            break;
        case Input::Key::Right:
            if (mPauseRendering) {
                mFrameCount++;
                mRenderOnce = true;
                mKeepFrameIndex = true;
                return true;
            }
            break;
        case Input::Key::Down:
            if (mPauseRendering) {
                mRenderOnce = true;
                mKeepFrameIndex = true;
                return true;
            }
            break;
        }
    }
    return false;
}

void BDPT::reset()
{
    mFrameCount = 0;
    mResetTemporalHistory = true;
}

void BDPT::resetPrograms()
{
    mpReflectTypes = nullptr;
    mpSampleCameraPathsPass = nullptr;
    mpSampleLightPathsPass = nullptr;
    mpCopyRadiancePass = nullptr;

    mRecompile = true;
}

void BDPT::updatePrograms()
{
    FALCOR_ASSERT(mpScene);

    if (mRecompile == false) return;

    // If we get here, a change that require recompilation of shader programs has occurred.
    // This may be due to change of scene defines, type conformances, shader modules, or other changes that require recompilation.
    // When type conformances and/or shader modules change, the programs need to be recreated. We assume programs have been reset upon such changes.
    // When only defines have changed, it is sufficient to update the existing programs and recreate the program vars.

    auto defines = mStaticParams.getDefines(*this);
    auto globalTypeConformances = mpScene->getTypeConformances();

    auto preparePass = [&](ref<ComputePass> pass)
    {
        // Note that we must use set instead of add defines to replace any stale state.
        pass->getProgram()->setDefines(defines);

        // Recreate program vars. This may trigger recompilation if needed.
        // Note that program versions are cached, so switching to a previously used specialization is faster.
        pass->setVars(nullptr);
    };

    // Create compute passes.
    ProgramDesc baseDesc;
    baseDesc.addShaderModules(mpScene->getShaderModules());
    baseDesc.addTypeConformances(globalTypeConformances);

    if (!mpSampleCameraPathsPass)
    {
        ProgramDesc desc = baseDesc;
        desc.addShaderLibrary(kBDPTPassFilename).csEntry("SampleCameraPaths");
        mpSampleCameraPathsPass = ComputePass::create(mpDevice, desc, defines, false);
    }
    preparePass(mpSampleCameraPathsPass);

    if (mStaticParams.useBPT)
    {
        if (!mpSampleLightPathsPass)
        {
            ProgramDesc desc = baseDesc;
            desc.addShaderLibrary(kBDPTPassFilename).csEntry("SampleLightPaths");
            mpSampleLightPathsPass = ComputePass::create(mpDevice, desc, defines, false);
        }
        preparePass(mpSampleLightPathsPass);
    }


    if (!mpCopyRadiancePass)
    {
        ProgramDesc desc = baseDesc;
        desc.addShaderLibrary(kBDPTPassFilename).csEntry("OutputRadiance");
        mpCopyRadiancePass = ComputePass::create(mpDevice, desc, defines, false);
    }
    preparePass(mpCopyRadiancePass);

    if (!mpReflectTypes)
    {
        ProgramDesc desc = baseDesc;
        desc.addShaderLibrary(kReflectTypesFile).csEntry("main");
        mpReflectTypes = ComputePass::create(mpDevice, desc, defines, false);
    }
    preparePass(mpReflectTypes);

    mVarsChanged = true;
    mRecompile = false;
}

void BDPT::prepareResources(RenderContext* pRenderContext, const RenderData& renderData)
{
    const uint32_t screenPixelCount = mParams.mOutputDim.x * mParams.mOutputDim.y;
    if (mStaticParams.disableLVC) mParams.mLightSubpathCount = screenPixelCount;
    const size_t maxLightVertices = mParams.mLightSubpathCount * std::max(1u, mParams.mMaxDiffuseBounces);

    auto var = mpReflectTypes->getRootVar();

    if (mStaticParams.useBPT)
    {
        if (!mpLightVertices || mpLightVertices->getElementCount() != maxLightVertices || mVarsChanged)
        {
            mpLightVertices = mpDevice->createStructuredBuffer(var["gPathGenerator"]["mLightVertexCache"]["lightVertices"], maxLightVertices, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess, MemoryType::DeviceLocal, nullptr, false);
            mVarsChanged = true;
        }

        size_t vertexCountSize = sizeof(uint32_t) * (mStaticParams.disableLVC ? screenPixelCount : 2);
        if (!mpLightVertexCount || mpLightVertexCount->getSize() != vertexCountSize || mVarsChanged)
        {
            mpLightVertexCount = mpDevice->createBuffer(vertexCountSize, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
            mVarsChanged = true;
        }

        // buffer for BPT light-trace contribution).
        if (!mpLightImage || mpLightImage->getSize() != sizeof(float3) * screenPixelCount || mVarsChanged)
        {
            mpLightImage = mpDevice->createBuffer(sizeof(float3) * screenPixelCount, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
            mVarsChanged = true;
        }
    }

    if (mStaticParams.debugHeatmap)
    {
        if (!mpPixelCounterData || mpPixelCounterData->getSize() != sizeof(uint32_t)*(screenPixelCount+1) || mVarsChanged)
        {
            mpPixelCounterData = mpDevice->createBuffer(sizeof(uint32_t)*(screenPixelCount+1), ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
            mVarsChanged = true;
        }
    }
}

void BDPT::resetLighting()
{
    // Retain the options for the emissive sampler.
    if (auto lightBVHSampler = dynamic_cast<LightBVHSampler*>(mpEmissiveSampler.get()))
    {
        mLightBVHOptions = lightBVHSampler->getOptions();
    }

    mpEmissiveSampler = nullptr;
    mpEnvMapSampler = nullptr;
    mRecompile = true;
}

void BDPT::prepareMaterials(RenderContext* pRenderContext)
{
    // This functions checks for scene changes that require shader recompilation.
    // Whenever materials or geometry is added/removed to the scene, we reset the shader programs to trigger
    // recompilation with the correct defines, type conformances, shader modules, and binding table.

    if (is_set(mpScene->getUpdates(), Scene::UpdateFlags::RecompileNeeded) ||
        is_set(mpScene->getUpdates(), Scene::UpdateFlags::GeometryChanged))
    {
        resetPrograms();
    }
}

bool BDPT::prepareLighting(RenderContext* pRenderContext)
{
    bool lightingChanged = false;

    if (is_set(mpScene->getUpdates(), Scene::UpdateFlags::RenderSettingsChanged))
    {
        lightingChanged = true;
        mRecompile = true;
    }

    if (is_set(mpScene->getUpdates(), Scene::UpdateFlags::SDFGridConfigChanged))
    {
        mRecompile = true;
    }

    if (is_set(mpScene->getUpdates(), Scene::UpdateFlags::EnvMapChanged))
    {
        mpEnvMapSampler = nullptr;
        lightingChanged = true;
        mRecompile = true;
    }

    if (mpScene->useEnvLight())
    {
        if (!mpEnvMapSampler)
        {
            mpEnvMapSampler = std::make_unique<EnvMapSampler>(mpDevice, mpScene->getEnvMap());
            lightingChanged = true;
            mRecompile = true;
        }
    }
    else
    {
        if (mpEnvMapSampler)
        {
            mpEnvMapSampler = nullptr;
            lightingChanged = true;
            mRecompile = true;
        }
    }

    // Request the light collection if emissive lights are enabled.
    if (mpScene->getRenderSettings().useEmissiveLights)
    {
        mpScene->getLightCollection(pRenderContext);
    }

    if (mpScene->useEmissiveLights())
    {
        if (!mpEmissiveSampler)
        {
            const auto& pLights = mpScene->getLightCollection(pRenderContext);
            FALCOR_ASSERT(pLights && pLights->getActiveLightCount(pRenderContext) > 0);
            FALCOR_ASSERT(!mpEmissiveSampler);

            switch (mStaticParams.emissiveSampler)
            {
            case EmissiveLightSamplerType::Uniform:
                mpEmissiveSampler = std::make_unique<EmissiveUniformSampler>(pRenderContext, mpScene->getILightCollection(pRenderContext));
                break;
            case EmissiveLightSamplerType::LightBVH:
                mpEmissiveSampler = std::make_unique<LightBVHSampler>(pRenderContext, mpScene->getILightCollection(pRenderContext), mLightBVHOptions);
                break;
            case EmissiveLightSamplerType::Power:
                mpEmissiveSampler = std::make_unique<EmissivePowerSampler>(pRenderContext, mpScene->getILightCollection(pRenderContext));
                break;
            default:
                FALCOR_THROW("Unknown emissive light sampler type");
            }
            lightingChanged = true;
            mRecompile = true;
        }
    }
    else
    {
        if (mpEmissiveSampler)
        {
            // Retain the options for the emissive sampler.
            if (auto lightBVHSampler = dynamic_cast<LightBVHSampler*>(mpEmissiveSampler.get()))
            {
                mLightBVHOptions = lightBVHSampler->getOptions();
            }

            mpEmissiveSampler = nullptr;
            lightingChanged = true;
            mRecompile = true;
        }
    }

    if (mpEmissiveSampler)
    {
        lightingChanged |= mpEmissiveSampler->update(pRenderContext, mpScene->getILightCollection(pRenderContext));
        auto defines = mpEmissiveSampler->getDefines();
        if (mpSampleCameraPathsPass && mpSampleCameraPathsPass->getProgram()->addDefines(defines)) mRecompile = true;
    }

    return lightingChanged;
}

void BDPT::bindShaderData(const ShaderVar& var, const RenderData& renderData) const
{
    // Bind static resources that don't change per frame.
    if (mVarsChanged)
    {
        var["mAtomicRadiance"] = mpLightImage;

        var["mLightVertexCache"]["lightVertices"] = mpLightVertices;
        var["mLightVertexCache"]["lightVertexCount"] = mpLightVertexCount;

        var["mOutputCounterData"] = mpPixelCounterData;


        mpSampleGenerator->bindShaderData(var);
    }

    if (mpEnvMapSampler) mpEnvMapSampler->bindShaderData(var["mEnvMapSampler"]);
    if (mpEmissiveSampler) mpEmissiveSampler->bindShaderData(var["mEmissiveSampler"]);

    ref<Texture> pViewDir;
    if (mpScene->getCamera()->getApertureRadius() > 0.f)
    {
        pViewDir = renderData.getTexture(kInputViewDir);
        if (!pViewDir) logWarning("Depth-of-field requires the '{}' input. Expect incorrect rendering.", kInputViewDir);
    }


    var["mParams"].setBlob(mParams);
    var["mVbuffer"] = renderData.getTexture(kInputVBuffer);
    var["mViewDir"] = pViewDir; // Can be nullptr
    var["mOutputRadiance"] = renderData.getTexture(kOutputColor);
}

bool BDPT::beginFrame(RenderContext* pRenderContext, const RenderData& renderData)
{
    if (mPauseRendering)
    {
        if (!mRenderOnce) return false;

        if (!mRenderOnceSceneUpdated)
        {
            if (mpScene) mpScene->update(pRenderContext, mFrameCount / 24.0);
            mRenderOnceSceneUpdated = true;
            // skip a frame to let the other passes process the scene update
            return false;
        }

        mRenderOnce = false;
        mRenderOnceSceneUpdated = false;
    }

    const auto& pOutputColor = renderData.getTexture(kOutputColor);
    FALCOR_ASSERT(pOutputColor);

    // Set output frame dimension.
    setFrameDim(uint2(pOutputColor->getWidth(), pOutputColor->getHeight()));

    // Validate all I/O sizes match the expected size.
    // If not, we'll disable the path tracer to give the user a chance to fix the configuration before re-enabling it.
    bool resolutionMismatch = false;
    auto validateChannels = [&](const auto& channels) {
        for (const auto& channel : channels)
        {
            auto pTexture = renderData.getTexture(channel.name);
            if (pTexture && (pTexture->getWidth() != mParams.mOutputDim.x || pTexture->getHeight() != mParams.mOutputDim.y)) resolutionMismatch = true;
        }
    };
    validateChannels(kInputChannels);
    validateChannels(kOutputChannels);

    if (mEnabled && resolutionMismatch)
    {
        logError("BDPT I/O sizes don't match. The pass will be disabled.");
        mEnabled = false;
    }

    if (mpScene == nullptr || !mEnabled)
    {
        pRenderContext->clearUAV(pOutputColor->getUAV().get(), float4(0.f));

        // Set refresh flag if changes that affect the output have occured.
        // This is needed to ensure other passes get notified when the path tracer is enabled/disabled.
        if (mOptionsChanged)
        {
            auto& dict = renderData.getDictionary();
            auto flags = dict.getValue(kRenderPassRefreshFlags, Falcor::RenderPassRefreshFlags::None);
            if (mOptionsChanged) flags |= Falcor::RenderPassRefreshFlags::RenderOptionsChanged;
            dict[Falcor::kRenderPassRefreshFlags] = flags;
        }

        return false;
    }

    // Update materials.
    prepareMaterials(pRenderContext);

    // Update the env map and emissive sampler to the current frame.
    bool lightingChanged = prepareLighting(pRenderContext);

    // Update refresh flag if changes that affect the output have occured.
    auto& dict = renderData.getDictionary();
    if (mOptionsChanged || lightingChanged)
    {
        auto flags = dict.getValue(kRenderPassRefreshFlags, Falcor::RenderPassRefreshFlags::None);
        if (mOptionsChanged) flags |= Falcor::RenderPassRefreshFlags::RenderOptionsChanged;
        if (lightingChanged) flags |= Falcor::RenderPassRefreshFlags::LightingChanged;
        dict[Falcor::kRenderPassRefreshFlags] = flags;
        mOptionsChanged = false;
    }

    mpPixelDebug->beginFrame(pRenderContext, mParams.mOutputDim);

    // Update the random seed.
    if (mUseFixedSeed) {
        mCurrentSeed = mFixedSeed;
    } else if (mUsePerFrameSeed) {
        uint seedsPerFrame = mParams.mCanonicalSpp;
        if (mStaticParams.useBPT) seedsPerFrame++; // light subpaths
        mCurrentSeed = mFrameCount * seedsPerFrame;
    } else {
        mCurrentSeed = (uint)std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }

    const auto& aabb = mpScene->getSceneBounds();
    mParams.mSceneSphere = float4(aabb.maxPoint + aabb.minPoint, length(aabb.maxPoint - aabb.minPoint))*.5f;

    return true;
}

void BDPT::endFrame(RenderContext* pRenderContext, const RenderData& renderData)
{

    mpPixelDebug->endFrame(pRenderContext);

    if (!mKeepFrameIndex)
        mFrameCount++;
    mKeepFrameIndex = false;

    mVarsChanged = false;

    if (mCameraPosOutputStream) {
        const Camera& cam = *mpScene->getCamera();
        mCameraPosOutputStream << cam.getPosition().x << "," << cam.getPosition().y << "," << cam.getPosition().z << ",";
        mCameraPosOutputStream << cam.getData().target.x << "," << cam.getData().target.y << "," << cam.getData().target.z << ",";
        mCameraPosOutputStream << cam.getData().up.x << "," << cam.getData().up.y << "," << cam.getData().up.z;
        mCameraPosOutputStream << std::endl;
    }
}

void BDPT::preparePass(RenderContext* pRenderContext, const RenderData& renderData, ComputePass& pass) const
{
    ref<Program> program = pass.getProgram();

    FALCOR_ASSERT(program);

    auto var = pass.getRootVar();
    mpPixelDebug->prepareProgram(program, var);

    // [Falcor 8] bindShaderDataForRaytracing expects the gScene ShaderVar, not root.
    mpScene->bindShaderDataForRaytracing(pRenderContext, var["gScene"]);

    bindShaderData(var["gPathGenerator"], renderData);

    var["CB"]["gRandomSeed"] = mCurrentSeed;
    var["CB"]["gSwapReservoirs"] = uint(mSwapReservoirs ? 1u : 0u);

    pass.addDefine("USE_VIEW_DIR", (mpScene->getCamera()->getApertureRadius() > 0 && renderData[kInputViewDir] != nullptr) ? "1" : "0");
}

DefineList BDPT::StaticParams::getDefines(const BDPT& owner) const
{
    DefineList defines;

    defines.add("USE_BSDF_IMPORTANCE_SAMPLING", useBsdfImportanceSampling ? "1" : "0");
    defines.add("MIS_POWER_EXPONENT", std::to_string(misPowerExponent));
    defines.add("USE_NEE", (useNEE || useBPT) ? "1" : "0");
    defines.add("USE_BIDIRECTIONAL", useBPT ? "1" : "0");
    defines.add("LIGHT_TRACE_ONLY", (useBPT && lightTraceOnly) ? "1" : "0");
    defines.add("DISABLE_CAMERA_CONNECTION", (useBPT && disableCameraConnection) ? "1" : "0");
    defines.add("DISABLE_VC", useBPT && disableVC ? "1" : "0");
    defines.add("DISABLE_LVC", useBPT && disableLVC ? "1" : "0");
    defines.add("DEBUG_BPT", debugBPT ? "1" : "0");
    defines.add("DEBUG_HEATMAP", debugHeatmap ? "1" : "0");
    // #if USE_RECONNECTION_MIS blocks that previously needed pinning
    // are also gone now.
    defines.add("USE_VIEW_DIR", "0"); // placeholder, set by prepareVars

    // Sampling utilities configuration.
    FALCOR_ASSERT(owner.mpSampleGenerator);
    defines.add(owner.mpSampleGenerator->getDefines());

    if (owner.mpEmissiveSampler) defines.add(owner.mpEmissiveSampler->getDefines());

    // Scene-specific configuration.
    const auto& scene = owner.mpScene;
    if (scene) defines.add(scene->getSceneDefines());
    defines.add("USE_ENV_LIGHT"      , scene && scene->useEnvLight()       ? "1" : "0");
    defines.add("USE_EMISSIVE_LIGHTS", scene && scene->useEmissiveLights() ? "1" : "0");
    defines.add("USE_ANALYTIC_LIGHTS", scene && scene->useAnalyticLights() ? "1" : "0");

    return defines;
}

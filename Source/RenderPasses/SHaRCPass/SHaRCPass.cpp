/***************************************************************************
 * SHaRCPass.cpp
 *
 * Falcor 8.0 RenderPass — SHaRC (Spatial Hash Radiance Cache)
 * Host-side buffer management and resolve dispatch.
 ***************************************************************************/

#include "SHaRCPass.h"
#include <algorithm>
#include <cstring>

// Buffer element sizes matching Slang structs
static constexpr size_t kHashEntrySize       = 8u;   // uint64_t
static constexpr size_t kAccumulationSize    = 16u;  // SharcAccumulationData { uint4 data }
static constexpr size_t kResolvedSize        = 16u;  // SharcPackedData { float16_t4 + uint + uint }

extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<RenderPass, SHaRCPass>();
}

// ---------------------------------------------------------------------------
SHaRCPass::SHaRCPass(ref<Device> pDevice, const Properties& props)
    : RenderPass(pDevice)
{
    if (props.has("capacity"))              mParams.capacity              = props["capacity"];
    if (props.has("sceneScale"))            mParams.sceneScale            = props["sceneScale"];
    if (props.has("radianceScale"))         mParams.radianceScale         = props["radianceScale"];
    if (props.has("accumulationFrameNum"))  mParams.accumulationFrameNum  = props["accumulationFrameNum"];
    if (props.has("staleFrameNumMax"))      mParams.staleFrameNumMax      = props["staleFrameNumMax"];
    if (props.has("levelBias"))             mParams.levelBias             = props["levelBias"];
    if (props.has("enableAntiFirefly"))     mParams.enableAntiFirefly     = props["enableAntiFirefly"];
}

ref<SHaRCPass> SHaRCPass::create(ref<Device> pDevice, const Properties& props)
{
    return make_ref<SHaRCPass>(pDevice, props);
}

// ---------------------------------------------------------------------------
void SHaRCPass::setProperties(const Properties& props)
{
    if (props.has("capacity"))              mParams.capacity              = props["capacity"];
    if (props.has("sceneScale"))            mParams.sceneScale            = props["sceneScale"];
    if (props.has("radianceScale"))         mParams.radianceScale         = props["radianceScale"];
    if (props.has("accumulationFrameNum"))  mParams.accumulationFrameNum  = props["accumulationFrameNum"];
    if (props.has("staleFrameNumMax"))      mParams.staleFrameNumMax      = props["staleFrameNumMax"];
    if (props.has("levelBias"))             mParams.levelBias             = props["levelBias"];
    if (props.has("enableAntiFirefly"))     mParams.enableAntiFirefly     = props["enableAntiFirefly"];
}

// ---------------------------------------------------------------------------
Properties SHaRCPass::getProperties() const
{
    Properties p;
    p["capacity"]              = mParams.capacity;
    p["sceneScale"]            = mParams.sceneScale;
    p["radianceScale"]         = mParams.radianceScale;
    p["accumulationFrameNum"]  = mParams.accumulationFrameNum;
    p["staleFrameNumMax"]      = mParams.staleFrameNumMax;
    p["levelBias"]             = mParams.levelBias;
    p["enableAntiFirefly"]     = mParams.enableAntiFirefly;
    return p;
}

// Input/output channel names
static const std::string kInputWorldPos  = "worldPos";
static const std::string kInputWorldNorm = "worldNorm";
static const std::string kOutputColor    = "color";

// ---------------------------------------------------------------------------
RenderPassReflection SHaRCPass::reflect(const CompileData&)
{
    RenderPassReflection r;
    r.addInput(kInputWorldPos, "World position (xyz) + hit flag (w)").format(ResourceFormat::RGBA32Float).flags(RenderPassReflection::Field::Flags::Optional);
    r.addInput(kInputWorldNorm, "World normal").format(ResourceFormat::RGBA32Float).flags(RenderPassReflection::Field::Flags::Optional);
    r.addOutput(kOutputColor, "Debug visualization output").format(ResourceFormat::RGBA32Float);
    return r;
}

// ---------------------------------------------------------------------------
void SHaRCPass::compile(RenderContext*, const CompileData& compileData)
{
    mFrameDims = compileData.defaultTexDims;
    allocateBuffers();

    // Resolve compute pass
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/SHaRCPass/SharcResolve.cs.slang")
            .csEntry("csResolve");
        DefineList defines;
        defines.add("SHARC_ENABLE_64_BIT_ATOMICS", "1");
        mpResolvePass = ComputePass::create(mpDevice, desc, defines);
    }

    // Debug visualization compute pass
    {
        ProgramDesc desc;
        desc.addShaderLibrary("RenderPasses/SHaRCPass/SharcDebugVis.cs.slang")
            .csEntry("csSharcDebugVis");
        DefineList defines;
        defines.add("SHARC_ENABLE_64_BIT_ATOMICS", "1");
        mpDebugVisPass = ComputePass::create(mpDevice, desc, defines);
    }
}

// ---------------------------------------------------------------------------
void SHaRCPass::allocateBuffers()
{
    // Ensure power-of-two capacity
    uint32_t cap = 1u;
    while (cap < mParams.capacity) cap <<= 1;
    mParams.capacity = cap;

    auto flags = ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess;

    mpHashEntries = mpDevice->createStructuredBuffer(
        kHashEntrySize, mParams.capacity, flags, MemoryType::DeviceLocal, nullptr, true);
    mpHashEntries->setName("SHaRC_HashEntries");

    mpAccumulation = mpDevice->createStructuredBuffer(
        kAccumulationSize, mParams.capacity, flags, MemoryType::DeviceLocal, nullptr, true);
    mpAccumulation->setName("SHaRC_Accumulation");

    mpResolved = mpDevice->createStructuredBuffer(
        kResolvedSize, mParams.capacity, flags, MemoryType::DeviceLocal, nullptr, true);
    mpResolved->setName("SHaRC_Resolved");

    mpLockBuffer = mpDevice->createStructuredBuffer(
        sizeof(uint32_t), mParams.capacity, flags, MemoryType::DeviceLocal, nullptr, true);
    mpLockBuffer->setName("SHaRC_Lock");
}

// ---------------------------------------------------------------------------
void SHaRCPass::autoTuneSceneScale()
{
    if (!mpScene) return;

    const auto& bounds = mpScene->getSceneBounds();
    float3 extent = bounds.extent();
    float sceneDiameter = std::max({extent.x, extent.y, extent.z});
    if (sceneDiameter <= 0.f) return;

    mParams.sceneScale = 1.0f / sceneDiameter * 100.0f;
}

// ---------------------------------------------------------------------------
void SHaRCPass::setScene(RenderContext* pCtx, const ref<Scene>& pScene)
{
    mpScene = pScene;
    if (mpScene)
    {
        autoTuneSceneScale();
        mFrameCount = 0u;
        logInfo("[SHaRC] Scene loaded: sceneScale={:.2f}", mParams.sceneScale);
    }
    allocateBuffers();
}

// ---------------------------------------------------------------------------
void SHaRCPass::execute(RenderContext* pCtx, const RenderData& renderData)
{
    // Get camera position
    float3 cameraPosition = float3(0.f);
    if (mpScene)
    {
        cameraPosition = mpScene->getCamera()->getPosition();
    }

    // ----------------------------------------------------------------
    // Export buffers + parameters to downstream passes via dictionary.
    // Downstream path tracer binds these for SHARC_UPDATE and SHARC_QUERY.
    // ----------------------------------------------------------------
    auto& dict = renderData.getDictionary();
    dict["sharcHashEntries"]    = mpHashEntries;
    dict["sharcAccumulation"]   = mpAccumulation;
    dict["sharcResolved"]       = mpResolved;
    dict["sharcLock"]           = mpLockBuffer;
    dict["sharcCapacity"]       = mParams.capacity;
    dict["sharcSceneScale"]     = mParams.sceneScale;
    dict["sharcRadianceScale"]  = mParams.radianceScale;
    dict["sharcLevelBias"]      = mParams.levelBias;
    dict["sharcAntiFirefly"]    = mParams.enableAntiFirefly;
    dict["sharcCameraPosition"] = cameraPosition;

    // ----------------------------------------------------------------
    // Run resolve pass: blend new accumulation into resolved buffer.
    // ----------------------------------------------------------------
    if (mpResolvePass)
    {
        auto vars = mpResolvePass->getRootVar();

        // SharcParameters members
        vars["gHashEntries"]        = mpHashEntries;
        vars["gAccumulation"]       = mpAccumulation;
        vars["gResolved"]           = mpResolved;
        vars["gLock"]               = mpLockBuffer;

        // GridParameters
        vars["SharcCB"]["cameraPosition"]   = cameraPosition;
        vars["SharcCB"]["logarithmBase"]    = 2.0f;  // SHARC_GRID_LOGARITHM_BASE
        vars["SharcCB"]["sceneScale"]       = mParams.sceneScale;
        vars["SharcCB"]["levelBias"]        = mParams.levelBias;

        // ResolveParameters
        vars["SharcCB"]["radianceScale"]         = mParams.radianceScale;
        vars["SharcCB"]["enableAntiFireflyFilter"] = mParams.enableAntiFirefly ? 1u : 0u;
        vars["SharcCB"]["cameraPositionPrev"]    = mCameraPositionPrev;
        vars["SharcCB"]["accumulationFrameNum"]  = mParams.accumulationFrameNum;
        vars["SharcCB"]["staleFrameNumMax"]      = mParams.staleFrameNumMax;
        vars["SharcCB"]["frameIndex"]            = mFrameCount;
        vars["SharcCB"]["capacity"]              = mParams.capacity;

        uint32_t numGroups = (mParams.capacity + 63u) / 64u;
        mpResolvePass->execute(pCtx, numGroups, 1u, 1u);
    }

    // ----------------------------------------------------------------
    // Debug visualization: query cache at primary hit positions.
    // Requires worldPos + worldNorm inputs (from GBufferRT).
    // ----------------------------------------------------------------
    auto pWorldPos  = renderData[kInputWorldPos];
    auto pWorldNorm = renderData[kInputWorldNorm];
    auto pOutput    = renderData[kOutputColor];

    if (mpDebugVisPass && pWorldPos && pWorldNorm && pOutput)
    {
        auto vars = mpDebugVisPass->getRootVar();
        vars["gWorldPos"]   = pWorldPos->asTexture();
        vars["gWorldNorm"]  = pWorldNorm->asTexture();
        vars["gOutput"]     = pOutput->asTexture();
        vars["gHashEntries"] = mpHashEntries;
        vars["gResolved"]   = mpResolved;

        vars["SharcVisCB"]["cameraPosition"] = cameraPosition;
        vars["SharcVisCB"]["logarithmBase"]  = 2.0f;
        vars["SharcVisCB"]["sceneScale"]     = mParams.sceneScale;
        vars["SharcVisCB"]["levelBias"]      = mParams.levelBias;
        vars["SharcVisCB"]["frameDim"]       = mFrameDims;
        vars["SharcVisCB"]["debugMode"]      = uint32_t(mDebugMode);
        vars["SharcVisCB"]["exposureScale"]  = mExposureScale;
        vars["SharcVisCB"]["capacity"]       = mParams.capacity;

        uint32_t gx = (mFrameDims.x + 15u) / 16u;
        uint32_t gy = (mFrameDims.y + 15u) / 16u;
        mpDebugVisPass->execute(pCtx, gx, gy, 1u);
    }

    mCameraPositionPrev = cameraPosition;
    mFrameCount++;
}

// ---------------------------------------------------------------------------
void SHaRCPass::renderUI(Gui::Widgets& widget)
{
    widget.text(fmt::format("Capacity: {} ({:.1f} MB)",
        mParams.capacity,
        float(mParams.capacity) * (kHashEntrySize + kAccumulationSize + kResolvedSize) / (1024.f * 1024.f)));
    widget.text(fmt::format("Frame: {}", mFrameCount));
    widget.separator();

    widget.var("Scene scale",       mParams.sceneScale,           0.1f, 10000.0f, 1.0f);
    widget.var("Radiance scale",    mParams.radianceScale,        1.0f, 100000.0f, 100.0f);
    widget.var("Accumulation frames", mParams.accumulationFrameNum, 1u, 1024u);
    widget.var("Stale frame max",   mParams.staleFrameNumMax,     1u, 1024u);
    widget.var("Level bias",        mParams.levelBias,            -5.0f, 5.0f, 0.5f);
    widget.checkbox("Anti-firefly filter", mParams.enableAntiFirefly);
    widget.separator();

    static const Gui::DropdownList kDebugModes = {
        {uint32_t(DebugMode::CachedRadiance), "Cached Radiance"},
        {uint32_t(DebugMode::HashGridColor),  "Hash Grid Coloring"},
        {uint32_t(DebugMode::Occupancy),      "Occupancy"},
    };
    widget.dropdown("Debug vis", kDebugModes, reinterpret_cast<uint32_t&>(mDebugMode));
    widget.var("Exposure scale", mExposureScale, 0.01f, 100.0f, 0.1f);
}

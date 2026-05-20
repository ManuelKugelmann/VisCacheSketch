#include "HashMap.h"
#include "Core/API/RenderContext.h"

namespace
{
    const char kShaderFile[] = "RenderPasses/ReSTIRBDPT/HashMap.cs.slang";
}

namespace Falcor
{

GPUHashMap::GPUHashMap(ref<Device> pDevice)
    : mpDevice(pDevice)
{
    DefineList defines = {};
    defines.add("DATA_SIZE", "1");
    mpComputeOffsetsPass = ComputePass::create(mpDevice, kShaderFile, "ComputeHashMapOffsets", defines);
    mpSortPass           = ComputePass::create(mpDevice, kShaderFile, "SortHashMapData", defines);
}

bool GPUHashMap::prepareResources(const ShaderVar& var, const uint cellCount, const uint maxSize)
{
    bool changed = false;

    if (!mpCounters)
    {
        mpCounters = mpDevice->createBuffer(sizeof(uint32_t)*2, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
        changed = true;
    }

    if (!mpCellKeys || mpCellDataOffsets->getElementCount() != cellCount)
    {
        mpCellKeys        = mpDevice->createBuffer(sizeof(uint32_t)*cellCount, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
        mpCellCounters    = mpDevice->createBuffer(sizeof(uint32_t)*cellCount, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
        mpCellDataOffsets = mpDevice->createStructuredBuffer(var["mCellDataOffsets"], cellCount, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess, MemoryType::DeviceLocal, nullptr, false);
        changed = true;
    }

    uint elementSize = var["mData"].getType()->unwrapArray()->asResourceType()->getSize();

    if (!mpData || mpData->getElementCount() != maxSize || mpData->getElementSize() != elementSize)
    {
        mpData            = mpDevice->createStructuredBuffer(elementSize,         maxSize, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess, MemoryType::DeviceLocal, nullptr, false);
        mpSortedData      = mpDevice->createStructuredBuffer(elementSize,         maxSize, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess, MemoryType::DeviceLocal, nullptr, false);
        mpDataIndices     = mpDevice->createStructuredBuffer(var["mDataIndices"], maxSize, ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess, MemoryType::DeviceLocal, nullptr, false);
        changed = true;
    }

    return changed;
}

void GPUHashMap::bindShaderData(const ShaderVar& var) const
{
    FALCOR_ASSERT(var.isValid());

    var["mCellKeys"]        = mpCellKeys;
    var["mCellCounters"]    = mpCellCounters;
    var["mCellDataOffsets"] = mpCellDataOffsets;
    var["mData"]            = mpData;
    var["mSortedData"]      = mpSortedData;
    var["mDataIndices"]     = mpDataIndices;
    var["mCounters"]        = mpCounters;

    var["mCellCount"]       = mpCellDataOffsets ? mpCellDataOffsets->getElementCount() : 0;
    var["mMaxSize"]         = mpData ? mpData->getElementCount() : 0;
}

size_t GPUHashMap::getTotalSize() const {
    size_t s = 0;
    if (mpData) {
        s += mpCellKeys->getSize();
        s += mpCellCounters->getSize();
        s += mpCellDataOffsets->getSize();
        s += mpData->getSize();
        s += mpSortedData->getSize();
        s += mpDataIndices->getSize();
        s += mpCounters->getSize();
    }
    return s;
}

void GPUHashMap::clear(RenderContext* pRenderContext) const
{
    pRenderContext->clearUAV(mpCellKeys->getUAV().get(), uint4(0));
    pRenderContext->clearUAV(mpCellCounters->getUAV().get(), uint4(0));
    pRenderContext->clearUAV(mpCounters->getUAV().get(), uint4(0));
}
void GPUHashMap::barrier(RenderContext* pRenderContext) const
{
    pRenderContext->uavBarrier(mpCellKeys.get());
    pRenderContext->uavBarrier(mpCellCounters.get());
    pRenderContext->uavBarrier(mpCounters.get());
}

void GPUHashMap::sort(RenderContext* pRenderContext) const
{
    {
        auto var = mpComputeOffsetsPass->getRootVar()["CB"];
        bindShaderData(var["gHashMap"]);
        mpComputeOffsetsPass->addDefine("DATA_SIZE", std::to_string(mpData->getElementSize()/sizeof(uint32_t)));
        mpComputeOffsetsPass->execute(pRenderContext, mpCellDataOffsets->getElementCount(), 1, 1);
    }

    {
        auto var = mpSortPass->getRootVar()["CB"];
        bindShaderData(var["gHashMap"]);
        mpSortPass->addDefine("DATA_SIZE", std::to_string(mpData->getElementSize()/sizeof(uint32_t)));
        mpSortPass->execute(pRenderContext, mpData->getElementCount(), 1, 1);
    }
}

}

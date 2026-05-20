#pragma once

#include "Core/API/Device.h"
#include "Core/Pass/ComputePass.h"
#include "Utils/UI/Gui.h"

namespace Falcor
{
class RenderContext;

/**
 * Utility class for hash maps on the GPU.
 *
 * This class has functions for configuring the shader program and
 * uploading the necessary data.
 * On the GPU, import GPUHashMap.slang in your shader program.
 */
class GPUHashMap
{
public:
    GPUHashMap(ref<Device> pDevice);
    ~GPUHashMap() = default;

    /**
     * Prepares the shader de
     * @param[in] pVars ProgramVars of the program to get data size from.
     * @param[in] cellCount Number of cells/buckets in the hash map.
     * @param[in] maxSize Max number of elements that can be added to the hash map.
     * @return true when the data is updated
    */
    bool prepareResources(const ShaderVar& var, const uint cellCount, const uint maxSize);

    /**
     * Binds the data to a program vars object.
     * @param[in] pVars ProgramVars of the program to set data into.
     */
    void bindShaderData(const ShaderVar& var) const;

    void clear(RenderContext* pRenderContext) const;
    void sort(RenderContext* pRenderContext) const;
    void barrier(RenderContext* pRenderContext) const;

    size_t getTotalSize() const;

private:
    ref<Device> mpDevice;

    ref<ComputePass> mpComputeOffsetsPass;
    ref<ComputePass> mpSortPass;

    ref<Buffer> mpCellKeys;
    ref<Buffer> mpCellCounters;
    ref<Buffer> mpCellDataOffsets;
    ref<Buffer> mpData;
    ref<Buffer> mpSortedData;
    ref<Buffer> mpDataIndices;
    ref<Buffer> mpCounters;
};
} // namespace Falcor

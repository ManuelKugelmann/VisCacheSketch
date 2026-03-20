/***************************************************************************
 * SharcResolve.cs.slang
 *
 * Compute shader that dispatches SharcResolveEntry() from SharcCommon.slang.
 * One thread per hash table entry.
 ***************************************************************************/

// Feature defines — must be set before importing SharcCommon
#ifndef SHARC_UPDATE
#define SHARC_UPDATE 0
#endif

#ifndef SHARC_QUERY
#define SHARC_QUERY 0
#endif

import SharcCommon;

// Buffers matching SharcParameters layout
RWStructuredBuffer<uint64_t>            gHashEntries;
RWStructuredBuffer<SharcAccumulationData> gAccumulation;
RWStructuredBuffer<SharcPackedData>     gResolved;
RWStructuredBuffer<uint>                gLock;

cbuffer SharcCB
{
    // HashGridParameters
    float3  cameraPosition;
    float   logarithmBase;
    float   sceneScale;
    float   levelBias;

    // SharcParameters scalars
    float   radianceScale;
    uint    enableAntiFireflyFilter;

    // SharcResolveParameters
    float3  cameraPositionPrev;
    uint    accumulationFrameNum;
    uint    staleFrameNumMax;
    uint    frameIndex;
    uint    capacity;
};

[numthreads(64, 1, 1)]
void csResolve(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint entryIndex = dispatchThreadId.x;
    if (entryIndex >= capacity)
        return;

    // Assemble SharcParameters from bound resources
    SharcParameters sharcParams;
    sharcParams.gridParameters.cameraPosition = cameraPosition;
    sharcParams.gridParameters.logarithmBase  = logarithmBase;
    sharcParams.gridParameters.sceneScale     = sceneScale;
    sharcParams.gridParameters.levelBias      = levelBias;
    sharcParams.hashMapData.capacity          = capacity;
    sharcParams.hashMapData.hashEntriesBuffer = gHashEntries;
#if !HASH_GRID_ENABLE_64_BIT_ATOMICS
    sharcParams.hashMapData.lockBuffer        = gLock;
#endif
    sharcParams.radianceScale                 = radianceScale;
    sharcParams.enableAntiFireflyFilter       = enableAntiFireflyFilter != 0;
    sharcParams.accumulationBuffer            = gAccumulation;
    sharcParams.resolvedBuffer                = gResolved;

    // Assemble SharcResolveParameters
    SharcResolveParameters resolveParams;
    resolveParams.cameraPositionPrev    = cameraPositionPrev;
    resolveParams.accumulationFrameNum  = accumulationFrameNum;
    resolveParams.staleFrameNumMax      = staleFrameNumMax;
    resolveParams.frameIndex            = frameIndex;

    SharcResolveEntry(entryIndex, sharcParams, resolveParams);
}

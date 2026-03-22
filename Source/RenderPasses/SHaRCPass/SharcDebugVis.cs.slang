/***************************************************************************
 * SharcDebugVis.cs.slang — Visualize SHaRC cached radiance at primary hits.
 *
 * Reads VBuffer for primary hit positions, queries the resolved SHaRC
 * cache, and outputs cached radiance directly as pixel color.
 * Also supports hash grid debug coloring (no cache data needed).
 ***************************************************************************/

import RenderPasses.SHaRCPass.SharcCommon;
import Scene.HitInfo;
import Scene.HitInfoType;

// V-buffer input (primary hits computed by VBufferRT)
Texture2D<PackedHitInfo> gVBuffer;

// World position + normal from G-buffer (written by GBufferRT or similar)
Texture2D<float4> gWorldPos;   // xyz = position, w = hit flag
Texture2D<float4> gWorldNorm;  // xyz = normal

// Output
RWTexture2D<float4> gOutput;

// SHaRC buffers (bound from dictionary)
RWStructuredBuffer<uint64_t>            gHashEntries;
RWStructuredBuffer<SharcPackedData>     gResolved;

cbuffer SharcVisCB
{
    // HashGridParameters
    float3  cameraPosition;
    float   logarithmBase;
    float   sceneScale;
    float   levelBias;

    // Vis settings
    uint2   frameDim;
    uint    debugMode;       // 0 = cached radiance, 1 = hash grid coloring, 2 = occupancy
    float   exposureScale;   // multiply output for visibility (default 1.0)
    uint    capacity;
};

[numthreads(16, 16, 1)]
void csSharcDebugVis(uint3 tid : SV_DispatchThreadID)
{
    uint2 pixel = tid.xy;
    if (any(pixel >= frameDim))
        return;

    float4 posW  = gWorldPos[pixel];
    float4 normW = gWorldNorm[pixel];

    // No surface hit
    if (posW.w == 0.f)
    {
        gOutput[pixel] = float4(0.f, 0.f, 0.f, 1.f);
        return;
    }

    float3 position = posW.xyz;
    float3 normal   = normalize(normW.xyz);

    // Assemble grid parameters
    HashGridParameters gridParams;
    gridParams.cameraPosition = cameraPosition;
    gridParams.logarithmBase  = logarithmBase;
    gridParams.sceneScale     = sceneScale;
    gridParams.levelBias      = levelBias;

    float3 color = float3(0.f);

    if (debugMode == 0)
    {
        // Mode 0: Show cached radiance from resolved buffer
        HashMapData hashMapData;
        hashMapData.capacity          = capacity;
        hashMapData.hashEntriesBuffer = gHashEntries;

        // Build minimal SharcParameters for query
        SharcParameters sharcParams;
        sharcParams.gridParameters = gridParams;
        sharcParams.hashMapData    = hashMapData;
        sharcParams.resolvedBuffer = gResolved;

        SharcHitData hitData;
        hitData.positionWorld = position;
        hitData.normalWorld   = normal;

        float3 radiance;
        bool hit = SharcGetCachedRadiance(sharcParams, hitData, radiance, /*debug=*/true);

        color = hit ? radiance * exposureScale : float3(0.05f, 0.0f, 0.0f);  // dark red = miss
    }
    else if (debugMode == 1)
    {
        // Mode 1: Hash grid debug coloring (no cache data needed)
        color = HashGridDebugColoredHash(position, normal, gridParams);
    }
    else if (debugMode == 2)
    {
        // Mode 2: Cache occupancy overlay
        HashMapData hashMapData;
        hashMapData.capacity          = capacity;
        hashMapData.hashEntriesBuffer = gHashEntries;
        color = HashGridDebugOccupancy(pixel, frameDim, hashMapData);
    }

    gOutput[pixel] = float4(color, 1.f);
}

/***************************************************************************
 * PrepareSurfaceData.cs.slang
 *
 * Prepares surface data from GBuffer/VBuffer for RTXDI light sampling.
 * Identical to Falcor's RTXDIPass/PrepareSurfaceData.cs.slang —
 * no VisCache involvement at this stage.
 ***************************************************************************/

import Scene.Scene;
import Scene.HitInfo;
import Scene.ShadingData;
import Utils.Math.MathHelpers;
import Rendering.RTXDI.RTXDI;

Texture2D<PackedHitInfo> gVBuffer;

[numthreads(8, 8, 1)]
void csPrepareSurfaceData(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    uint2 pixel = dispatchThreadId.xy;
    if (any(pixel >= gRTXDI.frameDim)) return;

    HitInfo hitInfo = HitInfo(gVBuffer[pixel]);
    if (!hitInfo.isValid()) return;

    if (hitInfo.getType() != HitType::Triangle) return;

    TriangleHit tri = hitInfo.getTriangleHit();
    VertexData v = gScene.getVertexData(tri);
    uint materialID = gScene.getMaterialID(tri.instanceID);

    float3 viewDir = normalize(gScene.camera.getPosition() - v.posW);
    ShadingData sd = gScene.materials.prepareShadingData(v, materialID, viewDir);

    gRTXDI.setSurfaceData(pixel, v.posW, sd.N, 1.0f);
}

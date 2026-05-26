/***************************************************************************
 # ReSTIRNEEPass/LoadShadingData.slang
 #
 # Thin stub: re-exports `loadVertexData` and `loadShadingData` from the
 # shared `RenderPasses.PathTraceCommon.LoadShadingData` module and keeps
 # the RT-only `computeDerivativesAtPrimaryTriangleHit` helper plus the
 # scene-flag-gated `getMaterialInstanceHints` policy.
 *************************************************************************/
#include "Scene/SceneDefines.slangh"
__exported import RenderPasses.PathTraceCommon.LoadShadingData;
import Rendering.Materials.TexLODHelpers;
import Utils.Math.MathHelpers;
import Params;

/** Compute derivatives at primary triangle hit.
*/
void computeDerivativesAtPrimaryTriangleHit(const TriangleHit hit, uint2 pixel, uint2 frameDim, out float2 ddx, out float2 ddy)
{
    // Get world space position
    VertexData v = gScene.getVertexData(hit);
    float hitT = length(v.posW - gScene.camera.getPosition());
    const float3 nonNormalizedRayDir = gScene.camera.computeNonNormalizedRayDirPinhole(pixel, frameDim);
    float3 rayDir = normalize(nonNormalizedRayDir);

    float3 dDdx, dDdy;
    computeRayDirectionDifferentials(nonNormalizedRayDir, gScene.camera.data.cameraU, gScene.camera.data.cameraV, frameDim, dDdx, dDdy);

    RayDiff rd = RayDiff(float3(0.f), float3(0.f), dDdx, dDdy);
    rd = rd.propagate(v.posW.xyz, rayDir, hitT, v.faceNormalW);

    // Bounce using primary hit geometry.
    const float4x4 worldMat = gScene.getWorldMatrix(hit.instanceID);
    const float3x3 worldInvTransposeMat = gScene.getInverseTransposeWorldMatrix(hit.instanceID);
    const uint3 vertexIndices = gScene.getIndices(hit.instanceID, hit.primitiveIndex);
    StaticVertexData vertices[3] = { gScene.getVertex(vertexIndices[0]), gScene.getVertex(vertexIndices[1]), gScene.getVertex(vertexIndices[2]) };
    float2 dBarydx, dBarydy;
    float3 unnormalizedN, normals[3];

    prepareRayDiffAtHitPoint(v, vertices, hit.getBarycentricWeights(), rayDir, worldMat, worldInvTransposeMat, rd, unnormalizedN, normals, dBarydx, dBarydy, ddx, ddy);
}

/** Determine hints to use when creating the material instance.
*/
uint getMaterialInstanceHints(const HitInfo hit, const bool isPrimary)
{
    uint hints = 0;
    if (hit.getType() == HitType::Triangle || hit.getType() == HitType::DisplacedTriangle)
    {
#if GBUFFER_ADJUST_SHADING_NORMALS
        if (kAdjustShadingNormals || isPrimary) hints |= (uint)MaterialInstanceHints::AdjustShadingNormal;
#else
        if (kAdjustShadingNormals && !isPrimary) hints |= (uint)MaterialInstanceHints::AdjustShadingNormal;
#endif
    }
    return hints;
}

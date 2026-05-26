/***************************************************************************
 # LoadShadingData.slang — shared vertex/shading-data loader.
 #
 # Hosts the bit-identical bodies of `loadVertexData` and `loadShadingData`
 # that every Falcor-PathTracer-lineage plugin used to copy verbatim
 # (PathTracerX + ReSTIRDIPass / ReSTIRDIReferencePass / ReSTIRNEEPass /
 #  ReSTIRBDPTPass / BDPTPass).
 #
 # Kept per-pass (NOT here):
 #   - `getMaterialInstanceHints` — policy diverges across passes
 #     (BDPT unconditional vs PT's GBUFFER_ADJUST_SHADING_NORMALS-gated form).
 #   - `computeDerivativesAtPrimaryTriangleHit` — RT-only, depends on
 #     pass-local Params macros.
 #
 # Falcor 8: `prepareShadingData` no longer takes an ITextureSampler; LOD
 # is handled internally by the material system. The previous `loadShadingData`
 # 4-arg form has been dropped — pass-local stubs adapt their call sites.
 *************************************************************************/
#include "Scene/SceneDefines.slangh"
__exported import Scene.Shading;
import Scene.Material.ShadingUtils;
import Utils.Math.MathHelpers;

/** Setup vertex data based on hit point.
    \param[in] hit Hit information.
    \param[in] rayOrigin Ray origin.
    \param[in] rayDir Normalized ray direction.
    \param[out] materialID Material ID.
    \return VertexData struct.
*/
VertexData loadVertexData(const HitInfo hit, const float3 rayOrigin, const float3 rayDir, out uint materialID)
{
    VertexData v = {};
    materialID = {};

#if SCENE_HAS_GEOMETRY_TYPE(GEOMETRY_TYPE_TRIANGLE_MESH)
    if (hit.getType() == HitType::Triangle)
    {
        const TriangleHit triangleHit = hit.getTriangleHit();
        StaticVertexData vertices[3];
        v = gScene.getVertexData(triangleHit, vertices);
        materialID = gScene.getMaterialID(triangleHit.instanceID);
    }
#endif
#if SCENE_HAS_GEOMETRY_TYPE(GEOMETRY_TYPE_DISPLACED_TRIANGLE_MESH)
    if (hit.getType() == HitType::DisplacedTriangle)
    {
        const DisplacedTriangleHit displacedTriangleHit = hit.getDisplacedTriangleHit();
        v = gScene.getVertexData(displacedTriangleHit, -rayDir);
        materialID = gScene.getMaterialID(displacedTriangleHit.instanceID);
    }
#endif
#if SCENE_HAS_GEOMETRY_TYPE(GEOMETRY_TYPE_CURVE)
    if (hit.getType() == HitType::Curve)
    {
        const CurveHit curveHit = hit.getCurveHit();
        v = gScene.getVertexDataFromCurve(curveHit);
        materialID = gScene.getMaterialID(curveHit.instanceID);
    }
#endif
#if SCENE_HAS_GEOMETRY_TYPE(GEOMETRY_TYPE_SDF_GRID)
    if (hit.getType() == HitType::SDFGrid)
    {
        const SDFGridHit sdfGridHit = hit.getSDFGridHit();
        v = gScene.getVertexDataFromSDFGrid(sdfGridHit, rayOrigin, rayDir);
        materialID = gScene.getMaterialID(sdfGridHit.instanceID);
    }
#endif
    return v;
}

/** Setup ShadingData based on loaded vertex/material attributes for a hit point.
    \param[in] hit Hit information.
    \param[in] rayOrigin Ray origin.
    \param[in] rayDir Normalized ray direction.
    \return ShadingData struct.
*/
ShadingData loadShadingData(const HitInfo hit, const float3 rayOrigin, const float3 rayDir)
{
    uint materialID = {};

    VertexData v = loadVertexData(hit, rayOrigin, rayDir, materialID);
    ShadingData sd = gScene.materials.prepareShadingData(v, materialID, -rayDir);
    return sd;
}

/***************************************************************************
 # BDPTPass/LoadShadingData.slang
 #
 # Thin stub: re-exports `loadVertexData` and `loadShadingData` from the
 # shared `RenderPasses.PathTraceCommon.LoadShadingData` module and keeps
 # BDPT's divergent `getMaterialInstanceHints` policy (unconditionally adjusts
 # shading normals on primary AND secondary triangle hits — see comment below).
 *************************************************************************/
__exported import RenderPasses.PathTraceCommon.LoadShadingData;
import Rendering.Materials.MaterialInstanceHints;
import Scene.HitInfo;

/** Determine hints to use when creating the material instance.
    Mirror of Falcor PathTracer's getMaterialInstanceHints — always sets
    AdjustShadingNormal on primary hits (and on all hits if scene-level
    adjustShadingNormals is enabled). Without this hint, shading normals
    can point opposite to the incoming ray, producing BSDF sample directions
    in the wrong hemisphere — large efficiency loss on multi-bounce / oblique
    geometry (see KNOWN_BIAS.md: 60x BSDF-hit-rate gap on Cornell+Slit).

    BDPT diverges from PathTracerX here: PT gates this on the scene-level
    kAdjustShadingNormals compile-time flag via GBUFFER_ADJUST_SHADING_NORMALS;
    BDPT doesn't have that plumbed in, so we unconditionally adjust on primary
    AND secondary hits (matches PathTracer's behavior when adjustShadingNormals
    is set true on the graph).
*/
uint getMaterialInstanceHints(const HitInfo hit, const bool isPrimary)
{
    uint hints = 0;
    if (hit.getType() == HitType::Triangle)
    {
        hints |= (uint)MaterialInstanceHints::AdjustShadingNormal;
    }
    return hints;
}

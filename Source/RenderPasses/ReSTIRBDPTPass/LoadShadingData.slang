/***************************************************************************
 # ReSTIRBDPTPass/LoadShadingData.slang
 #
 # Thin stub: re-exports `loadVertexData` and `loadShadingData` from the
 # shared `RenderPasses.PathTraceCommon.LoadShadingData` module and keeps
 # the same `getMaterialInstanceHints` policy as the vanilla BDPTPass
 # (unconditionally adjusts shading normals on triangles — see KNOWN_BIAS).
 *************************************************************************/
__exported import RenderPasses.PathTraceCommon.LoadShadingData;
import Rendering.Materials.MaterialInstanceHints;
import Scene.HitInfo;

/** Determine hints to use when creating the material instance.
    Matches BDPTPass's divergent policy — unconditional AdjustShadingNormal
    on triangle hits (60× BSDF-hit-rate gap closure on Cornell+Slit; see
    BDPTPass/KNOWN_BIAS.md). Task #17 ported this from BDPTPass.
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

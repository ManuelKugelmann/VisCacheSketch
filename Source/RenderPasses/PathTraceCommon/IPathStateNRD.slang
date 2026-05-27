/***************************************************************************
 # IPathStateNRD.slang — minimal interface that NRD-buffer writers need
 # from a PathState. Each consumer plugin (PathTracerX + ReSTIRDIPass +
 # ReSTIRDIReferencePass + ReSTIRNEEPass) keeps its own concrete
 # `PathState` struct but conforms to this interface via a one-line
 # `extension PathState : IPathStateNRD { ... }` in its PathState.slang.
 #
 # Why: PathState's full shape diverges across plugins (NEE adds K-RIS
 # state, etc.) but the NRD-write surface is identical. Pulling the
 # surface into an interface lets `NRDHelpers.slang` live in
 # PathTraceCommon as generic-over-PathState functions, instead of being
 # copied verbatim into every plugin.
 *************************************************************************/

interface IPathStateNRD
{
    uint getSampleIdx();
    uint getVertexIndex();
    bool isDeltaReflectionPrimaryHit();
    bool isDeltaTransmissionPath();
    bool isDiffusePrimaryHit();
    bool isSpecularPrimaryHit();
    float3 getL();              ///< Accumulated path contribution (PathState.L).
    float  getSceneLengthF32(); ///< Path length in scene units (PathState.sceneLength, promoted to f32).
};

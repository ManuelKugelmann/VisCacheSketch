add_plugin(BDPTPass)

# Vanilla bidirectional path tracer extracted from ReSTIRBDPTPass.
# Camera-trace + light-trace + MIS-weighted connections — the same role
# for BDPT that Falcor's PathTracer plays for unidirectional PT.
# ReSTIR layers (temporal / spatial reuse, caustic shift, reservoir
# resampling) live in ReSTIRBDPTPass.

target_sources(BDPTPass PRIVATE
    BitfieldMacros.slangh
    LoadShadingData.slang
    Params.slang
    PathGenerator.slang
    PathReservoir.slang
    LightVertexCache.slang
    ReflectTypes.cs.slang
    BDPT.cpp
    BDPT.h
    BDPT.cs.slang
)

target_copy_shaders(BDPTPass RenderPasses/BDPTPass)

target_source_group(BDPTPass "RenderPasses")

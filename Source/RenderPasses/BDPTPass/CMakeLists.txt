add_plugin(BDPTPass)

# Vanilla bidirectional path tracer.
# Camera-trace + light-trace + MIS-weighted connections — the BDPT
# analog of Falcor's built-in PathTracer for unidirectional PT.

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

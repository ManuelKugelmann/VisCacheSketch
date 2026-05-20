add_plugin(BDPTPass)

# Vanilla bidirectional path tracer extracted from ReSTIRBDPTPass.
# Forces ReSTIR resampling / temporal / caustic layers off, so this
# pass plays the same role for BDPT that Falcor's PathTracer plays
# for unidirectional PT — a deterministic baseline.

target_sources(BDPTPass PRIVATE
    BitfieldMacros.slangh
    HashMap.slang
    HashMap.cs.slang
    HashMap.cpp
    HashMap.h
    LoadShadingData.slang
    Params.slang
    PathGenerator.slang
    PathReservoir.slang
    PathShift.slang
    LightVertexCache.slang
    ReflectTypes.cs.slang
    BDPT.cpp
    BDPT.h
    SpatialReuse.cs.slang
    TemporalReuse.cs.slang
    BDPT.cs.slang
)

target_copy_shaders(BDPTPass RenderPasses/BDPTPass)

target_source_group(BDPTPass "RenderPasses")

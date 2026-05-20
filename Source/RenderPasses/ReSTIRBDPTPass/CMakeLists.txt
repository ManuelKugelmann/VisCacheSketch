add_plugin(ReSTIRBDPT)

target_sources(ReSTIRBDPT PRIVATE
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
    ReSTIRBDPT.cpp
    ReSTIRBDPT.h
    SpatialReuse.cs.slang
    TemporalReuse.cs.slang
    BDPT.cs.slang
)

target_copy_shaders(ReSTIRBDPT RenderPasses/ReSTIRBDPT)

target_source_group(ReSTIRBDPT "RenderPasses")

add_plugin(ReSTIRBDPTPass)

target_sources(ReSTIRBDPTPass PRIVATE
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
    ResolveLightTrace.cs.slang
    ResolveLightTraceShift.cs.slang
    TemporalShiftPrev.cs.slang
    TemporalShiftCaustics.cs.slang
)

target_copy_shaders(ReSTIRBDPTPass RenderPasses/ReSTIRBDPTPass)

target_source_group(ReSTIRBDPTPass "RenderPasses")

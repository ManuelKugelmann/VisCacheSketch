add_plugin(ReSTIRPTPass)

target_sources(ReSTIRPTPass PRIVATE
    ReSTIRPTPass.h
    ReSTIRPTPass.cpp
    # Slang shaders (1:1 from DQLin ReSTIR PT)
    Params.slang
    StaticParams.slang
    PathState.slang
    PathReservoir.slang
    PathBuilder.slang
    PathTracer.slang
    Shift.slang
    LoadShadingData.slang
    NRDHelpers.slang
    GeneratePaths.cs.slang
    TracePass.cs.slang
    TemporalReuse.cs.slang
    SpatialReuse.cs.slang
    TemporalPathRetrace.cs.slang
    SpatialPathRetrace.cs.slang
    ComputePathReuseMISWeights.cs.slang
    ReflectTypes.cs.slang
)

target_copy_shaders(ReSTIRPTPass RenderPasses/ReSTIRPTPass)

target_source_group(ReSTIRPTPass "RenderPasses")


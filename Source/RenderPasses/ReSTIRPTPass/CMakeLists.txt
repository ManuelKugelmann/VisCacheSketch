add_plugin(ReSTIRPTPass)

target_sources(ReSTIRPTPass PRIVATE
    ReSTIRPTPass.h
    ReSTIRPTPass.cpp
    # Slang shaders (verbatim copy from Source/RenderPasses/ReSTIRPTPass/;
    # see project_restirpt2d_status memory + Falcor/LOCAL_FIXES.md for why
    # we maintain this as a separate near-byte-identical sibling plugin).
    Params.slang
    StaticParams.slang
    PathState.slang
    PathReservoir.slang
    PathReservoirCellPool.slang
    PathBuilder.slang
    PathTracer.slang
    Falcor8Compat.slang
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

target_copy_data(ReSTIRPTPass ReSTIRPTPass)

target_source_group(ReSTIRPTPass "RenderPasses")

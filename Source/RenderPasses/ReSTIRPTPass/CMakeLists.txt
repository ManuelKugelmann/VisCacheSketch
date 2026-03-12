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

target_compile_options(ReSTIRPTPass PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:
        /we4456  /we4457  /we4458  /we4715
    >
    $<$<CXX_COMPILER_ID:GNU>:
        -Werror=shadow
        -Werror=return-type
    >
    $<$<CXX_COMPILER_ID:Clang>:
        -Werror=shadow
        -Werror=return-type
    >
)

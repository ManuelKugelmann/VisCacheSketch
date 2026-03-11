add_plugin(ReSTIRPTPass)

target_sources(ReSTIRPTPass PRIVATE
    ReSTIRPTPass.h
    ReSTIRPTPass.cpp
    ReSTIRPTCommon.slang
    InitialSampling.cs.slang
    TemporalReuse.cs.slang
    SpatialReuse.cs.slang
    FinalShading.cs.slang
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

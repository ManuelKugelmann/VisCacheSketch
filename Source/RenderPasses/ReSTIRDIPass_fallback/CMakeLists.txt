add_plugin(ReSTIRDIPass)

target_sources(ReSTIRDIPass PRIVATE
    ReSTIRDIPass.h
    ReSTIRDIPass.cpp
    PrepareSurfaceData.cs.slang
    FinalShading.cs.slang
)

target_copy_shaders(ReSTIRDIPass RenderPasses/ReSTIRDIPass)

target_source_group(ReSTIRDIPass "RenderPasses")

target_compile_options(ReSTIRDIPass PRIVATE
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

add_plugin(ReSTIRGIPass)

target_sources(ReSTIRGIPass PRIVATE
    ReSTIRGIPass.h
    ReSTIRGIPass.cpp
    InitialSampling.cs.slang
    TemporalReuse.cs.slang
    SpatialReuse.cs.slang
    FinalShading.cs.slang
    SpatialReuse_VisCache_delta.slang
)

target_copy_shaders(ReSTIRGIPass RenderPasses/ReSTIRGIPass)

target_source_group(ReSTIRGIPass "RenderPasses")

# Warning escalations — same policy as VisCache (see VisCache/CMakeLists.txt)
target_compile_options(ReSTIRGIPass PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:
        /we4456  # local variable hides another local
        /we4457  # local variable hides function parameter
        /we4458  # local variable hides class member
        /we4715  # not all control paths return a value
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

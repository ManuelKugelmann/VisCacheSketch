add_plugin(VisCache)

target_sources(VisCache PRIVATE
    VisCache.h
    VisCache.cpp
    VisCache.slang
    VisCacheInsert.cs.slang
    VisCacheDecay.cs.slang
    ShadingCV.slang
)

target_copy_shaders(VisCache RenderPasses/VisCache)

target_source_group(VisCache "RenderPasses")

# ---------------------------------------------------------------------------
# Warning policy for VisCache plugins.
# Falcor's PUBLIC compile options (/W4 /WX on MSVC, -Wall on GCC) are
# inherited automatically.  Here we escalate hiding/shadowing and missing-
# return-value warnings to errors (not covered by Falcor's /we list) and
# keep the rest of Falcor's noise suppressions.
# ---------------------------------------------------------------------------
target_compile_options(VisCache PRIVATE
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

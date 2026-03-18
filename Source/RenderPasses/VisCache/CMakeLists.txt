add_plugin(VisCachePass)

target_sources(VisCachePass PRIVATE
    VisCache.h
    VisCache.cpp
    VisCache.slang
    VisCacheDiagnostics.slang
    VisCacheInsert.cs.slang
    VisCacheDecay.cs.slang
    VisCachePathTracer.slang
    VisCacheRTXDI.slang
    VisCacheDiagPass.cs.slang
    VisCacheMinimalPT.slang
    RevalidationCommon.slang
    ShadingCV.slang
)

target_copy_shaders(VisCachePass RenderPasses/VisCache)

# Deploy project scripts to build output (graph configs, smoke tests, etc.)
set(_viscache_project_root "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
if(EXISTS "${_viscache_project_root}/scripts/smoke_test.py")
    add_custom_command(TARGET VisCachePass POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${_viscache_project_root}/scripts"
            "${FALCOR_OUTPUT_DIRECTORY}/scripts/VisCache"
        COMMENT "VisCachePass: Deploying project scripts"
    )
endif()

target_source_group(VisCachePass "RenderPasses")

# ---------------------------------------------------------------------------
# Warning policy for VisCache plugins.
# Falcor's PUBLIC compile options (/W4 /WX on MSVC, -Wall on GCC) are
# inherited automatically.  Here we escalate hiding/shadowing and missing-
# return-value warnings to errors (not covered by Falcor's /we list) and
# keep the rest of Falcor's noise suppressions.
# GCC: -Werror=shadow=local (not =shadow) avoids false positives from
# Falcor headers where constructor params shadow members (standard C++).
# ---------------------------------------------------------------------------
target_compile_options(VisCachePass PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:
        /we4456  # local variable hides another local
        /we4457  # local variable hides function parameter
        /we4458  # local variable hides class member
        /we4715  # not all control paths return a value
    >
    $<$<CXX_COMPILER_ID:GNU>:
        -Werror=shadow=local
        -Werror=return-type
    >
    $<$<CXX_COMPILER_ID:Clang>:
        -Werror=shadow
        -Werror=return-type
    >
)

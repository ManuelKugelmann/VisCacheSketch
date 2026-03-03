# CMakeLists.txt — VisHashFilter RenderPass plugin
# Place this file at: Source/RenderPasses/VisHashFilter/CMakeLists.txt
# Then add the following line to Source/RenderPasses/CMakeLists.txt:
#   add_subdirectory(VisHashFilter)

cmake_minimum_required(VERSION 3.21)

add_plugin(VisHashFilter)

target_sources(VisHashFilter PRIVATE
    VisHashFilter.h
    VisHashFilter.cpp
)

# Slang shaders are discovered automatically by Falcor's build system
# via the .slang extension — no explicit listing needed.
# They are copied to the output shader directory at build time.

target_copy_shaders(VisHashFilter
    VisHashFilter.slang
    VisHashInsert.cs.slang
    VisHashDecay.cs.slang
    ShadingCV.slang
)

# Require SM 6.5 for WaveMatch (ablation toggle C)
# Falls back gracefully if SM 6.5 unavailable: WaveMatch disabled at runtime
target_compile_definitions(VisHashFilter PRIVATE
    VHF_SM65_WAVEMATCH=$<IF:$<BOOL:${FALCOR_GFX_D3D12}>,1,0>
)

target_link_libraries(VisHashFilter PRIVATE
    Falcor
)

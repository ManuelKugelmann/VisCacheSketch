# CMakeLists.txt — ReSTIRGIPass RenderPass plugin (Falcor 8.0)
#
# Ported from DQLin/ReSTIR_PT with MLVHF revalidation integration.
# Depends on VisHashFilter plugin (for Slang imports at shader compile time).
#
# Add to Source/RenderPasses/CMakeLists.txt:
#   add_subdirectory(ReSTIRGIPass)

cmake_minimum_required(VERSION 3.21)

add_plugin(ReSTIRGIPass)

target_sources(ReSTIRGIPass PRIVATE
    ReSTIRGIPass.h
    ReSTIRGIPass.cpp
    # TODO: Add remaining DQLin .cpp files after porting
)

target_copy_shaders(ReSTIRGIPass
    SpatialReuse.cs.slang
    SpatialReuse_MLVHF_delta.slang
    # TODO: Add remaining DQLin .slang files after porting:
    # InitialSampling.cs.slang
    # TemporalReuse.cs.slang
    # FinalShading.cs.slang
    # PathReservoir.slang
)

target_link_libraries(ReSTIRGIPass PRIVATE
    Falcor
    VisHashFilter  # for Slang import resolution
)

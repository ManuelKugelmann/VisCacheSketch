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

# Copy data files (16RooksPattern256.txt, pyscenes) to build output.
# target_copy_shaders only handles .slang/.hlsl — data files need explicit rules.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/Data")
    add_custom_command(TARGET ReSTIRPTPass POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${CMAKE_CURRENT_SOURCE_DIR}/Data"
            "${FALCOR_OUTPUT_DIRECTORY}/data/ReSTIRPTPass"
        COMMENT "Copying ReSTIRPTPass data files"
    )
endif()

target_source_group(ReSTIRPTPass "RenderPasses")


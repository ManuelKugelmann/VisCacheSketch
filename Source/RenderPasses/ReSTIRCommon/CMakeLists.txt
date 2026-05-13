add_plugin(ReSTIRCommon)

target_sources(ReSTIRCommon PRIVATE
    ReSTIRCommon.cpp

    # DI-lineage shared slang utilities deployed under
    # runtime/shaders/RenderPasses/ReSTIRCommon/. Imported by ReSTIRDIPass,
    # ReSTIRDIReferencePass, ReSTIRNEEPass.
    LightReservoir.slang
)

target_copy_shaders(ReSTIRCommon RenderPasses/ReSTIRCommon)

target_source_group(ReSTIRCommon "RenderPasses")

add_plugin(Common)

target_sources(Common PRIVATE
    Common.cpp

    # Shared slang utilities deployed under runtime/shaders/RenderPasses/Common/.
    # Imported by PathTracerX, ReSTIRDIPass, ReSTIRNEEPass, ReSTIRPTPass.
    PathTraceCore.slang
)

target_copy_shaders(Common RenderPasses/Common)

target_source_group(Common "RenderPasses")

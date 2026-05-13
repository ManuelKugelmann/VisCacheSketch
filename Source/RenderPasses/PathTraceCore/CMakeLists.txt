add_plugin(PathTraceCore)

target_sources(PathTraceCore PRIVATE
    PathTraceCore.cpp

    # Shared slang utilities deployed under runtime/shaders/RenderPasses/PathTraceCore/.
    # Truly-common path-tracing primitives: base LightSample (6 fields),
    # ILightSampleBase interface, LightType enum, selection probabilities.
    #
    # DI-lineage extensions (LightSampleDI, rebuilders) live in the
    # ReSTIRCommon plugin instead.
    PathTraceCore.slang
)

target_copy_shaders(PathTraceCore RenderPasses/PathTraceCore)

target_source_group(PathTraceCore "RenderPasses")

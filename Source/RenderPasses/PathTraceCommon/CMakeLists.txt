add_plugin(PathTraceCommon)

target_sources(PathTraceCommon PRIVATE
    PathTraceCommon.cpp

    # Shared slang utilities deployed under runtime/shaders/RenderPasses/PathTraceCommon/.
    # Truly-common path-tracing primitives: base LightSample (6 fields),
    # ILightSampleBase interface, LightType enum, selection probabilities.
    #
    # The slang file keeps its content-descriptive name (PathTraceCore.slang);
    # the plugin dir provides the namespace (RenderPasses.PathTraceCommon.PathTraceCore).
    #
    # DI-lineage extensions (LightSampleDI, rebuilders) live in the
    # ReSTIRCommon plugin instead.
    PathTraceCore.slang
)

target_copy_shaders(PathTraceCommon RenderPasses/PathTraceCommon)

target_source_group(PathTraceCommon "RenderPasses")

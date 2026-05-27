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

    # Shared vertex/shading-data loader — collapses the verbatim-identical
    # `loadVertexData` + `loadShadingData` bodies that every
    # Falcor-PathTracer-lineage plugin used to keep its own copy of.
    # Per-pass stubs still own `getMaterialInstanceHints` (divergent policy).
    LoadShadingData.slang

    # Shared `GuideData` struct (denoising guide channels). Pure packed-data
    # struct with no plugin-local imports; bit-identical copies used to live
    # in each PT-lineage plugin.
    GuideData.slang

    # Shared `ColorType` struct (per-pixel HDR output). Dispatches on the
    # per-plugin `COLOR_FORMAT` preprocessor macro that each consumer
    # plugin's C++ injects via `defines.add("COLOR_FORMAT", ...)`.
    ColorType.slang

    # IPathStateNRD interface — the minimal surface NRDHelpers needs from
    # a PathState. Lets the bit-identical NRD-write functions live in
    # PathTraceCommon as generics, while each plugin's concrete PathState
    # stays divergent (NEE adds K-RIS state, etc.).
    IPathStateNRD.slang

    # Generic-over-IPathStateNRD NRD-buffer writers. Each consumer plugin's
    # NRDHelpers.slang collapses to a one-line `__exported import` stub.
    NRDHelpers.slang
)

target_copy_shaders(PathTraceCommon RenderPasses/PathTraceCommon)

target_source_group(PathTraceCommon "RenderPasses")

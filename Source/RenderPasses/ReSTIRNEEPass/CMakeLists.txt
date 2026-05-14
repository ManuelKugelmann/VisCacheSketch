add_plugin(ReSTIRNEEPass)

target_sources(ReSTIRNEEPass PRIVATE
    ReSTIRNEEPass.h
    ReSTIRNEEPass.cpp

    # ReSTIR NEE — every-vertex K-RIS NEE on top of a clean PathTracerX base.
    # Forked from Source/RenderPasses/PathTracerX (which is itself a fork of
    # Falcor's vanilla PathTracer). The differentiator vs PathTracerX is the
    # K-RIS wrap inside PathTracer.slang's NEE block: at every NEE call-site
    # (every vertex with non-Delta lobes) the pass samples K light candidates,
    # runs streaming RIS with target pdf = unshadowed contribution, then
    # evaluates visibility on the winner only.
    #
    # No buffer-backed reservoirs — purely online RIS per vertex. Spatial /
    # temporal reuse is intentionally NOT implemented (would need per-vertex
    # cell keying, see project_restir_nee_layer for the design discussion).
    ColorType.slang
    GeneratePaths.cs.slang
    GuideData.slang
    LoadShadingData.slang
    NRDHelpers.slang
    Params.slang
    PathState.slang
    PathTracer.slang
    PathTracerNRD.slang
    ReflectTypes.cs.slang
    ResolvePass.cs.slang
    StaticParams.slang
    TracePass.rt.slang
)

target_copy_shaders(ReSTIRNEEPass RenderPasses/ReSTIRNEEPass)

target_source_group(ReSTIRNEEPass "RenderPasses")

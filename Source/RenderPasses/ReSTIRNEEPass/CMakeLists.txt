add_plugin(ReSTIRNEEPass)

target_sources(ReSTIRNEEPass PRIVATE
    ReSTIRNEEPass.h
    ReSTIRNEEPass.cpp

    # Forked from Falcor's PathTracer plugin — inherits the ParameterBlock-based
    # binding plumbing (proven working with ReSTIR DI), bringing the K-RIS +
    # temporal + spatial + retrace logic over byte-identical. Plugin class is
    # ReSTIRNEEPass (distinct registration); slang struct stays `PathTracer`
    # because that's what TracePass.rt.slang and friends still reference.
    # Following ReSTIRPTPass / ReSTIRPTReferencePass precedent — verbatim sibling
    # fork is an accepted maintenance pattern in this project.
    PathTracer.slang
    PathState.slang
    Params.slang
    StaticParams.slang
    ColorType.slang
    GuideData.slang
    NRDHelpers.slang
    PathTracerNRD.slang
    LoadShadingData.slang
    TracePass.rt.slang
    GeneratePaths.cs.slang
    ReflectTypes.cs.slang
    ResolvePass.cs.slang
)

target_copy_shaders(ReSTIRNEEPass RenderPasses/ReSTIRNEEPass)

target_source_group(ReSTIRNEEPass "RenderPasses")

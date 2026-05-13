add_plugin(ReSTIRDIPass)

target_sources(ReSTIRDIPass PRIVATE
    ReSTIRDIPass.h
    ReSTIRDIPass.cpp

    # Forked from Falcor's PathTracer plugin — inherits the ParameterBlock-based
    # binding plumbing (proven working with WS-ReSTIR DI), bringing the K-RIS +
    # temporal + spatial + retrace logic over byte-identical. Plugin class is
    # ReSTIRDIPass (distinct registration); slang struct stays `PathTracer`
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

    # ReSTIRDIPass-local additions (transitional re-exports + design notes)
    Reservoir.slang
    ReservoirIO.slang
)

target_copy_shaders(ReSTIRDIPass RenderPasses/ReSTIRDIPass)

target_source_group(ReSTIRDIPass "RenderPasses")

add_plugin(PathTracerX)

target_sources(PathTracerX PRIVATE
    PathTracerX.h
    PathTracerX.cpp

    # Forked from Falcor's PathTracer plugin (Falcor/Source/RenderPasses/PathTracer/).
    # Carries the VisCache + ReSTIR DI integration. The upstream PathTracer
    # plugin is reverted to NVIDIA-vanilla; project work happens here.
    # Plugin class is PathTracerX (distinct registration); the internal slang
    # struct stays named `PathTracer` because that's what TracePass.rt.slang and
    # friends reference. Same forking pattern as ReSTIRNEEPass /
    # ReSTIRDIReferencePass / ReSTIRPTReferencePass.
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

target_copy_shaders(PathTracerX RenderPasses/PathTracerX)

target_source_group(PathTracerX "RenderPasses")

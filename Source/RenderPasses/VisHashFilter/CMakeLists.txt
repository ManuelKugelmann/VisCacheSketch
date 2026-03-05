add_plugin(VisHashFilter)

target_sources(VisHashFilter PRIVATE
    VisHashFilter.h
    VisHashFilter.cpp
    VisHashFilter.slang
    VisHashInsert.cs.slang
    VisHashDecay.cs.slang
    ShadingCV.slang
)

target_copy_shaders(VisHashFilter RenderPasses/VisHashFilter)

target_source_group(VisHashFilter "RenderPasses")

add_plugin(VisCache)

target_sources(VisCache PRIVATE
    VisCache.h
    VisCache.cpp
    VisCache.slang
    VisCacheInsert.cs.slang
    VisCacheDecay.cs.slang
    ShadingCV.slang
)

target_copy_shaders(VisCache RenderPasses/VisCache)

target_source_group(VisCache "RenderPasses")

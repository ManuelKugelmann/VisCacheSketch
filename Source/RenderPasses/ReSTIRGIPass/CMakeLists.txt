add_plugin(ReSTIRGIPass)

target_sources(ReSTIRGIPass PRIVATE
    ReSTIRGIPass.h
    ReSTIRGIPass.cpp
    SpatialReuse.cs.slang
    SpatialReuse_VisCache_delta.slang
)

target_copy_shaders(ReSTIRGIPass RenderPasses/ReSTIRGIPass)

target_source_group(ReSTIRGIPass "RenderPasses")

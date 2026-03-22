add_plugin(SHaRCPass)

target_sources(SHaRCPass PRIVATE
    SHaRCPass.h
    SHaRCPass.cpp
    SharcTypes.slang
    HashGridCommon.slang
    SharcCommon.slang
    SharcResolve.cs.slang
    SharcDebugVis.cs.slang
)

target_copy_shaders(SHaRCPass RenderPasses/SHaRCPass)

target_source_group(SHaRCPass "RenderPasses")

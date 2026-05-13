add_plugin(CacheCommon)

target_sources(CacheCommon PRIVATE
    CacheCommon.cpp

    # Generic cache-primitive slang utilities deployed under
    # runtime/shaders/RenderPasses/CacheCommon/. Imported by:
    #   - VisCache (cache-table addressing)
    #   - ReSTIRCommon (Reservoir/CellPool indexing)
    #   - ReSTIRPTPass (PathReservoirCellPool — was duplicating pcg3d)
    #
    # Pure-math primitives — no cbuffer dependency, no USE_VISCACHE guard,
    # callable from any consumer without binding VisCache's parameter block.
    CacheHash.slang
)

target_copy_shaders(CacheCommon RenderPasses/CacheCommon)

target_source_group(CacheCommon "RenderPasses")

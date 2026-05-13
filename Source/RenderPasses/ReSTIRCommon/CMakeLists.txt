add_plugin(ReSTIRCommon)

target_sources(ReSTIRCommon PRIVATE
    ReSTIRCommon.cpp

    # DI-lineage shared slang utilities deployed under
    # runtime/shaders/RenderPasses/ReSTIRCommon/. Imported by ReSTIRDIPass,
    # ReSTIRDIReferencePass, ReSTIRNEEPass (and ReSTIRPTPass for CellPool).
    LightReservoir.slang

    # Migrated from VisCache in Phase C-light: Reservoir struct + I/O,
    # CellPool struct + I/O, ReservoirBoilingFilter compute shader.
    # The host buffers (mpReservoirs, mpPixelReservoirs, mpCellPools,
    # mpCellPoolSlots) still live in VisCache.cpp — Phase C-light is
    # slang-only.
    Reservoir.slang
    ReservoirIO.slang
    CellPool.slang
    CellPoolIO.slang
    ReservoirBoilingFilter.cs.slang
)

target_copy_shaders(ReSTIRCommon RenderPasses/ReSTIRCommon)

target_source_group(ReSTIRCommon "RenderPasses")

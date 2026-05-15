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

    # Pairwise MIS bias correction (RTXDI BiasCorrection::Pairwise +
    # Boksansky 2022 §4). Generic primitives shared across DI/NEE/PT —
    # holds the snapshot+stream+finalize state plus the m_j and m_canon
    # formulas. DI uses it via ReSTIRDIPass/PathTracer.slang's merge sites;
    # NEE and PT pick it up when they add reservoir-reuse layers.
    PairwiseMIS.slang
)

target_copy_shaders(ReSTIRCommon RenderPasses/ReSTIRCommon)

target_source_group(ReSTIRCommon "RenderPasses")

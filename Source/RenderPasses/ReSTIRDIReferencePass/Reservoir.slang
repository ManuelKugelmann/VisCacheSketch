/***************************************************************************
 * ReSTIRDIPass Reservoir.slang — DI per-pixel reservoir.
 *
 * Phase 2a transitional: re-exports the Reservoir struct + pack helpers
 * from VisCache, where the types currently live. Phase 6 renames the
 * VisCache file (`Reservoir.slang` → `Source/RenderPasses/ReSTIRDIPass/
 * Reservoir.slang`) and drops the `WS` identifier prefix; until then this
 * forwarder keeps both consumers happy.
 ***************************************************************************/
#pragma once

__exported import RenderPasses.VisCache.Reservoir;

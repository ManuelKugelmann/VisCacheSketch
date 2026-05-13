/***************************************************************************
 * ReSTIRDIPass ReservoirIO.slang — per-pixel reservoir storage I/O.
 *
 * Phase 2a transitional: re-exports `gPixelReservoirs` + `pixelIndex`
 * from VisCache, where the storage currently lives. Phase 6 moves the
 * declaration into this file and renames the global; until then the
 * forwarder keeps both consumers happy.
 ***************************************************************************/
#pragma once

__exported import RenderPasses.ReSTIRCommon.ReservoirIO;

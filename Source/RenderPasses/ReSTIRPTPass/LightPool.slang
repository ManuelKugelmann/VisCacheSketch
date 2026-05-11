/***************************************************************************
 * LightPool.slang
 *
 * P-axis NEE light-sample pool for ReSTIRPT (Tasks #18 + #21).
 *
 * Per user direction 2026-05-11 ("mirror / reuse restirdi plumbing"):
 * imports the WSCellPool struct from VisCache so the pool layout is
 * shared between DI and PT. Same N=128 packed-light-index design that
 * the parallel agent's 61e9946 audit confirmed beats RTXDI on
 * Cornell+Sponza at architectural parity.
 *
 * Status: STEP 1+2 OF MVP — buffer alloc + dispatch wiring (commits
 * e71cb1f → 7346222). RIS-at-insert (`wsCellPoolInsert` analog) in the
 * fill pass + reader-side RIS resample at NEE site are TODO. Until
 * then the pool stores sentinel values and is unused by NEE.
 *
 * Design + four-day implementation plan: see PORT_NOTES_P_AXIS.md.
 **************************************************************************/
#pragma once

// Reuse the DI-side WSCellPool struct directly so the data layout is
// shared between the DI pre-pass and the PT-side fill pass. WSCellPool =
// fingerprint + count + 128 packed (lightTypeIndex, payload, sourcePdf).
import RenderPasses.VisCache.WSCellPool;

/// Compile-time pool slot capacity. Matches WSCellPool's WS_CELL_POOL_N
/// (128) — a single source of truth: changing N in WSCellPool.slang
/// propagates here.
static const uint kLightPoolN = WS_CELL_POOL_N;

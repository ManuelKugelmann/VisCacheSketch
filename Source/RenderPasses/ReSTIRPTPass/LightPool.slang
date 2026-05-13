/***************************************************************************
 * LightPool.slang
 *
 * P-axis NEE light-sample pool for ReSTIRPT (Tasks #18 + #21).
 *
 * Per user direction 2026-05-11 ("mirror / reuse restirdi plumbing"):
 * imports the CellPool struct from VisCache so the pool layout is
 * shared between DI and PT. Same N=1024 packed-light-index design that
 * matches RTXDI's `RTXDI_LightTilePresampleCount` exactly.
 *
 * Status: STEP 1+2 OF MVP — buffer alloc + dispatch wiring (commits
 * e71cb1f → 7346222). RIS-at-insert (`cellPoolInsert` analog) in the
 * fill pass + reader-side RIS resample at NEE site are TODO. Until
 * then the pool stores sentinel values and is unused by NEE.
 *
 * Design + four-day implementation plan: see PORT_NOTES_P_AXIS.md.
 **************************************************************************/
#pragma once

// Reuse the DI-side CellPool struct directly so the data layout is
// shared between the DI pre-pass and the PT-side fill pass. CellPool =
// fingerprint + count + frameLastInsert + _pad + 1024 packed
// (lightTypeIndex, payload, sourcePdf).
import RenderPasses.ReSTIRCommon.CellPool;

/// Compile-time pool slot capacity. Matches CellPool's WS_CELL_POOL_N
/// (1024) — a single source of truth: changing N in CellPool.slang
/// propagates here.
static const uint kLightPoolN = WS_CELL_POOL_N;

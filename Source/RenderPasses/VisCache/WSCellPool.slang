/***************************************************************************
 * WSCellPool.slang
 *
 * §9.4 World-space ReSTIR DI — per-cell N=8-slot candidate buffer
 * (RTXDI-tile semantics: each slot is one pdf-sampled proposal, NO
 * Bitterli streaming RIS at write, NO writer-pHat tracking).
 *
 * Why no Bitterli RIS at write: a per-slot pHat-weighted stream biases
 * the survivor toward the WRITER's shading point. For cross-pixel cells
 * (multiple writers with different pHats), the survivor is optimal for
 * one writer but not the reader — bias on emissive-heavy scenes (Sponza
 * 8.37 → 12.17 at x4 with merge-with-Bitterli-insert; reverts to ~8.37
 * with this RTXDI-tile design). Writer-pHat-AGNOSTIC random-replace per
 * slot mirrors RTXDI's tile presample: each slot is a power-pdf-weighted
 * candidate, the reader does its own K-RIS at its pHat with sourcePdf-
 * based unbias.
 *
 * Layout (104 B / pool):
 *   uint fingerprint;          // 0 = empty sentinel
 *   uint count;                // 0..WS_CELL_POOL_N (high-water mark)
 *   uint lightTypeIndex[8];    // (lightType<<24) | lightIndex
 *   uint payload[8];           // emissive barys / env dir / analytic 0
 *   float sourcePdf[8];        // writer-side NEE proposal pdf — preserved for
 *                              //   reader-side RIS unbias (Convention B), and
 *                              //   to match RTXDI's slot data layout
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.WSReservoir;

// N=128 — Cornell_3AL_x4 trail-closure experiment 2026-05-05 (Task #35).
// Pre-pass sampler change (Power → PdfMipmap) showed 0pp Cornell_3AL impact,
// confirming bottleneck is downstream of fill. Bumping per-cell candidate
// count further (RTXDI uses 1024 per tile; we previously won big on
// Sponza/BistroInt going 16→64 + K_pre 8→32). Doubling again to test if
// diversity is still the binding constraint. K_pre also doubles to keep
// slot-turnover ratio consistent.
static const uint WS_CELL_POOL_N = 128u;

struct WSCellPool
{
    uint  fingerprint;
    uint  count;
    uint  lightTypeIndex[128];
    uint  payload[128];
    float sourcePdf[128];    // writer's NEE proposal density — used at read time for RIS unbias
};

WSCellPool wsCellPoolInit(uint fp)
{
    WSCellPool p;
    p.fingerprint = fp;
    p.count       = 0u;
    [unroll] for (uint i = 0u; i < 128u; ++i)
    {
        p.lightTypeIndex[i] = 0u;
        p.payload[i]        = 0u;
        p.sourcePdf[i]      = 0.f;
    }
    return p;
}

bool wsCellPoolIsEmpty(WSCellPool p) { return p.fingerprint == 0u || p.count == 0u; }

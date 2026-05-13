/***************************************************************************
 * CellPool.slang
 *
 * §9.4 World-space ReSTIR DI — per-cell N=128-slot candidate buffer
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
 * Layout (12,296 B / pool at N=1024 — AoS slot layout):
 *   uint           fingerprint;     // 0 = empty sentinel
 *   uint           count;           // high-water mark of slot index touched (capped at N at read)
 *   CellPoolSlot slots[N]:
 *     uint  lightTypeIndex;        // (lightType<<24) | lightIndex
 *     uint  payload;               // emissive barys / env dir / analytic 0
 *     float sourcePdf;             // writer-side NEE proposal pdf — preserved for
 *                                  //   reader-side RIS unbias (Convention B), and
 *                                  //   to match RTXDI's slot data layout
 *
 * AoS is load-bearing: per-slot 3-field contiguity means a single bufferLoad/
 * bufferStore at one offset handles a whole slot. SoA (separate arrays for
 * lightTypeIndex / payload / sourcePdf) would split slot access across three
 * non-adjacent buffer ops — under concurrent reader/writer, observable as
 * torn reads (sourcePdf from new writer, lightTypeIndex/payload from old).
 ***************************************************************************/

#pragma once
import RenderPasses.VisCache.Reservoir;

// N=128 — interim hold while N=1024 (RTXDI-parity slot count) hits a
// shader-side limit that's not yet diagnosed. The other improvements in
// this iteration (probe-on-collision, atomic-increment wrap fill, per-
// field buffer access, frameLastInsert timestamp) all land and validate
// at N=128 first. Once N=1024 is unblocked the only change needed here
// is the constant + the array sizes.
static const uint WS_CELL_POOL_N = 1024u;

// AoS slot layout — three fields contiguous per slot (12 B), so a single
// `gCellPools[slot].slots[i] = ...` compiles to one struct-store at
// computed offset rather than three SoA bufferStores at offsets 12 KB
// apart. Within-slot coherence is preserved without needing whole-cell
// struct copies — that was the load-bearing property of the old layout
// (reader iterating pool.X[slotR] saw the same writer's contribution).
struct CellPoolSlot
{
    uint  lightTypeIndex;
    uint  payload;
    float sourcePdf;       // writer's NEE proposal density — used at read time for RIS unbias.
    uint  mAndFrame;       // Packed: (M << 16) | (frame & 0xFFFFu).
                           //   - Low 16 bits  = frameStamp (gFrameCount & 0xFFFFu) — freshness filter at reader.
                           //   - High 16 bits = M (sample count, used by PR3d mode; 0 in P3d mode).
                           // 16-byte alignment for single uint4 bufferStore.
};

// Header-only struct — slot data lives in a SEPARATE flat buffer
// (`gCellPoolSlotBuf`) indexed as `cellIdx * WS_CELL_POOL_N + slotIdx`.
// The nested-array-in-struct pattern (slots[N] inside CellPool) trips
// DXC's local-memory validation at N≥1024 even with full-struct buffer
// accesses, so we split. Keeps single bufferLoad/store per slot via the
// flat buffer's element type = CellPoolSlot (16 B).
struct CellPool
{
    uint fingerprint;
    uint count;
};

// Stack-allocated init for callers that hold a local CellPool (rare —
// reader path now uses `lookupCellPool` + direct buffer indexing, avoiding
// the 12 KB struct copy). Slot arrays are intentionally left uninitialised:
// writers fill random slots and readers only access [0, count), so any
// content beyond count is unreachable garbage.
// No longer used in the hot path — readers/writers access the buffer
// directly. Kept for parity with parallel agent's LightPoolFill that may
// still call it. Slot data is intentionally left uninitialised; reader's
// `if (sourcePdf <= 0) continue` guard handles uninit slots (zero-init
// at buffer creation handles the first-frame case).
CellPool cellPoolInit(uint fp)
{
    CellPool p;
    p.fingerprint = fp;
    p.count       = 0u;
    return p;
}

bool cellPoolIsEmpty(CellPool p) { return p.fingerprint == 0u || p.count == 0u; }

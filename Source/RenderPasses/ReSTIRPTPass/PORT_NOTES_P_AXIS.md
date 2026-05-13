# Design note: P-axis NEE pool for ReSTIR-PT (Tasks #18 + #21)

## Status (2026-05-11)

Scaffolding through Step 2b complete (commits e71cb1f → 673b020):
- `restirptPoolAddrMode` / `restirptPoolFootprintPx` cbuffer fields
  (`Params.slang`, parser in `ReSTIRPTPass.cpp`, kwarg in `ReSTIRPT_Graph.py`)
- `mpLightPool` ref<Buffer> allocated when mode != 0 (sized to reservoirCount)
- `LightPool.slang` re-exports VisCache's `CellPool` (N=128 packed
  candidates per slot — single source of truth shared with DI side)
- `LightPoolFill.cs.slang` compute pass dispatched once/frame before
  TracePass when mode != 0. Currently writes sentinel CellPool entries
  (recognizable lightTypeIndex/payload values for downstream verification).
- AB harness `AB_POOL_MODE` env var enables P-axis end-to-end without
  graph edits.

Steps remaining for working MVP (Step 2c real fill + Step 3 NEE-site
read): ~2 days, see "Implementation pivot" section below.

## What it is

P-axis (presample-pool addressing) is orthogonal to R-axis (reservoir
storage) and dispatches **the NEE light-sample pool**. Mirrors the DI side's
`gPoolAddrMode` (RTXDI-style hierarchical 2D pdf as on parallel-agent's
`prePassEmissiveSampler="PdfMipmap"`).

| `restirptPoolAddrMode` | name | pool keying |
|---:|---|---|
| 0 | Pno | no presample pool — fresh `emissiveSampler.sampleLight` at every NEE (current behavior) |
| 1 | P2d | 2D screen-tile pool (RTXDI-tile semantics) |
| 2 | P3d | 3D world-cell pool at `gCellPoolFootprintPx` |

`restirptPoolFootprintPx` interprets:
- P2d: tile side-length in pixels (default 16 → 16×16 = 256 px per tile)
- P3d: cell side-length in pixels (sqrt-area at primary hit's depth)

## Why

Per RTXDI: presampling lights into a shared pool then RIS-selecting at NEE
time amortizes the light-sampling cost across many pixels and lets each
pixel weight by its own BSDF + visibility heuristic. On simple scenes the
pool dilutes (worse than fresh `emissiveSampler`), but on dense-light scenes
the variance reduction wins.

Parallel agent's RDI00 audit found:
- `R3dP3d_noPreK24` cumulative-best across 7-scene matrix (30.54 vs K=48 31.35).
- F00P24 (preOnly = pool-only with K=24) is the **WORST** lane on every
  non-trivial scene; pool-only doesn't work.
- Hybrid F+P (e.g. K=48 = 32 fresh + 16 pool) is the production-conservative
  default; pure-3D-reservoir + no-pre-pass-with-pool is synthetic-best.
- Behavior light-count-dependent: pre-pass HURTS on simple Cornell, HELPS on
  Bistros (mirrors F-vs-P sweep gradient).

## Where to insert (PT side)

Current NEE: `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang:934`
`generateLightSample(...) -> LightSample` calls
`emissiveSampler.sampleLight(vertex.pos, vertex.normal, upperHemisphere, sg, tls)`.

P-axis modification: when `restirptPoolAddrMode != 0`, replace the fresh
sample with a **K-RIS over presampled candidates from the pool keyed by
the path vertex's posW (P3d) or pixel (P2d)**.

## Data structure

```hlsl
// One per pool slot. PackedLightSample = light index + barycentrics + pdf,
// ~12-16 B. With K=16 candidates per slot the pool is small enough to fit
// in L2 for typical tile/cell counts (256 tiles × K=16 = 4 KB; 32K cells ×
// K=16 = 512 KB).
struct LightPoolSlot {
    PackedLightSample samples[K_PER_SLOT];  // K_PER_SLOT compile-time const
};
RWStructuredBuffer<LightPoolSlot> lightPool;  // size = ceil(W*H/poolFootprintPx²) for P2d
                                              //      = cellPoolCapacity for P3d
```

Reuse the existing `CellPool` addressing helpers (`resolveTilePoolAddr`
for P2d, `resolveCellPoolAddr` for P3d) — these are already in
`Source/RenderPasses/VisCache/CellPoolIO.slang`. The PT-side pool would
share those resolvers; keep `gPoolAddrMode` as the dispatch (DI's existing
field) since this is the same pool semantically.

## Fill pass

New compute pass `LightPoolFill.cs.slang` runs BEFORE TracePass each frame:
- One thread per pool slot.
- Each thread does K_PER_SLOT independent `emissiveSampler.sampleLight` calls
  with a slot-keyed seed (so the same slot gets the same K samples each frame
  — temporally stable, not stochastic across frames within a presampling cycle).
- Writes the K packed samples into `lightPool[slotIdx]`.

For P2d (screen-tile) keying: the slot index is `tileX + tileY * tilesX`.
For P3d (world-cell) keying: the slot index is the cell hash mod capacity.

For P3d the fill pass needs to know which cells are LIVE (i.e. claimed by some
pixel's primary hit). One option: piggyback on the cell-pool fingerprint write
from the previous frame and only refill cells that have non-zero fingerprints.
Another: refill ALL cells uniformly (simpler, more wasted work).

## Read at NEE

`generateLightSample` modification:
```hlsl
if (params.restirptPoolAddrMode != 0u) {
    // Resolve pool slot for this vertex.
    uint slotIdx = (params.restirptPoolAddrMode == 1u)
        ? resolveTilePoolAddr(pixel)             // P2d: 2D tile
        : resolveCellPoolAddr(vertex.pos, ...);  // P3d: 3D cell
    LightPoolSlot slot = lightPool[slotIdx];

    // RIS over K candidates: pick by w_i = f̂(c_i) / p(c_i)
    // where f̂ is the BSDF*G*Le target and p is emissiveSampler's pdf.
    float wSum = 0; LightSample chosen = ...;
    for (uint k = 0; k < K_PER_SLOT; ++k) {
        LightSample c = unpack(slot.samples[k]);
        float w = targetPdf(c, vertex) / emissivePdf(c);
        wSum += w;
        if (sampleNext1D(sg) * wSum < w) chosen = c;
    }
    chosen.pdf = wSum / K_PER_SLOT;  // RIS-corrected pdf
    return chosen;
}
// Else: fresh sample (current code path).
```

## Composition with R-axis

P-axis is orthogonal to R-axis storage. Per parallel-agent's findings:

| R-axis × P-axis | usefulness on PT side (extrapolated from DI) |
|---|---|
| R2d  + Pno  | DQLin baseline (current restirpt_2d) |
| R2d  + P2d  | DQLin + RTXDI-tile pool — production-conservative |
| R2d  + P3d  | DQLin + 3D-cell pool — modest variance reduction |
| R3d  + Pno  | current restirpt_pure3d |
| R3d  + P3d  | likely hybrid-best per parallel agent's RDI finding (R3dP3d_noPreK24 = 30.54 cum-best) |
| R3d  + P2d  | unconventional; mismatched dimensionality |

## Estimated effort

- Pool buffer allocation + binding: 1 day (mirror `mpPathReservoirCellPool`).
- Fill pass: 1 day (new compute pass + dispatch wiring).
- NEE-site modification: 1 day (RIS-from-pool helper, dispatch on mode).
- Validation against RPT_ZOO ladder: 1 day (4 new variants × 7 scenes × 3 SPPs).

Total: ~4 days for a working P-axis MVP. Per parallel-agent's findings,
expect modest cumulative wins (~0.5-1pp), with the R3d+P3d combo as the
likely production-canonical winner.

## Why we haven't done it

The R-axis ZOO already gives the headline win (R3d firefly cleanup on
Bistro/Sponza, -46pp cumulative at SPP=16). P-axis is incremental on top
of that and isn't blocking any current work. Defer until either:
- A specific scene shows R3d+Pno underperforming where P3d would help.
- Stage F (Falcor 8 native PathTracer integration, Task #11) starts and
  the pool design needs to be locked in before larger refactors.

## Implementation pivot (2026-05-11): mirror VisCache's CellPool

Per user direction: "mirror / reuse restirdi plumbing". Rather than the
self-contained `LightPool.slang` introduced in commits e71cb1f/b2da2fc,
the cleaner long-term design is to reuse the DI-side `CellPool`
infrastructure from `Source/RenderPasses/VisCache/`:

| DI plumbing | What PT P-axis can reuse |
|---|---|
| `CellPool` struct (N=128 packed light candidates per slot) | identical representation |
| `CellPoolIO.slang::resolvePoolAddr(posA, faceN, pixel)` | mode-dispatched address resolver (P2d tile vs P3d cell) |
| `CellPoolIO.slang::cellPoolFindSlot` | open-addressed double-hash probe |
| `CellPoolIO.slang::cellPoolInsert` | RIS-at-insert with `pHat × V / sourcePdf` weight |
| `CellPoolIO.slang::loadCellPool` | reader-side RIS resample |

**Architectural parity (per parallel agent's 61e9946 audit):**
P2d (screen-tile pool, K=24 pure-pool) BEATS RTXDI on Cornell_1AL and
Sponza by 0.85-1.06pp at architectural parity.

P3d (3D-cell pool) was 2-4pp WORSE than P2d at the time of that audit
— but the parallel agent's own note identifies the cause as **N=128
slots vs RTXDI's 1024 + first-writer-wins discards write effort**, NOT
the 3D-vs-2D architecture itself. They've since landed
`cellPoolFindSlot` (double-hash probe, 2026-05-11) to fix the
collision-handling half of that gap; Sponza re-run pending.

**Provisional guidance** (likely to change once the parallel agent's
Sponza re-run with the collision fix lands):
- Match RTXDI's slot capacity (N=1024, currently 128 in `WS_CELL_POOL_N`
  at `Source/RenderPasses/VisCache/CellPool.slang:38`).
  Memory cost ×8: per-slot grows from ~1 KB → ~8 KB, total ~512 MB for
  a 65K-slot pool (vs ~64 MB at N=128). Tractable for production GPUs.
- Don't hard-default to P2d for PT side. Let the post-fix Sponza data
  decide. Hash collisions are P3d's main weakness; P2d's direct-map
  semantic avoids them entirely but doesn't benefit from world-space
  cell sharing across pixels in close primary regions.

**What blocks the direct reuse:**
Each VisCache helper depends on cbuffer fields (`gCellPoolCapacity`,
`gCellPoolFootprintPx`, `gPoolAddrMode`, `gPoolTileSize`,
`gCellLevel`, `gNormalAddr`, `gNumLevels`, jitter params, etc.).
Those are bound by `VisCachePass`'s cbuffer. ReSTIRPTPass needs either:
(a) the same cbuffer-field plumbing in its own params (one-time
    refactor; field names + parser additions + bind calls — match
    `kRestirptPoolAddrMode`/`kRestirptPoolFootprintPx` pattern from
    commit 2a52663), or
(b) an indirect reference to the VisCachePass's parameter block when
    one is active in the render graph (cross-pass binding, fragile —
    breaks when ReSTIRPTPass runs without VisCache).

Recommend (a). Estimated effort:
- Plumb 8-10 cbuffer fields from `gWS*` namespace to `restirpt*` namespace
  in `Params.slang` + cpp parser/dict: ~1 day.
- Import `CellPool`/`CellPoolIO` slang modules into ReSTIRPTPass's
  shader compile path; rename per-cbuffer-field references in a copy of
  `CellPoolIO.slang` (or extract the helpers into a shared
  `CellPoolHelpers.slang` that doesn't depend on the cbuffer fields,
  taking them as function args): ~1 day.
- Fill pass: do RIS-at-insert per pixel in a Bayer-prepass pattern
  (mirrors VisCache's existing prepass): ~1 day.
- NEE-site reader-side RIS at `generateLightSample`: ~1 day.

Total: ~4 days. The current `LightPool.slang` + `LightPoolFill.cs.slang`
scaffolding (commits e71cb1f → 7346222) is preserved as a stub that
demonstrates buffer alloc + dispatch wiring works end-to-end. The next
implementer should DELETE those files and start from the CellPool
reuse pattern instead.

# Design note: P-axis NEE pool for ReSTIR-PT (Tasks #18 + #21)

## Status

Scaffolding exists (`restirptPoolAddrMode`, `restirptPoolFootprintPx` cbuffer
fields in `Params.slang`, property parser in `ReSTIRPTPass.cpp`, render-graph
kwarg in `scripts/ReSTIRPT_Graph.py`); no pool buffer allocated, no shader
logic. This document specifies the design for a future implementer.

## What it is

P-axis (presample-pool addressing) is orthogonal to R-axis (reservoir
storage) and dispatches **the NEE light-sample pool**. Mirrors the DI side's
`gWSPoolAddrMode` (RTXDI-style hierarchical 2D pdf as on parallel-agent's
`prePassEmissiveSampler="PdfMipmap"`).

| `restirptPoolAddrMode` | name | pool keying |
|---:|---|---|
| 0 | Pno | no presample pool — fresh `emissiveSampler.sampleLight` at every NEE (current behavior) |
| 1 | P2d | 2D screen-tile pool (RTXDI-tile semantics) |
| 2 | P3d | 3D world-cell pool at `gWSCellPoolFootprintPx` |

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

Reuse the existing `WSCellPool` addressing helpers (`wsResolveTilePoolAddr`
for P2d, `wsResolveCellPoolAddr` for P3d) — these are already in
`Source/RenderPasses/VisCache/WSCellPoolIO.slang`. The PT-side pool would
share those resolvers; keep `gWSPoolAddrMode` as the dispatch (DI's existing
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
        ? wsResolveTilePoolAddr(pixel)             // P2d: 2D tile
        : wsResolveCellPoolAddr(vertex.pos, ...);  // P3d: 3D cell
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

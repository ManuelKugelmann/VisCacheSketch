# Unified Reservoir Addressing — K-Slot Cells with All-Slots-As-Neighbourhood

Source: design discussion 2026-05-19, session bd123fd2.
Status: design only; implementation deferred. Architectural sketch for a
"v2 of WS-ReSTIR" reservoir/pool layer.

## Motivation

Today's reservoir / pool layers have grown two independent code paths that
encode what are really the same primitives applied to different address
spaces:

```
R2d (pixel-direct addressing)         R3d (world-cell hash addressing)
└── gPixelReservoirs[pixel.xy]        └── gReservoirs[hash(cell)]
P2d (screen-tile pool)                P3d (world-cell pool)
└── gCellPools[tileIdx]               └── gCellPools[hash(cell)]
```

Plus a separate spatial-reuse pass that re-hashes K jittered cell addresses
and re-fetches them, with `resolveJitteredCell` + tangent-plane jitter math.

The math (RIS / weighted reservoir / MIS) is identical across modes; only
the address function differs. The unified-config push of 2026-05-19
(commits 4b32125, 695282e) collapsed redundant gates (`useCellInRIS`,
`enableCellPool`), but the two-buffer two-codepath split remains.

This doc sketches a deeper unification: one reservoir-storage primitive
(K-slot chunked cells), one insert mechanism (atomic counter),
one read mechanism (load cell → merge K slots). Spatial reuse becomes
intrinsic to read, not a separate pass.

## Architecture

### Storage primitive: K-slot chunked cell

```
struct Cell {
    uint        count;          // 4B atomic, drives slot selection
    Reservoir   slot[K];        // K × 32B = 128B (K=4) or 256B (K=8)
};
```

One reservoir-buffer entry per addressable cell. Each cell holds K
independent reservoirs ("slots"). K is a small constant (4 or 8) so the
cell fits 1-2 cache lines.

### Addressing: pluggable address function

```
addr(pixel, scene) ∈ {
    pixelDirect(pixel)                    // pixel.xy → bucket
    screenTile(pixel / tileSize)          // coarse screen bucket
    worldCellHash(posW, faceN, fp)        // world-space, hashed
}
```

Address function is a property of the variant; the storage primitive is
identical regardless. R2d / R3d / pool / pixel-direct all become POINTS
in this space, not separate code paths.

### Insert: atomic counter, reservoir-sample-replacement

```
slot_idx = atomicAdd(cell.count, 1)
if (slot_idx < K) {
    cell.slot[slot_idx] = reservoir         // fill phase
} else if (rand() * (slot_idx + 1) < K) {
    cell.slot[rand() % K] = reservoir       // replacement phase
}
```

Standard weighted-reservoir-sampling, applied at slot selection. No
Bayer-gated ownership (Bayer requires the single-writer-per-slot
assumption which breaks at multi-bounce). One atomic per insert, on
a small counter — cheap on modern GPUs (Ampere+ L2-resident atomics).

### Read: all-slots-are-neighbourhood

```
// Old: separate spatial-reuse pass with jittered addressing
my_res = load(my_addr)
for i in 1..N_neighbours:
    n_addr = resolveJitteredCell(my_addr, i, jitter)
    n_res = load(n_addr)                    // N separate fetches
    merge(my_res, n_res)

// New: K-slot read IS spatial reuse
cell = load(my_addr)                        // ONE fetch, K reservoirs
my_res = init()
for i in 0..K-1:
    merge(my_res, cell.slot[i])
```

The K reservoirs in a cell are its neighbourhood by construction — they
are exactly the K reservoir-sampled writers who contributed to this cell.
Spatial reuse degenerates into "read your cell, merge all slots".

## Design coordinate system

Each layer is described by a 3-tuple plus optional draw count for pools:

```
R<addrFn>-<K>-<W>x<H>          reservoir layer
P<addrFn>-<K>-<W>x<H>-d<drawK> pool layer (when distinct)
F<freshK>                      K-RIS fresh candidates streamed per reservoir
```

Filename-safe form uses dashes within axis-tuples and underscores between
groups: `ReSTIRDI_R3d-4-2x2_P3d-1024-16x16-d24_TagRole_F17P24_vblind`.

Today's canonical variants in the new coordinates:

| Today's tag                  | New coordinate                                       |
|------------------------------|------------------------------------------------------|
| `R2dP2d_F17P24` (R2dP2d)     | `R2d-1-1x1 · P2d-1024-16x16-d24 · F17`               |
| `R3dP3d_F00P24` (R3dP3d)     | `R3d-1-1x1 · P3d-1024-16x16-d24 · F00`               |
| RTXDI reference (external)   | `R2d-1-1x1 · P2d-128-16x16-d24 · F8`                 |

Future variants the architecture naturally supports:

| Coordinate                             | Description                              |
|----------------------------------------|------------------------------------------|
| `R3d-4-2x2 · P3d-1024-16x16-d24 · F17` | K=4 chunked, fp=2x2 — pure chunking probe |
| `R3d-8-8x8 · P3d-1024-16x16-d24 · F17` | K=8 chunked at coarser fp — spatial-reuse-via-chunk |
| `R2d-4-1x1 · P2d-1024-16x16-d24 · F17` | K=4 per pixel — temporal multi-sample (RTXDI history layers) |
| `R3d-1-1x1 · P3d-128-16x16-d24 · F8`   | RTXDI exact through hashed addressing — direct parity probe |

## Implementation impact

### Drops

- `gPixelReservoirs` and `gReservoirs` as separate buffers — one buffer
  per address-function variant; possibly one shared buffer with pluggable
  index function.
- `spatialNeighbours` cbuffer field (Phase D after current 2026-05-19
  flatten) — collapsed into K.
- `spatialNeighbourCount()` shader helper — becomes constant K.
- `resolveJitteredCell()` + tangent-plane jitter math — no jittered
  neighbour addressing.
- Separate spatial-reuse code blocks in `PathTracer.slang` — replaced by
  the slot-merge loop inside the read step.
- `cellReservoirMerge` (0=identity, 1=Bitterli weighted) — merge is
  always weighted in the K-slot all-slots read.

### Adds

- `K` cbuffer field (new) — slots per cell, small (4–8) constant.
- Cell struct with embedded atomic counter — one structured buffer of
  `{uint count, Reservoir[K] slots}`.
- Atomic-counter insert path (replaces per-pixel-direct write).
- All-slots merge loop on read.

### Preserved

- K-RIS math (streaming `F` candidates into one reservoir slot before
  insert) — unchanged.
- Pairwise MIS bias correction — extends trivially to merging K slots
  (treat each slot as one of K spatial neighbours under pairwise).
- Temporal reuse — orthogonal; can still load a prior-frame reservoir
  and merge into local.
- Address-function abstraction — varies per variant; address logic stays
  inside `resolveCell` per current `ReservoirIO.slang`.

## Equivalences and degenerate cases

- **K=1, addr=pixelDirect, fp=1x1** ≡ today's R2dP2d per-pixel reservoir.
  No chunking, no atomic counter (only 1 writer per cell), no spatial
  reuse from same-cell.
- **K=1, addr=worldHash, fp=1x1** ≡ today's R3dP3d_F00P24 RTXDI-baseline.
  Single slot per world cell, no in-cell spatial reuse.
- **K=N²-pixel-area, addr=screenTile(N), fp=NxN** ≡ RTXDI presample tile
  with N² candidates per tile (modulo: tile holds raw samples, we hold
  reservoirs).
- **K=2, addr=pixelDirect, fp=1x1** ≡ RTXDI history layers (current
  frame slot + last frame slot, ping-pong replacement).

## Quality and performance trade-offs

### Where K-slot wins

1. **Cache locality on read**: one cell fetch returns K reservoirs in
   adjacent memory. Today's spatial reuse re-hashes and re-fetches K
   separate cells.
2. **No atomic write contention**: each writer takes a counter ticket
   (cheap atomic) and writes to one slot independently. Today's K-slot
   alternatives (multi-sample reservoir) require atomic CAS over the
   full multi-record struct.
3. **Multi-bounce safe**: writer count per cell is unpredictable in
   multi-bounce paths (ReSTIRPTPass, ReSTIRNEEPass `USE_NEE_CELLS=1`).
   Atomic counter handles variable writer count; Bayer-ownership does
   not.
4. **Hash function cost**: one hash per pixel for cell address vs
   N+1 hashes for jittered spatial neighbours.

### Where K-slot risks quality

1. **Cell straddles depth/normal discontinuity**: K slots from same cell
   mix samples from different surfaces. Today's jittered-cell spatial
   reuse can be set to gather over nearby cells of the same surface
   (via `cellReservoirFootprintPx` + tangent-plane jitter). K-slot
   removes the jitter freedom.
2. **fp = 1x1 chunked**: pure storage optimization, no algorithmic win.
   K-slot at fp=1x1 with strict ownership = today's per-pixel layer
   with different memory layout. Worth measuring but not transformative.
3. **K too large**: cell record > 1 cache line; bandwidth-limited reads.
   K=4 (128B) is conservative; K=8 (256B) is the upper bound for cache
   friendliness on consumer GPUs (64-128B L1 lines).

### Performance estimates

Estimates (un-instrumented, to be measured on the ladder):

- Insert: ~1 atomic per write (cheap on Ampere+ L2 atomics)
- Read: K reservoir loads from one cell (1 memory transaction if cache
  hits, ≤2 if K=8 straddles cache lines)
- Replacement: per-cell counter wraps after K writers — `rand() % K`
  selects replacement slot, single atomic write of `Reservoir` struct
  (32B, fits coalesced)

vs today's per-pixel-with-jittered-cell-reuse:
- Insert: 1 atomic per write (already)
- Read: N+1 cell hashes (~10 ALU ops each) + N+1 separate memory
  transactions (typically L2 misses across scattered addresses)
- Spatial reuse loop has branchy code paths (fingerprint compare to
  reject home cell collisions)

Net expected ms reduction: tracePass/raytraceScene cost dominated by
memory-bandwidth + register pressure of the spatial-reuse block.
Replacing N scattered fetches with 1 coherent fetch should reduce that
block's contribution. Headline structural win is ambiguous without
measurement; possible 5-20% per-frame reduction in tracePass.

## Validation plan

Each step is a separate ladder run (`RDI00_KSlot??`) to isolate effects:

1. **Equivalence check**: `R3d-1-1x1` and `R3d-4-2x2-strict-ownership`
   should give bit-identical rmse on Sponza (4×1 reservoirs vs 1×4
   reservoirs same data). Confirms chunking is a no-op on the
   single-bounce / strict-ownership path.
2. **Pure chunking probe**: same as (1) but measure ms — should show
   cache-locality benefit even at no algorithmic change.
3. **Cross-slot read enabled**: `R3d-4-2x2-all-slots-merge`. First
   genuine algorithmic change; verify rmse stays within RNG noise of
   today's R3d-1-1x1 + spatialNeighbours=4.
4. **Coarser cell**: `R3d-4-4x4-all-slots-merge`. Tests surface-mismatch
   risk; rmse expected to rise on Bistro's geometry-heavy regions.
5. **Pool extension**: drop separate WSCellPool (P3d-1024 raw samples) and
   replace with `P3d-K-fp-d{drawK}` for K=4-8 reservoir-sampled writer
   contributions per pool cell. Tests whether reservoir-pool subsumes
   raw-sample-pool.
6. **Multi-bounce**: wire into `ReSTIRNEEPass` (the c13939f5 cells path)
   and measure quality lift vs today's single-slot cell reservoir.

Success criterion per step: rmse drift ≤ noise floor (~0.2%) AND
per-frame ms equal or better than today's canonical at the same K
budget.

## Migration path

This is a v2-of-WS-ReSTIR architecture, not an in-place refactor of
the existing code. Recommended approach:

1. Land it as a separate plugin (`ReSTIRDIPassV2` or
   `ReSTIRDIPassKSlot`) alongside existing `ReSTIRDIPass`, similar
   to how `ReSTIRDIReferencePass` coexists.
2. New plugin builds on top of existing `ReSTIRCommon` slang utilities;
   adds the K-slot chunked cell struct + atomic-counter insert + all-
   slots merge as new helpers.
3. Wire a new ladder set (`RDI00_KSlot*`) that compares old vs new
   across the equivalence + algorithmic-change steps above.
4. If perf/quality both win across the 3-scene matrix (Bistro / Sponza
   / Cornell_32PL), promote new plugin to canonical and deprecate old.
5. If old wins in some regime (e.g., R2dP2d sticks with direct
   addressing being faster than chunked at K=1), keep both.

No forward-only-migration burden on the existing R2dP2d / R3dP3d
canonical baselines — they continue to exist and be benchmarked
against the new variants.

## Open questions

- **Slot selection determinism**: atomic counter is deterministic-per-
  frame (insert order matters). RNG seeding for replacement-phase needs
  to be per-cell-per-frame to avoid bias from kernel scheduler order.
  Counter value itself can seed `rand()`.
- **Reservoir struct size with embedded count**: `{uint count, Reservoir[K]}`
  layout vs separate `count[]` array. Embedded keeps cache line locality
  on combined read; separate keeps count-atomic from contending with
  slot reads. Likely embedded wins (counter is touched only on insert,
  read path skips the count word).
- **Cross-slot variance**: K reservoirs in same cell have correlated
  samples (same address → same world region → similar lighting context).
  Merging K correlated samples gives less variance reduction than K
  truly independent samples. Magnitude depends on K and cell size;
  worth measuring.
- **Tile-vs-cell address function for R2d**: should the chunked R2d use
  pixelDirect (current per-pixel buffer, K=2 = history layers) OR
  screenTile (RTXDI-style, K=many per tile)? Different perf characteristics:
  pixelDirect is coherent, screenTile is coarser and reused more.
- **Pool layer collapse**: if reservoir-pool (K=4-8 reservoirs per cell)
  subsumes raw-sample-pool, do we keep WSCellPool (K=1024 raw lights)
  at all? Likely yes for variance-rich many-lights scenes (high pool
  draw count gives RIS quality at modest storage); reservoir-pool is
  for paths where pre-built reservoirs amortize the RIS cost.

## Relation to other planned work

- **Split-pass pipeline** (discussed 2026-05-19, no doc yet): RTXDI's
  multi-pass approach for the trace stage. Orthogonal to this doc but
  composes — K-slot cell structure works equally well in a monolithic
  raygen or a split-pass pipeline. The split-pass conversation is about
  *how* to dispatch the K-RIS+temporal+spatial work (one pass vs many);
  this doc is about *what data structure* holds the reservoirs.
- **Reservoir-pool unification with WSCellPool**: as noted in open
  questions, the K-slot reservoir cells could absorb some of WSCellPool's
  role. Full collapse may not be desirable; partial overlap is.
- **Phase D config flatten**: `spatialNeighbours` field becomes
  redundant under K-slot all-slots-as-neighbourhood. Drop alongside the
  V2 plugin land. Today's R2dP2d_F17P24 / R3dP3d_F00P24 continue using
  spatialNeighbours via the legacy code path.

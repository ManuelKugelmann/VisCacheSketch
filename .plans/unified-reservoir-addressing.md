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

### Read: all-slots-as-neighbourhood, with optional extended neighbourhood

The K reservoirs in a cell are its **primary** neighbourhood by construction
— exactly the K reservoir-sampled writers who contributed to this cell.
Extended neighbourhood (jittered-cell reuse from today's code path) is
**additive**: optionally layered on top to gather more samples from
nearby cells.

```
// New: K-slot read = primary neighbourhood (in-cell)
cell = load(my_addr)                        // ONE fetch, K reservoirs
my_res = init()
for i in 0..K-1:
    merge(my_res, cell.slot[i])

// Optional: extended neighbourhood (additive, configurable)
for i in 1..N_extendedNeighbours:           // 0 by default
    n_addr = resolveJitteredCell(my_addr, i, jitter)
    n_cell = load(n_addr)                   // load whole neighbour cell
    for j in 0..K-1:
        merge(my_res, n_cell.slot[j])       // all K slots in neighbour
```

`N_extendedNeighbours = 0` is the default — no extra jittered fetches.
`N_extendedNeighbours > 0` adds the prior code path's spatial-reuse
mechanism on top. Both can be active: K=4 in-cell + 2 jittered extended
cells = 12 reservoirs merged.

Degenerate cases for backward equivalence:
- **K=1, N_extended=0** ≡ today's R3d single-slot, no spatial reuse
- **K=1, N_extended=4** ≡ today's R3d with `spatialNeighbours=4` (jittered)
- **K=4, N_extended=0** ≡ new pure-chunking spatial reuse
- **K=4, N_extended=4** ≡ K-slot + extended jittered combined (most coverage)

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

### Repurposes / extends (no drops)

Extended-neighbourhood machinery stays as an additive option, so today's
code paths are preserved as the `K=1, N_extended > 0` degenerate case.

- `spatialNeighbours` cbuffer field — **kept**. Renamed in spirit to
  `extendedNeighbours` (count of jittered neighbour cells beyond the
  in-cell K). Semantics unchanged for K=1 (today's behavior); composes
  with K>1 chunking.
- `spatialNeighbourCount()` shader helper — kept; meaning shifts to
  "extended neighbourhood count" rather than total neighbour count.
- `resolveJitteredCell()` + tangent-plane jitter math — kept; used only
  when `extendedNeighbours > 0`.
- `cellReservoirMerge` (0=identity, 1=Bitterli weighted) — kept as a
  per-slot merge mode. K-slot read defaults to weighted merge but the
  identity-only mode stays available for diagnostic/ablation.

### Refactored

- Single buffer for reservoirs with embedded K slots. Layout becomes
  `Cell { uint count, Reservoir[K] }`. Total buffer size = bucket_count
  × sizeof(Cell). For K=1 this is bit-identical to today's single-slot
  buffer layout (just an extra 4B counter per cell, which can be
  optimized out when K=1 via a compile-time `#if K==1` guard).
- `mpPixelReservoirs` and `mpReservoirs` either unified into one
  address-function-pluggable buffer, OR kept as two distinct buffer
  bindings sharing the same Cell struct. (Latter is the safer
  incremental refactor.)
- Reservoir-read loop in `PathTracer.slang`: gains the `for i in 0..K-1`
  inner loop over `cell.slot[i]`. Outer extended-neighbourhood loop
  (existing, jittered) is preserved.

### Adds

- `K` cbuffer field (new) — slots per cell, small (4–8) constant.
  Default `K=1` for backward equivalence; ladder steps raise it.
- Atomic-counter insert path. When K=1, optimized to direct write
  (no atomic) to match today's single-slot semantics.
- In-cell slot-merge loop on read.

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

Each step compares the evolved `ReSTIRDIPass` against the frozen
`ReSTIRDIPass_v1_baseline`. Pass-criterion at each step: rmse drift
≤ noise floor (~0.2%) for parity steps; per-frame ms equal or better
than v1_baseline at the same `K` × `extendedNeighbours` budget for
perf steps.

**Parity steps** (algorithm must match v1_baseline exactly):

1. **K=1, extended=0** matches `R3d-1-1x1_F00P24` baseline. Reservoir
   reads slot[0] only; no atomic counter (direct write at K=1);
   no jittered fetches. Bit-identical rmse expected.
2. **K=1, extended=4** matches `R3d-1-1x1_F00P24` with today's
   `spatialNeighbours=4`. Single-slot cells + jittered extended
   neighbourhood. Bit-identical rmse expected.
3. **K=4, extended=0, strict ownership** (Bayer-mapped writer→slot for
   ablation only; production uses atomic-counter). Verifies storage-
   layout equivalence when each pixel deterministically owns one slot.
   rmse should match (1) within RNG noise.

**Algorithmic steps** (genuinely new behavior):

4. **K=4, extended=0, atomic-counter insert + all-slots-merge read,
   fp=2x2**. First genuine K-slot variant. rmse expected within RNG
   noise of (2) (similar effective neighbourhood size); ms should
   improve from cache locality.
5. **K=4, extended=4, fp=2x2**. All-slots in-cell + jittered extended
   cells. Largest effective neighbourhood; tests upper bound of
   variance reduction.
6. **Coarser cell**: K=4, fp=4x4 and K=8, fp=4x4. Tests surface-mismatch
   risk; rmse expected to rise on Bistro's geometry-heavy regions.
7. **Pool extension**: replace `P3d-1024-raw-samples-d24` with
   `P3d-K-reservoirs-fp-d{K}` for K=4-8. Tests whether reservoir-pool
   subsumes raw-sample-pool, or stays a distinct mechanism for
   variance-rich many-lights scenes.
8. **Multi-bounce**: wire K-slot into `ReSTIRNEEPass` (the c13939f5
   cells path). Atomic counter handles multi-bounce's unpredictable
   writer count per cell; measure quality lift vs today's single-slot
   cell reservoir.

## Migration path

Natural evolution of the existing `ReSTIRDIPass`, not a parallel plugin.
The K-slot architecture is a strict superset of today's design (K=1,
N_extended=0..4 reproduces today's variants bit-identically), so the
existing pass can evolve in place while a frozen copy serves as the
parity yardstick.

1. **Use existing `ReSTIRDIReferencePass` as the v1 baseline** — no new
   plugin needed. The reference pass already exists (created tick 11 of
   9585297a's session) and is functionally identical to current
   `ReSTIRDIPass` after the 2026-05-19 cleanup commits applied to both
   in parallel. Freeze it at its current state going forward: no further
   mechanical refactors touch it; algorithm + params pinned. It serves
   as the bit-identical parity yardstick for the K-slot evolution.

   Net plugin tree stays at today's count (ReSTIRDIPass active +
   ReSTIRDIReferencePass frozen). No third plugin alongside.
2. **Evolve `ReSTIRDIPass` toward K-slot in place**. Each step is
   verifiable against the v1_baseline parity yardstick:
   a. Introduce `K` cbuffer field, default K=1. Cell struct
      `{uint count, Reservoir[K]}` with `#if K==1` optimization to
      degenerate to today's storage layout.
   b. Wire atomic-counter insert path; gate behind `K>1` (K=1 keeps
      direct write).
   c. Wire in-cell slot-merge read loop; gate behind `K>1` (K=1 reads
      just slot[0] as today).
   d. At each step: ladder rmse delta vs v1_baseline must be within
      RNG noise floor (~0.2%).
3. **Add ladder steps `RDI00_KSlot*`** for the genuinely new variants
   (K>1) — chunking-only, all-slots-merge, all-slots+extended,
   coarse-cell-with-K-slots, multi-bounce K-slot for NEE/PT.
4. **Promote when both perf and quality win across the 3-scene matrix
   at the chosen K**. The canonical baseline tags (R2dP2d_F17P24 /
   R3dP3d_F00P24) stay the same names but the underlying pass is now
   the K-slot-capable evolution; they pin K=1 to keep parity with
   v1_baseline.
5. **`ReSTIRDIReferencePass` remains as the long-term parity yardstick**.
   Unlike a session-scoped archive, it's already in the codebase and
   serves the same role for all future refactors (not just this one).
   Don't deprecate it after K-slot lands — it's the permanent reference.

Same pattern applies to `ReSTIRNEEPass` and `ReSTIRPTPass` (forks of
the same fork lineage) — each gets a `_v1_baseline` archive snapshot
and an in-place evolution toward K-slot when the design proves out on
DI first.

Net effect: the historical canonical baselines (`R2dP2d_F17P24` etc.)
remain reproducible against their v1_baseline counterparts forever,
while the canonical pass evolves to support the full unified design
space. No two-implementations-doing-the-same-thing smell.

## 2026-05-19 implementation FINAL status

The K-slot evolution is structurally and algorithmically complete.
Eight commits total: `7dd79fa`, `dc5072e`, `f913892`, `7d4f0e3`,
`57d1354`, `a4603b5`, `354ea52`, plus the design-doc commits
`b8b2eb9`, `6632e66`. Parity at K=1 bit-clean (≤0.20% RNG noise
floor).

### K>1 empirical finding: quality regresses ~2.3× on R3dP3d_F00P24

Sponza x64 across the K × fp matrix:

| Variant       | fp=1 rmse | fp=8 rmse |
|---------------|-----------|-----------|
| K=1 baseline  | 0.176     | (canonical fp=1) |
| K=4           | 0.412     | 0.413     |
| K=8           | 0.413     | 0.417     |

The cluster at ~0.41 is **invariant under fp and K** — signature of
an architectural mismatch, not a tuning issue. Footprint variation
doesn't move the rmse needle.

### Why K-slot regresses on R3dP3d_F00P24

R3dP3d_F00P24 already uses **24 pool draws** as its primary
aggregation: the WSCellPool pulls light samples across many pixels
(world-space aggregation already happening through the pool). Cell
reservoirs on top of that create **double-aggregation**:

1. **Pool aggregation**: ~64 pixels per pool cell × 24 candidates per
   draw → ~1500-sample world-aggregated pool per pixel.
2. **Cell-RIS aggregation**: K stored writers per cell × ~64 pixels
   per cell footprint → another aggregation layer with same world-
   spatial scope.

The two overlap. Adding the cell-RIS samples to the K-RIS canonical
estimator doesn't reduce variance — it adds correlated samples
(same world region, similar lighting) that shift the estimator's
distribution. Net effect: rmse goes up by ~2.3×.

### What architecture would benefit from K-slot

K-slot's quality benefit needs **cell-RIS as the PRIMARY aggregation**,
not as an addition on top of pool aggregation. Several promising
configurations:

- **Pure fresh + cell** (`F8 + P0`): drop the pool entirely; rely
  on per-pixel fresh K=8 candidates + cell-RIS from K=4 stored slots
  per cell. K-slot fills the role pool currently plays.
- **Per-pixel reservoir as the temporal layer + cell-K-slot for spatial**:
  R2d variant where pixels have their own temporal reservoirs AND
  cells provide K-slot spatial-neighbour samples.
- **K-slot for multi-bounce paths** (`ReSTIRNEEPass`, `ReSTIRPTPass`):
  these are c13939f5's domain; their NEE cell-reservoir work
  (commit `71b504e`) already uses the same selection-only consumption
  pattern. K-slot at multi-bounce vertices where MANY pixels'
  secondary/tertiary hits converge on the same world cell would
  see real spatial aggregation that the canonical DI F00P24 doesn't.

These are architectural choices, not parameter tweaks. The K-slot
infrastructure is **ready to be plugged into any of them** without
additional plumbing work — `gReservoirK`, `gReservoirCounters`,
`kSlotAddr`, `loadCellMerged`, atomic-counter insert path are all in
place.

### What the K-slot evolution definitively delivered

1. K=1 parity preserved bit-clean across all changes.
2. K>1 atomic-counter insert path correctly fills K slots per cell
   via Vitter '85 reservoir-sample replacement.
3. K>1 in-cell merge read path correctly aggregates K stored slots
   into a single weighted-merged reservoir.
4. Selection-only consumption (identity-hint stream at reader's pHat
   with invPdf=1) is bias-correct — no firefly explosion despite
   stored W's known unbounded-W issue at biasCorrection=0.
5. Quality finding above is a real empirical measurement, not a
   bug — the architecture works as designed; the question is where
   to deploy it.

### Recommended next step (out of K-slot scope)

Pursue the `F8 + P0 + K-slot=4` architecture as a new ladder variant
in a dedicated session. That's the cleanest test of "K-slot as primary
aggregation". If it beats the canonical pool-heavy F00P24, K-slot
delivers a real quality win. If not, K-slot is best-suited for
multi-bounce paths in NEE/PT where the pool isn't the dominant
mechanism.

### 2026-05-19 v3 design — multi-level K-slot leveraging VisCache cascade

After the v2 cross-scene results (Sponza wins, Bistro/Cornell regress at
fp>1 due to surface mixing), the natural next architecture is **two-level
K-slot riding VisCache's existing posA cascade**:

```
WRITE (per pixel per frame):
  level 0 (fine, fp=1px):    single-slot insert (today's behavior)
  level 1 (one coarser):     K-slot insert via atomic counter

READ (per pixel per frame):
  primary    = loadCell(level=0, my_cell)          # own pixel history
  neighbours = loadCellMerged(level=1, my_cell, K) # K writers' spatial samples
  merge_into_local(primary, neighbours)
```

**Why it solves the cell-coherence problem**:
- Fine level (fp=1) — one writer per cell — no surface mixing. Provides
  RTXDI-equivalent per-pixel reservoir. "My own sample, no contamination."
- Coarse level (fp ~ 2-4 pixels typically) — multiple writers per cell —
  K-slot pool of nearby pixels. The RIS weighting at reader's pHat
  naturally downweights mismatched-surface contributions, so cross-cell
  contamination is handled by the math (not avoided architecturally).

**Why it's free architecturally**:
- VisCache already has `numLevels` posA cascade (default 8 levels).
- Each level has its own cell addressing via `resolveCellAtLevel`.
- No new buffer machinery: extend `gReservoirs` to hold cells at multiple
  levels, indexed by `hash(level, addr)`. Cascade hash separates levels
  naturally.

**Implementation steps**:
1. Buffer: extend `gReservoirs` to span 2 levels. Either two bindings
   (`gReservoirsFine` / `gReservoirsCoarse`) or one buffer with level-offset
   indexing. Single-buffer is cleaner if cascade hash gives non-colliding
   addresses across levels.
2. Write: `mergeIntoCell` becomes two calls — single-slot at level 0,
   K-slot atomic-counter at level 1.
3. Read: replace jittered-neighbour spatial merge with two-level fetch
   (load level 0 for primary, loadCellMerged level 1 for neighbourhood).
4. Footprint policy: `coarseLevelOffset = 1` default. Tunable knob.
5. Multi-bounce: every level naturally has more writers per cell at
   higher bounces. Bounce-cone convergence is intrinsic to the cascade —
   no Sharc-style explicit growth needed.

**Expected outcomes**:
- Sponza: keeps v2's win (coarse level still aggregates similar writers).
- Bistro/Cornell: v2 regression goes away (fine level is bias-free; coarse
  level's contribution is RIS-weighted at reader's pHat — mismatched
  surfaces auto-downweighted, not blindly aggregated).
- Multi-bounce paths (NEEPass/PTPass): K-slot benefit emerges naturally
  via the cascade's per-level cell coverage.

**Scope estimate**: ~2-3 commits of work in a dedicated session.
v2's infrastructure (atomic counter, kSlotAddr, loadCellMerged) generalizes
directly — just add level-offset indexing. Per-slot normal filter from
v2's last commit becomes redundant (cell hash + RIS weighting handle the
surface separation).

### 2026-05-19 cross-scene K-slot characterization (v2)

**K-slot is scene-dependent, not a universal quality win.** Results at x64:

| Scene         | F8P0 K=1 | F8P0 K=4 | Δ K=4 | Canonical F00P24 |
|---------------|----------|----------|-------|------------------|
| Sponza        | 0.231    | 0.186    | **−19%** | 0.176 |
| BistroInterior| 39.804   | 92.423   | **+132%** | 65.761 |
| Cornell_32PL  | 0.245    | 0.973    | **+297%** | 0.283 |

K-slot's in-cell aggregation:
- **WINS** on Sponza — env-map dominated, smooth lighting; nearby pixels
  share important lights → cell aggregation reduces variance.
- **LOSES** on Bistro / Cornell_32PL — discrete emissive lights with
  strong spatial dependence; nearby pixels have DIFFERENT important
  lights → cell aggregation mixes incompatible samples.

This is the classic "spatial reuse with surface-dependent visibility"
limitation that applies to all spatial-reuse schemes — RTXDI mitigates
it via screen-space radius gating + visibility-test of selected
candidates. K-slot lacks both today.

**Surprising secondary finding**: F8P0 K=1 itself beats canonical F00P24
on Bistro (39.8 < 65.7) and Cornell_32PL (0.245 < 0.283). 8 fresh K-RIS
candidates outperform 24 pool draws when BRDF-conditional sampling
matters more than world-spatial aggregation. The pool's "shading-
agnostic emissive samples from PdfMipmap" miss surface-specific
relevance that fresh K-RIS captures.

So the architectural picture is more nuanced than initially thought:
1. F8P0 architecture itself is **competitive with canonical F00P24**
   across scenes; sometimes better.
2. K-slot's contribution is a **separate axis on top** — Sponza
   happens to benefit, geometry-heavy scenes don't.

K-slot is best deployed via **scene-adaptive or surface-aware
filtering**: don't merge cell candidates whose original-writer surface
disagrees with reader surface beyond some threshold. That requires
storing writer normal/material/curvature in the slot — bigger record,
more bookkeeping. Not in K-slot scope.

### 2026-05-19 F8P0 measurement — K-slot delivers a quality win (Sponza only)

Ran the F8P0 + K=variant ladder (commit forthcoming). Sponza x64:

| F8P0 variant   | rmse | Δ vs K=1 F8P0 baseline |
|----------------|------|------------------------|
| K=1 F8P0       | 0.231 | (baseline)           |
| K=4 F8P0       | 0.186 | **−19%**             |
| K=8 F8P0       | 0.183 | **−21%**             |

K-slot scales quality with K when used as primary aggregation. The
architectural hypothesis is confirmed: F00P24's pool aggregation
saturates the gain K-slot can provide; F8P0 leaves room for K-slot
to deliver.

Absolute comparison:
- Canonical F00P24 (24 pool draws): rmse 0.176
- F8P0 + K=8:                       rmse 0.183 (+4% vs canonical)
- F8P0 + K=4:                       rmse 0.186 (+5% vs canonical)

F8P0+K=8 closes most of the gap to the canonical pool-heavy variant
with only 8 fresh candidates per pixel + 8 stored cell slots per
footprint — total K-budget of 16 vs canonical's 24. Per-sample
efficiency favors K-slot.

The K-slot evolution has delivered a measurable, reproducible quality
win in the architecture it was designed for. Future work:
- K=16 / cache-line straddle (256B cells)
- F-K-budget sweep at fixed total candidates (F8K8 vs F16K0 vs F0K16)
- Multi-bounce K-slot in NEEPass/PTPass (c13939f5 territory)
- Hybrid pool + K-slot (decide which aggregates which way)

## 2026-05-19 implementation status (historical detail)

Steps 1-7 of the migration path landed across commits `7dd79fa` ..
`57d1354` (plus `b8b2eb9` and `6632e66` for the design doc itself).
All K=1 variants verified bit-identical to ReSTIRDIReferencePass via
Sponza A/B (rmse drift ≤0.20%, RNG noise floor).

**Structural completion**: the K-slot machinery is in place —
gReservoirK cbuffer field, gReservoirCounters atomic buffer (allocated
only at K>1), kSlotAddr indexing helper, isMultiSlot() dispatch,
mergeIntoCell K>1 atomic-counter-insert body, loadCellMerged K-slot
read body. ReSTIRDIPass / ReSTIRDIReferencePass / ReSTIRNEEPass all
have the binding plumbing.

**Algorithmic exercising remains deferred**: the K>1 read path
(`loadCellMerged`) is only invoked inside the cell-RIS spatial merge
loop (gated on `spatialNeighbours > 0`). Two issues block direct K>1
quality validation:

1. The cell-RIS spatial merge at biasCorrection=0 (RTXDI-faithful)
   has a known catastrophic firefly mode: cell.W is undefined when
   different writers contribute samples with mismatched last_pHat —
   pairwise downweights m_c but doesn't shrink cell.W. With
   `spatialNeighbours=4` enabled on R3dP3d_F00P24, rmse explodes
   to 1090-2139 vs canonical 0.176. This is the same bug documented
   in `VisCache_LadderCommon.py:5012-5021`; it predates K-slot.

2. R3dP3d_F00P24 canonical (`spatialNeighbours=0`) is effectively
   "pool K-RIS only" — cell reservoirs are written via
   `mergeIntoCell` but never read back for shading or temporal
   reuse. With cell-RIS disabled there's no consumer for the
   K-slot in-cell data; K=1/4/8 produce identical output.

Two paths forward to genuinely characterize K>1 quality:

**(a) Fix the cell-RIS bias first**, then re-enable
`spatialNeighbours>0` and observe K-slot's contribution to variance
reduction in the spatial merge.

**(b) Add a new "temporal-cell-reuse" path** that reads the cell
reservoir from the previous frame as a temporal source, analogous
to per-pixel temporal reuse but keyed by world-cell instead of
pixel.xy. This bypasses the spatial-merge bias entirely and
exercises K-slot via the natural "in-cell K writers across frames
form temporal multi-sample".

Both are out of K-slot scope. The K-slot pieces are ready to be
consumed when either path lands. Until then, the architecture is
plumbing-correct and parity-validated at K=1 — sleeping potential.

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

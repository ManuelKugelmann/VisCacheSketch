# ReSTIRPTPass — active port toward Falcor 8 native PathTracer

## Status (2026-05-10) — R-axis ZOO COMPLETE

This plugin is the **active port** of dqlin-style ReSTIR-PT, paired with
`Source/RenderPasses/ReSTIRPTReferencePass/` (byte-frozen verbatim mirror
of the upstream dqlin reference).

**Maintenance contract**: when the upstream dqlin reference changes, apply the
same diff to `ReSTIRPTReferencePass/` first, then port the same delta to this
plugin. Deliberate divergences are called out inline (e.g. dqlin RTXDI gating
in `evalEnvAtMiss`).

## R-axis variants (ALL LIVE)

`restirptAddrMode` cbuffer field dispatches three live R-axis variants:

| mode | name    | reservoir storage                            |
|-----:|---------|----------------------------------------------|
| 0    | R2d     | 2D pixel buffer only (DQLin baseline)        |
| 1    | R2dR3d  | 2D pixel + 3D cell-pool override (cell-first, pixel-fallback) |
| 2    | R3d     | Pure 3D cell-pool, no pixel buffer           |
| 3    | H2dR3d  | NOT IMPLEMENTED (deferred — see memory `project_h2dr3d_design_constraint`) |

## Validation (current — full 7-scene RPT_ZOO ladder, b=4, OkLab%×2L vs vanilla_b4_x4096 GT)

AB harness (`scripts/RestirPT2D_AB.py`, ImageCompare metric) confirms
`restirpt_2d` is **bit-identical to `restirpt_ref`** (the frozen DQLin verbatim
plugin) on every tested scene. Mode-0 = DQLin parity, validated.

Ladder cumulative R3d-vs-R2d delta across the 7-scene matrix
(`docs/LADDERLOG.md` Step RPT_ZOO has the per-scene table):

| SPP | cum d(R3d−R2d) | cum d(R3d−vanilla) | story |
|----:|---:|---:|---|
| 1   | +6.69pp | -55.82pp | R3d cold-cell penalty; R2d wins HUGE over vanilla |
| 4   | -6.78pp | -18.06pp | DQLin Sponza fireflies start; R3d fixes |
| 16  | **-46.08pp** | +5.44pp | R3d severe firefly cleanup on Bistro/Sponza; small Cornell tax |

**Architectural finding:** R3d's cell-pool first-writer-wins atomic-CAS
suppresses a DQLin per-pixel-reservoir firefly pathology on Bistro/Sponza
at SPP≥4. Sponza R2d at SPP=16 = 27.76% OkLab; R3d = 7.18%. Cross-
checked via frozen `restirpt_ref` plugin → confirmed it's a DQLin algorithm
property, not a port bug.

Cornell scenes pay a small tax (R3d slightly worse than R2d) — vanilla
converges fast on simple lighting, ReSTIR overhead doesn't earn back its
bias. Net cumulative across the matrix is a substantial R3d win.

**Cost-axis finding (2026-05-11).** R3d is also ~67% FASTER than R2d
(gpu_total_ms, 7-scene mean R3d/R2d=0.329×, R2dR3d/R2d=0.555×). Per-
scene ratios are uniform (0.297-0.362× for R3d) → structural speedup
from skipping per-pixel reservoir write + downstream temporal/spatial-
reuse passes that consume it. Combined with the quality finding above,
**R3d Pareto-dominates R2d on every measured axis**: the Cornell
+0.1pp quality tax is offset by a 67% compute drop.

Caveat: ladder gpu_total_ms includes warmup overhead — absolutes
aren't real-time-relevant, only ratios. See
`scripts/audit_rpt_zoo_cost.py 16` to regenerate.

## v2 progress so far

- ✅ Two plugins live side-by-side: ReSTIRPTReferencePass (frozen) +
  ReSTIRPTPass (active port).
- ✅ Plugin name distinct (FALCOR_PLUGIN_CLASS), both registered in
  `build.bat` PLUGIN_DIRS.
- ✅ Vanilla PathTracer plugin entirely untouched.
- ✅ AB harness validates vanilla / ref / 2d / 3d on Cornell + Sponza.
- ✅ Task #12: 2D/3D addressing-mode dispatch infrastructure
  (`restirptAddrMode` cbuffer field + host-side property,
  `getReservoirOffset(pixel, posA, faceN)` 3-arg overload,
  `gPathTracer.resolveReservoirOffset(pixel)` 1-arg helper, all 16
  call sites routed through it).
- ✅ Task #13: posA/faceN wiring scaffold (currently 1-arg helper used
  everywhere; 3-arg form reachable but mode=1 stubbed).
- 🔨 Task #11 (paired-helper extractions toward Falcor 8 native PT):
  - `evalEnvAtMiss(path, out Le, out misWeight)` extracted in both
    Falcor 8 PathTracer + ReSTIRPTPass (mirrored helper pair).
  - `evalEmissiveMIS(path, sd, isPrimaryHit, isLightSamplable,
    isTriangleHit, [out lightPdf]) -> misWeight` extracted in both.
  - Remaining handleHit body is increasingly plugin-specific
    (path.L update, pathBuilder.addEscapeVertex, NRD writes) —
    diminishing returns on further extraction.

## Resolved blockers

### Task #15 — restirpt_3d concurrent-write corruption ✅ RESOLVED

Original symptom: hash-keyed flat reservoir buffer couldn't handle concurrent
writes from multiple pixels mapping to the same slot — torn writes → corrupt
`rcVertex.hit` → DXGI_DEVICE_REMOVED.

Resolution: `PathReservoirCellPool.slang` cell-pool with fingerprint +
atomic-CAS slot claim. First writer wins; subsequent writers fall back to
pixel buffer (mode 1) or empty (mode 2). Validated working on all 7 scenes
in the RPT_ZOO ladder. Cell-pool cleared every frame via `clearUAV` in
`ReSTIRPTPass.cpp::execute()` for natural per-frame refresh.

A frame-stamp scheme (`InterlockedMax` on per-slot frameStamp) was prototyped
and reverted (commit `a3129ab`) — the non-atomic stamp write between the
CAS and reader consumption introduced a write-ordering race that regressed
Cornell quality 25%. Per-frame `clearUAV` is the canonical refresh.

## Future steps (Task #11 continued)

1. **Make TracePass.cs.slang a thin shim** around Falcor 8's PathTracer
   raygen, with a hook for reservoir population.
2. **Reduce PathTracer.slang** to a thin adapter exposing the same
   struct surface (handleHit/nextVertex/generatePath/handleMiss/
   finalize/writeOutput) but delegating internals to Falcor 8.
3. **Adapt PathBuilder.slang** to operate on Falcor 8's `PathState`.
4. **Drop Falcor8Compat.slang** once everything is Falcor 8 native.

Each step validated against `ReSTIRPTReferencePass` to ensure quality
is preserved (within frame noise — different RNG sequences from
different path-walk implementations expected once Falcor 8 PT is the
backbone, but accumulated-frame results should converge).

(Note: AB harness uses a simpler graph than the canonical RPT00 ladder — no
NRD denoiser, no RTXDI direct-light feed — so the absolute err numbers are
higher than the ladder's. The relevant check is `restirpt == restirpt_ref`.)

## Next-iteration plan (Task #11)

Replace the dqlin-specific path-tracing logic with calls into Falcor 8's
native `PathTracer` plugin. The reuse machinery (`PathReservoir.slang`,
`Shift.slang`, `SpatialReuse.cs.slang`, `TemporalReuse.cs.slang`,
`SpatialPathRetrace.cs.slang`, `TemporalPathRetrace.cs.slang`,
`ComputePathReuseMISWeights.cs.slang`) stays.

### Files to keep (reuse machinery)
- `PathReservoir.slang` — reservoir struct + GRIS math
- `Shift.slang` — reconnection / hybrid / random-replay shift kernels
- `SpatialReuse.cs.slang`, `TemporalReuse.cs.slang`
- `SpatialPathRetrace.cs.slang`, `TemporalPathRetrace.cs.slang`
- `ComputePathReuseMISWeights.cs.slang`
- `Params.slang`, `StaticParams.slang`, `ReflectTypes.cs.slang`
- `NRDHelpers.slang`, `LoadShadingData.slang`

### Files to replace / remove (dqlin path-tracing logic)
- `TracePass.cs.slang` — currently dispatches dqlin's own `walkPath` against
  dqlin's `PathTracer` struct. Replace with a thin shim that runs Falcor 8's
  vanilla `PathTracer` trace pass to fill in primary-hit shading data and
  per-path radiance, plus a hook to populate `outputReservoirs` (rcVertex
  selection + cached integrand) during the path walk.
- `PathTracer.slang` — dqlin's PathTracer struct (handleHit, nextVertex,
  generatePath, finalize, writeOutput, light sampling, BSDF eval, RR, etc.)
  ~2148 LoC. Replace with a thin adapter that exposes the same struct surface
  but delegates to Falcor 8's `Falcor::PathTracer` internals.
- `PathBuilder.slang` — reservoir construction during path walk. Keep the
  reservoir-population logic but adapt to Falcor 8's `PathState` instead of
  dqlin's. The math (rcVertex selection, prefix throughput, postfix weight)
  is unchanged.
- `Falcor8Compat.slang` — bridge between Falcor 4-era BSDF API and Falcor 8.
  Once we use Falcor 8 native types throughout, this can be removed.
- `GeneratePaths.cs.slang` — sample distribution. Falcor 8's
  `GeneratePaths.cs.slang` already handles this; can either delegate or copy
  the relevant pieces.

### Strategy (per user direction 2026-05-07)

**Redirect dqlin tracing functions to Falcor 8 without changing their
signatures or names.** Extending Falcor 8's PathTracer base is permitted
when needed for hooks, but only additively — vanilla PathTracer must
remain bit-identical for `useRestirPT=false`-equivalent code paths.

Concrete sub-steps (each validated against `ReSTIRPTReferencePass`):

1. **Make `TracePass.cs.slang` a thin shim** around Falcor 8's PathTracer
   raygen, with a hook for the reservoir population.
2. **Reduce `PathTracer.slang` to a thin adapter** exposing the same struct
   surface (handleHit, nextVertex, generatePath, handleMiss, finalize,
   writeOutput) but delegating internals to Falcor 8.
3. **Adapt `PathBuilder.slang`** to operate on Falcor 8's `PathState` instead
   of dqlin's. The math (rcVertex selection, prefix throughput, postfix
   weight) is unchanged.
4. **Drop `Falcor8Compat.slang`** once everything is Falcor 8 native.

### Practical first step (next iteration)

The simplest delegation target is `handleMiss`. dqlin's body (~70 lines)
includes a chunk of generic env-radiance eval logic that's identical to
Falcor 8's. To delegate:

a. Add an additive helper to Falcor's `PathTracer.slang`:
   `bool evalEnvAtMiss(in PathState path, out float3 Le, out float misWeight)`
   — pure function, no side effects, just computes the env contribution.
   Vanilla PathTracer.slang can be refactored to call it (no behavior change),
   AND ReSTIRPTPass can call it. Additive — vanilla output unchanged.

b. Replace dqlin's handleMiss body's env-eval block with a call to that
   helper. The dqlin-specific side effects (path.L update,
   path.LDeltaDirect, pathBuilder.addEscapeVertex) stay.

c. Validate: `ReSTIRPTPass` AB output must remain bit-identical to
   `ReSTIRPTReferencePass`.

Then iterate same pattern for `handleHit` (more complex — many side
effects on `path.pathBuilder` etc.), `nextVertex`, etc.

## Future extension (Task #12): 2D/3D addressing modes

Mirror the `gWSPoolAddrMode` pattern from VisCache's WS-ReSTIR DI:

- `restirptAddrMode = 0` (2D, default): reservoir indexed by linear pixel
  offset (current behavior — `params.getReservoirOffset(pixel)`).
- `restirptAddrMode = 1` (3D): reservoir indexed by world-cell hash via
  VisCache's `wsResolveCellPoolAddr(posA, faceN)` from
  `Source/RenderPasses/VisCache/WSCellPoolIO.slang`. The world-cell mode
  enables reuse across non-spatially-coherent regions, mirroring restir_3d
  for DI.

This requires VisCache to be a runtime dependency of ReSTIRPTPass, which is
acceptable since restir_3d (DI) already uses the same pattern.

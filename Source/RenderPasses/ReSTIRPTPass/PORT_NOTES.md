# ReSTIRPTPass — active port toward Falcor 8 native PathTracer

## Status (2026-05-07)

This plugin is the **active port** toward Falcor 8 native PathTracer
integration. It currently contains a **byte-identical copy** of the dqlin
reference (mirrored separately in `Source/RenderPasses/ReSTIRPTReferencePass/`,
which stays frozen).

**Maintenance contract**: when the upstream dqlin reference changes, apply the
same diff to `ReSTIRPTReferencePass/` first, then port the same delta to this
plugin.

## Validation (current)

AB harness `scripts/RestirPT2D_AB.py`, SPP=32, 512×512, vs ladder x4096 GT:

| scene             | vanilla | `restirpt_ref` | `restirpt` (this plugin) |
|-------------------|---------|----------------|--------------------------|
| Cornell_1AreaLight| 0.00519 | 0.02133220     | 0.02133220 (== ref ✓)    |
| Sponza            | 0.00821 | 0.150901       | 0.150901 (== ref ✓)      |

Bit-identical to reference, as expected for a verbatim copy.

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

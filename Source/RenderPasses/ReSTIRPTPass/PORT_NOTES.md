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

### Strategy

1. **Preserve reuse-pass interfaces.** The existing
   `outputReservoirs[params.getReservoirOffset(pixel)]` interface stays —
   what changes is who fills it.
2. **Make `TracePass.cs.slang` a thin shim.** Instead of `gPathTracer.handleHit/...`,
   it dispatches Falcor 8's PathTracer raygen (or copies its logic) and adds
   the rcVertex selection + reservoir-write at the right path-walk hook.
3. **Iterative**: do this in stages, validating against `ReSTIRPTReferencePass`
   after each step. The test is `ReSTIRPTPass` produces output that's *close*
   to `ReSTIRPTReferencePass` (not bit-identical — different RNG sequences from
   different path-walk implementations), within accumulated-frame noise.

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

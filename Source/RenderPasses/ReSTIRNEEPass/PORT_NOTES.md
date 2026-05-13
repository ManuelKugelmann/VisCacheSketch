# ReSTIRNEEPass — scaffold for per-vertex NEE reservoir reuse

## Status (2026-05-13)

**Scaffold only.** Cloned verbatim from working ReSTIRDIPass (Tick 16 of the
ReSTIRDI refactor /loop, after parity was locked). Compiles and registers as
a distinct plugin (`ReSTIRNEEPass.dll`) but is **algorithmically identical
to ReSTIRDIPass** at this point — needs the per-vertex differentiation work
described below.

## Why a separate pass (vs mode flag on ReSTIRDIPass)

Per `project_restir_nee_layer.md` design note (parallel session,
2026-05-13): three peer ReSTIR passes form a single-responsibility ladder.

| Pass | Reservoir element | Path walk? |
|---|---|---|
| ReSTIRDIPass | LightSample at primary hit | No (`maxBounces=0`) |
| **ReSTIRNEEPass (this)** | LightSample at every vertex (keyed pos+normal) | Yes |
| ReSTIRPTPass | Full path / suffix | Yes (with Shift) |

Trying to unify in one pass forces either runtime-selected kernels (~same
cost as two passes), `#if`-cluttered shaders (doubles compile permutations),
or wasted runtime branch divergence. None saves meaningful code.

## What needs to change vs ReSTIRDIPass

Currently this pass is byte-identical to ReSTIRDIPass. The algorithmic
differentiation work TODO:

1. **Reservoir keying.** ReSTIRDIPass uses pixel-indexed reservoir
   (`gWSPixelReservoirs[wsPixelIndex(pixel)]`). ReSTIRNEEPass should use
   world-space-cell-keyed reservoir indexed by `(pos, faceN)` cascade —
   reuses VisCache's posA addressing. This is the "every-vertex" reuse
   target: each NEE site in the path walk consults a reservoir keyed by
   THAT vertex's shading-point position, not the originating pixel.

2. **NEE call-site integration.** PathTracer.slang's NEE block at L1167-
   onwards currently runs the WS-ReSTIR DI K-RIS at `path.getVertexIndex()
   == 1`. ReSTIRNEEPass should run the equivalent reservoir reuse at
   EVERY vertex where NEE fires (all bounces ≤ maxSurfaceBounces).

3. **maxBounces default.** ReSTIRDIPass canonical config is `maxBounces=0`
   (DI-only); ReSTIRNEEPass canonical is `maxBounces ≥ 1` so the path
   walk actually traverses interior vertices.

4. **Per-vertex Bayer / freshness gates.** The cell-pool freshness gate
   currently runs once per pixel per frame in ReSTIRDIPass. For per-vertex
   NEE, the gate needs to either fire at each vertex (expensive) or share
   per-pixel state (cheaper but biases against deep-vertex variance
   reduction). Open design question — see project_restir_nee_layer for
   alternatives.

## Maintenance contract (until algorithmic work lands)

- This plugin is a **scaffold** — exact duplicate of ReSTIRDIPass with
  renamed C++ class only. Building/loading verifies the plumbing.
- Do NOT add it to any active ladder runner — the parity with
  ReSTIRDIPass is trivial (they ARE the same algorithm right now).
- When the algorithmic work above lands, this PORT_NOTES gets the per-step
  validation table. Until then, this pass is unwired.

## File-level inheritance from ReSTIRDIPass

Same slang surface as ReSTIRDIPass (verbatim PathTracer fork): PathTracer.slang,
TracePass.rt.slang, PathState.slang, Params.slang, StaticParams.slang,
ColorType.slang, GuideData.slang, NRDHelpers.slang, PathTracerNRD.slang,
LoadShadingData.slang, GeneratePaths.cs.slang, ReflectTypes.cs.slang,
ResolvePass.cs.slang. C++ class renamed `ReSTIRDIPass` → `ReSTIRNEEPass`
throughout; plugin name string `"ReSTIRNEEPass"`.

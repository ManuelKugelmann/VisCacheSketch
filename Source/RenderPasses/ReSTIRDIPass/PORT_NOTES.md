# ReSTIRDIPass — port notes

## Goal

Move primary-hit ReSTIR DI out of `Falcor/Source/RenderPasses/PathTracer/PathTracer.slang`
into a standalone plugin that is a **peer to RTXDIPass and PathTracer**, not a
consumer of either.

## Architectural shape (user-confirmed)

- ReSTIRDIPass is a standalone radiance producer with its own raygen
- Imports Falcor library directly: `Scene.*`, `Rendering.Materials.*`,
  `Rendering.Lights.*`, `Utils.Sampling.*` — same imports any standalone raygen
  needs. **Does NOT import `RenderPasses.PathTracer.PathTracer`.**
- Imports `RenderPasses.VisCache.*` for the optional cache-amortized V-test
  utility (just like PathTracer does — VisCache is a shared utility plugin)
- Render graph picks ONE of {PathTracer, RTXDIPass, ReSTIRDIPass} at
  `maxBounces=0`. Mirrors how RTXDI replaces PathTracer in RTXDI-mode graphs

## Net delta against the two goals

**Goal 1 — minimize PathTracer modifications:**
- PathTracer net delta is **negative**: removing ~1000 lines (the WS-ReSTIR DI
  body) without adding any new lines. Becomes near-vanilla Falcor.
- The only PathTracer extension retained is the existing optional VisCache
  hook (`USE_VISCACHE_VISIBILITYCHECK` + `vcVisibility_Ray` wrapper at NEE
  shadow rays). That's a generic utility, not a ReSTIRDIPass dependency.

**Goal 2 — minimize duplication:**
- ReSTIRDIPass.slang does NOT copy PathTracer.slang code. The lifted body
  uses Falcor library calls directly (`sampleEmissiveLight`, `mi.eval`,
  `evalMIS`, `SceneRayQuery<>::traceVisibilityRay`, etc.) — same library
  calls PathTracer uses, but no shared shader module
- Reservoir types stay in VisCache for v1 (shared utility). Phase 6 renames
  + moves them into ReSTIRDIPass

## Source map: what lifts where

PathTracer.slang ranges to lift (~750 LOC):

| Range | What | Target file |
|---|---|---|
| L50–L60 imports | `Reservoir`, `ReservoirIO`, `CellPool`, `CellPoolIO`, `VisCache`, `Utils.Math.MathHelpers` | `TracePass.rt.slang` imports |
| L650–L797 | `packLightSamplePayload`, `rebuildEnvMapLightSample`, `rebuildAnalyticLightSample`, `rebuildEmissiveLightSample` | `TracePass.rt.slang` (or factor into `Reservoir.slang` helpers) |
| L1206–L1974 | Primary-hit NEE block: K-RIS, V-aware K-RIS fill, temporal reuse, spatial reuse, retrace-on-reuse, reservoir writeback | `TracePass.rt.slang` raygen body |
| L2010–L2019 | Boiling-filter no-op cleanup at miss | `TracePass.rt.slang` |
| 4× `vcDiagCountRay(..., REVAL)` sites | Reuse-revalidation diag bumps | `TracePass.rt.slang` (now owns its own ReSTIRDIPass diag UAVs) |

PathTracer.h state to lift:
- `mpVHFWS*` host members (reservoir buffer + frame dims + cell pool aliases)
- `mp*Reservoirs` allocations
- Per-frame reset bookkeeping

PathTracer.cpp state to lift:
- All `gWS*` cbuffer per-field bindings (~12 fields)
- All `mpVHFWS*` allocation + setVars wiring
- Cross-pass dict reads for WS reservoir state

## Replacements for PathTracer-specific couplings

The lifted body currently uses:
- `path.sg` → standalone `SampleGenerator sg = SampleGenerator(pixel, params.seed * spp + sampleIdx);` setup at raygen entry, same as RTXDIPass
- `path.getPixel()` → `uint2 pixel = DispatchRaysIndex().xy;` (RT pass) or thread ID (CS pass)
- `path.getSampleIdx()` → loop index in N-SPP outer loop
- `path.getVertexIndex() <= 1` check (bounce-0 only) → drop, ReSTIRDIPass IS bounce-0 only
- `sd.frame.N` (shading frame normal) → loaded once per pixel from `loadShadingData(pixel, vbuffer)`
- `mi.eval(sd, dir)` → `IMaterialInstance mi = gScene.materials.getMaterialInstance(sd, lod);` then `mi.eval(...)`
- `vq.traceVisibilityRayCV(...)` → if `USE_VISCACHE_VISIBILITYCHECK`: `vcVisibility_Ray(...)` from `VisCache.VisCachePathTracer`; else: `SceneRayQuery<UseAlphaTest>::traceVisibilityRay(...)`

## Phases of the port

Phase 2a (DONE on this commit): scaffolding only — Params.slang, Reservoir.slang re-export, stub TracePass.rt.slang. Build verifies plugin still loads.

Phase 2b: lift the raygen body from PathTracer.slang. Build verifies the new pass produces output. ReSTIRDIPass.cpp setShaderData modeled on RTXDIPass.cpp.

Phase 3: remove the lifted blocks from PathTracer.slang + corresponding cbuffer fields/host members. PathTracer goes back to near-vanilla.

Phase 4: render-graph wiring in `scripts/PathTracer_Graph.py` and prop routing in `scripts/VisCache_LadderCommon.py::_run_baseline_restir`.

Phase 5: parity validation against pre-refactor `runtime/captures/ladder/RDI00/stats.csv`. Tolerance: <0.05pp err delta per scene.

Phase 6: rename `Reservoir.slang` → `Reservoir.slang` (move from VisCache → ReSTIRDIPass), drop `WS` prefix from identifiers consistently. Update all importers.

## Maintenance contract after port

- Upstream Falcor PathTracer changes apply ~directly (near-zero merge conflicts on `Falcor/Source/RenderPasses/PathTracer/`)
- ReSTIRDIPass + RTXDIPass + ReSTIRPTPass all migrate Falcor library API changes in parallel, sharing none of their state
- VisCache stays the only cross-plugin utility, imported by anyone who wants visibility caching

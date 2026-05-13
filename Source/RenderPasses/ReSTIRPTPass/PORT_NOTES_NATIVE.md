# Design note: finish the port to Falcor 8's native PathTracer surface

## Status (2026-05-13)

**ON HOLD — waiting on two upstream prerequisites:**

1. **Parallel agent's PathTracer plugin cleanup.** Don't touch any
   `Falcor/Source/RenderPasses/PathTracer/` files until their cleanup
   commits land.
2. **ReSTIR DI being split into its own render pass.** Per user
   2026-05-13: "restirDI moves into a separate pass." Once that lands,
   `Falcor/.../PathTracer/PathTracer.slang` sheds the WS-ReSTIR DI
   integration (`USE_WS_RESERVOIRS` block, WS-ReSTIR imports, K-RIS,
   retrace-on-reuse). The "native PathTracer substrate" ReSTIR-PT
   eventually integrates with will then be the **post-DI-split**
   PathTracer — a much smaller, cleaner surface.

**Scope locked** for when prerequisites land: "port to Falcor's native
PathTracer" = **delete `Falcor8Compat.slang` and have callers use
`IMaterialInstance` directly, the same way Falcor's native PathTracer
does.** Not a path-walk re-integration; not a from-scratch GRIS rewrite.

## Why this is the right scope

Three interpretations of "port to native PathTracer" were considered:

| | strategy | scope | verdict |
|---|---|---|---|
| A | Move ReSTIRPTPass's GRIS into `Falcor/.../PathTracer/` | ~3300 LoC shader + ~700 LoC host; multi-week | v1 attempted (commits `95b8cf4..4564e90`), archived `9bf94c2` — "re-deriving GRIS from first principles is the wrong shape" |
| B | Swap ReSTIRPTPass's path-walk for Falcor's `gPathTracer` methods | architecturally fat — ReSTIRPTPass's compute passes would need to mirror Falcor PathTracer's full `ParameterBlock` (env-map sampler, emissive sampler, NRD buffers, RTXDI hooks, pixel stats) | feasible but disproportionate |
| C | **Drop `Falcor8Compat.slang` shim** | 281 LoC deleted + 33 call sites rewritten across 4 files | bounded, reversible, zero algorithmic change |

C is the operational definition of "port done": the only thing in
`Source/RenderPasses/ReSTIRPTPass/` that *is* a port-compat shim
disappears. Callers use Falcor 8's native API just like Falcor's own
PathTracer plugin does. Algorithm untouched, R-axis wins preserved.

## What `Falcor8Compat.slang` actually is

Pure rename layer over Falcor 8's `IMaterialInstance`. Internals (lines
36-240) already call the native methods:

| DQLin shim | Falcor 8 native |
|---|---|
| `sampleBSDF(sd, sg, result, useIS)` | `mi.sample(sd, sg, bs, useIS)` |
| `evalBSDFCosine(sd, dir)` | `mi.eval(sd, dir, sg)` |
| `evalBSDFCosine(sd, dir, allowedFlags)` | `mi.evalBsdfAndPdf(sd, dir, sg, allowedFlags, _, _)` |
| `evalPdfBSDF(sd, dir)` | `mi.evalPdf(sd, dir, true)` |
| `evalPdfBSDF(sd, dir, out pdfAll, flags)` | `mi.evalBsdfAndPdf(sd, dir, sg, flags, componentPdf, pdfAll)` |
| `classifyAsRough(sd, t)` | `mi.getProperties(sd).roughness > t` |
| `hasRoughComponent(sd, t)` | inline check on `mi.getProperties(sd).roughness` + `mi.getLobeTypes(sd)` |
| `getRoughness(sd)` | `mi.getProperties(sd).roughness` |
| `getEmission(sd)` | `mi.getProperties(sd).emission` |
| `BSDFSample_` struct | `BSDFSample` (no trailing underscore) |

### The one non-trivial member: `BSDFSample_::pdfSingle`

`BSDFSample_` adds a `pdfSingle` field that Falcor 8's `BSDFSample`
doesn't have: it's the per-lobe-class partial PDF used by Shift.slang's
Jacobian math when `kSeparatePathBSDF == 1`. The shim populates it
eagerly with a second `mi.evalBsdfAndPdf` call inside `sampleBSDF`
(lines 60-68).

**Native-form plan:** drop `pdfSingle` from the struct. Call sites that
need it (only in `Shift.slang`, where `kSeparatePathBSDF` is consulted)
compute it on demand via `mi.evalBsdfAndPdf` post-sample. Saves the
eager-eval cost on call sites that don't need it.

### `Camera::computeRayPinholePrevFrame`

Lines 246-280 are a `Camera` extension method reconstructing the
previous-frame ray from `prevViewMat`. **Not** a DQLin compat shim —
it's a missing Falcor 8 primitive. **Keep**, move into a new
`PrevFrameCameraRay.slang` sibling so it survives the
`Falcor8Compat.slang` deletion.

## Call-site inventory

Total: **33 occurrences across 4 files** (per `grep` of
`BSDFSample_|sampleBSDF\(|evalBSDF\(|evalPdfBSDF\(`):

| File | hits | nature |
|---|---:|---|
| `Falcor8Compat.slang` | 16 | self (defines the shims) — removed wholesale |
| `Shift.slang` | 9 | dense GRIS use; needs `pdfSingle` careful handling |
| `PathTracer.slang` | 7 | path-walk primary BSDF calls |
| `PathBuilder.slang` | 1 | single BSDF sample at retrace entry |

## Migration plan (incremental)

Each chunk = one logical commit, build-clean + smoke-pass before moving
on. The R-axis variants (R2d, R3d) must stay bit-identical through every
intermediate step — the AB harness on Cornell_1AL at SPP=4 is the
trip-wire.

1. **Chunk 1 — `PathBuilder.slang` (1 site).** Smallest call-site count;
   prove the migration pattern works. Replace `sampleBSDF(...)` with
   `IMaterialInstance` direct call inline. If `pdfSingle` needed, add
   the second `evalBsdfAndPdf` post-sample call locally.

2. **Chunk 2 — `PathTracer.slang` (7 sites).** Path-walk BSDF calls.
   Mostly `sampleBSDF` for scatter rays + `evalBSDFCosine` for NEE
   shading. Lower density than Shift; clean targets.

3. **Chunk 3 — `Shift.slang` (9 sites).** The trickiest pass — many
   `pdfSingle` uses. Likely produces a small Jacobian eval change in
   the BSDF path that requires AB validation at full SPP sweep.

4. **Chunk 4 — `TemporalReuse.cs.slang` + `TemporalPathRetrace.cs.slang`.**
   Last consumers; remove `import Falcor8Compat;` lines.

5. **Chunk 5 — move `Camera::computeRayPinholePrevFrame` extension** to
   a sibling `PrevFrameCameraRay.slang`, update imports.

6. **Chunk 6 — delete `Falcor8Compat.slang`**, drop from CMake. Run
   full RPT_ZOO ladder to verify R-axis variants unchanged on the
   full 7-scene matrix.

## What this doesn't do

- Doesn't move GRIS into `Falcor/.../PathTracer/`. That's the v1
  archived strategy; the R-axis wins live inside ReSTIRPTPass and stay
  there.
- Doesn't introduce new shaders or new dispatch passes.
- Doesn't touch the cell-pool / frame-CAS substrate.

## Validation gates

Each chunk:
- `build.bat --skip-setup` clean
- `.scripts/smoke.sh` passes
- AB harness: `RestirPT2D_AB.py` on Cornell_1AL b=4 SPP=4 — delta vs
  pre-chunk capture ≤ 0.001 (noise floor)

After Chunk 6:
- Full RPT_ZOO ladder on the 4-Cornell + Sponza + Bistro matrix
- R3d cumulative err delta vs current main: ≤ 0.1pp on every scene
- No regressions in BistroExt TDR stability (still passes x16+x32)

## Architectural recontext (2026-05-13): ReSTIR DI split

User decision 2026-05-13: ReSTIR DI moves into its own render pass,
separate from Falcor's PathTracer plugin. Implications:

- `Falcor/.../PathTracer/PathTracer.slang` returns to a clean
  path-tracing-only substrate. The `USE_WS_RESERVOIRS`,
  `USE_VISCACHE_LIGHTSELECTION`, K-RIS, retrace-on-reuse blocks all
  move to the new DI pass.
- `VisCacheParams` cbuffer and `gCellPool*` bindings move with the
  DI pass.
- This makes the "port to native PathTracer" target *cleaner over
  time*, not harder. Wait for the split to settle before doing the
  Falcor8Compat removal — the imports/dependencies in
  `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang` will likely
  shed a few `import RenderPasses.VisCache.*` lines that currently
  exist for shared WS-ReSTIR plumbing.
- The Falcor8Compat removal plan itself is **local to ReSTIRPTPass**
  and not affected by either the parallel-agent PathTracer cleanup or
  the DI split. It can run as soon as the parallel agent's cleanup
  settles and our R-axis variants are validated against the post-
  cleanup state.

## Out of scope

- P-axis NEE pool real RIS-at-insert (Task #21)
- Bayer-staged TracePass subframes (Task #22)
- v2's "RestirPTPass2D separate plugin" strategy — superseded by this
  smaller scope.
- ReSTIR DI pass extraction itself — out of this task's scope; that's a
  separate refactor that this port note merely waits on.

Source: `Source/RenderPasses/ReSTIRPTPass/Falcor8Compat.slang` + callers.

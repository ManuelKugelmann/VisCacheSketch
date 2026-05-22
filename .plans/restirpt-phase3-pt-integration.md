# Phase 3 — ReSTIRPTPass full PathTracer(X) integration

**Active goal as of 2026-05-22 evening**, per user directive: archive current
ReSTIRPT, work toward delegating tracing internals to PathTracerX.

Archive tag: `restirpt-pre-pt-nudge-2026-05-22` (commit 2aa43ed9).

## Why

ReSTIRPTPass's `PathTracer.slang` is 2344 lines of dqlin's 2022 ReSTIR-PT
research code (Lin et al.). Vanilla Falcor 8 PathTracer = 1203 lines.
PathTracerX (our fork with VC hooks) = 1268 lines. Three nearly-parallel
PathTracer struct surfaces but bespoke math woven through dqlin's.

The drift is real: dqlin and Falcor 8 share BSDF sampling, RR, MIS code
but call slightly different helpers; bugs found in Falcor 8 (e.g. recent
analytic-light gap) don't auto-propagate. Maintenance compounds.

## Strategy (user-directed 2026-05-07, restated 2026-05-22)

**Redirect dqlin tracing functions to PathTracerX (or Falcor 8 native) without
changing their signatures or names.** Extending PathTracerX is permitted when
needed for hooks, but only additively — vanilla PathTracer must remain
bit-identical for the `useRestirPT=false`-equivalent path.

Each step validated against `Source/RenderPasses/ReSTIRPTReferencePass/`
(byte-frozen dqlin verbatim mirror). Quality must hold within frame noise
on the 7-scene AB harness (`scripts/RestirPT2D_AB.py`).

## Step list (fine-grained, one per /loop iteration where possible)

### Step 3.0 — Prerequisite: shared `evalMIS` via int-arg API
Currently `MISHeuristic` enum is duplicated 5 times (ReSTIRPTPass,
PathTracerX, ReSTIRDIPass, ReSTIRDIReferencePass, ReSTIRNEEPass
Params.slang lines ~47-53). All bodies identical: Balance=0,
PowerTwo=1, PowerExp=2. Moving the enum itself is awkward because
Params.slang is host-shared (C++ reads enum values via `HOST_CODE`
ifdef), and PathTraceCore.slang is shader-only.

**Approach**: extract `evalMIS` taking `uint heuristic` instead of the
enum type, so it stays decoupled from any single Params.slang's enum
copy. Implementation:
- Add `float evalMIS(uint heuristic, float n0, float p0, float n1, float p1)`
  to PathTraceCore.slang.
- Replace 2 call sites at ReSTIRPTPass + PathTracerX with
  `evalMIS(uint(kMISHeuristic), ...)`.
- Validate: PT smoke + AB-vs-Reference parity (same bit pattern since
  enum→int cast preserves value).

This is the proof-of-concept extraction. Bigger helpers (russianRoulette,
sampleBSDF) follow the same pattern in step 3.1.

### Step 3.1 — Helper-extract findings (post-3.0)

After Step 3.0 succeeded with `evalMIS`, surveyed remaining candidates:

| helper | dqlin | PathTracerX | extract candidate |
|---|---|---|---|
| `evalMIS` | static, struct-local | non-static, struct-local | ✅ DONE (3.0) — `evalMISImpl(uint heuristic, ...)` |
| RR (russianRoulette) | `terminatePathByRussianRoulette` method | inlined pattern | ❌ structurally different — defer |
| `russianRoulettePdf` accumulator | `path.russianRoulettePdf` field | same field | already in shared PathState (no extraction needed) |
| `getCoherenceHints` | not present | struct method | PathTracerX-only, no shared opportunity |
| `updatePathThroughput`, `addToPathContribution` | PathState-style on dqlin's PathState | PathTracerX-style | adapter Step 3.2 territory |
| `generateScatterRay` | dqlin `sampleScatterRay` | PathTracerX `generateScatterRay` | similar surface, different bodies → Step 3.2 |

Conclusion: **only `evalMIS` is cleanly extractable via the int-arg pattern**. Other shared helpers either (a) live on diverging PathState surfaces (needs Step 3.2 adapter first), or (b) are structurally different enough that extracting forces a behaviour change.

**Implication**: Step 3.1 essentially ends with `evalMIS`. Step 3.2 (PathTracerX as a field of dqlin's PathTracer struct, calling into its scatter/throughput/contribution helpers) is the next forward motion — but a bigger lift since PathState compat is involved. Defer to a focused multi-session effort.

### Step 3.1 — Helper-extract: pure BSDF eval / RR / MIS (DEFERRED beyond 3.0)
Identify methods in dqlin's `PathTracer.slang` that are byte-identical (or
near-identical, modulo signature) to PathTracerX's. Extract into a shared
slang module under `Source/RenderPasses/PathTraceCommon/` (already exists per
[[project_plugin_architecture]]). Initial candidates: `evalMIS`, `russianRoulette`,
`sampleBSDF`, `getMaterialInstance`, light-sampling MIS branches.

### Step 3.2 — Adapter: PathTracerX as field of dqlin's PathTracer
Add a `PathTracerX::PathTracer ptx` field to dqlin's `PathTracer` struct.
Use `ptx.generateScatterRay`, `ptx.updatePathThroughput`,
`ptx.addToPathContribution` for the routine work; keep dqlin's `handleHit`
outer logic but call `ptx.*` for the pure-PT parts.

**PathState delta (Step 3.2 prerequisite):**

Common fields (1:1): `id, bounceCounters, origin, dir, pdf, normal, hit, thp, L, interiorList, sg`.

dqlin-only extras (ReSTIR reservoir bookkeeping):
- `prefixThp` — for rcVertexIrradiance[1] computation
- `rcVertexPathTreeIrradiance` — path-tree irradiance accumulator
- `LDeltaDirect` — direct lighting saved on delta surfaces
- `sharedScatterDir`
- `rcPrevVertexHit` — previous vertex of rcVertex for hybrid shift replay
- `rcPrevVertexWo` — outgoing dir at rcPrev for hybrid shift replay
- `hitDist` — NRD denoiser input

PathTracerX-only:
- `flagsAndVertexIndex` — packed vertex idx + path flags

**Migration strategy:** dqlin keeps its PathState (superset of PathTracerX's
minus the packing detail). PathTracerX methods called via the `ptx` field
operate on a PathState-compatible view — either (a) cast/reinterpret to
PathTracerX's PathState if layouts can be made superset-compatible, or
(b) construct a temporary PathTracerX::PathState from the dqlin one for
each method call. (a) is faster (no copy), (b) is safer (no layout
coupling). Start with (b), evolve to (a) if profile shows the copy is hot.

### Step 3.3 — Reservoir hook in PathTracerX (additive)
PathTracerX gains an optional `inout PathReservoir res` arg on `handleHit`,
gated by `#if USE_RESTIR_RESERVOIRS`. Default off → bit-identical to vanilla.
ReSTIRPTPass instantiates with the macro on.

### Step 3.4 — Delegate `handleHit`
ReSTIRPTPass's `handleHit` becomes `ptx.handleHit(path, res)`. Reservoir
population logic moves into the hook called inside PathTracerX's handleHit.

### Step 3.5 — Delegate `nextVertex` / `handleMiss` / `generatePath`
Same pattern for the remaining 4 methods on the dqlin PathTracer struct.

### Step 3.6 — Adapt `PathBuilder.slang` to Falcor 8 `PathState`
dqlin has a custom `PathState`; PathTracerX uses Falcor 8's `PathState`.
`PathBuilder.slang` (reservoir construction during walk) needs the schema
swap. rcVertex selection / prefix throughput / postfix weight math unchanged.

### Step 3.7 — Drop `Falcor8Compat.slang`
Once everything is Falcor 8 native, remove the bridge module.

### Step 3.8 — Drop dqlin `PathTracer.slang`
Final cleanup — what was 2344 lines becomes a thin adapter struct (~200 lines)
or disappears entirely.

## Validation gate per step

After each step:
1. `.scripts/smoke-pt.sh` (vblind + VC) must pass.
2. `scripts/RestirPT2D_AB.py` AB harness vs `ReSTIRPTReferencePass` must hold
   within frame noise (1 cornell-scale scene minimum, full 7-scene at
   key milestones).
3. RPT00 ladder Cornell_3AL spot-check: err numbers stable.

## Files not nudged (reuse machinery — see PORT_NOTES.md)

- `PathReservoir.slang` — reservoir struct + GRIS math
- `Shift.slang` — reconnection / hybrid / random-replay shift kernels
- `SpatialReuse.cs.slang`, `TemporalReuse.cs.slang`
- `SpatialPathRetrace.cs.slang`, `TemporalPathRetrace.cs.slang`
- `ComputePathReuseMISWeights.cs.slang`
- `Params.slang`, `StaticParams.slang`, `ReflectTypes.cs.slang`
- `NRDHelpers.slang`, `LoadShadingData.slang`

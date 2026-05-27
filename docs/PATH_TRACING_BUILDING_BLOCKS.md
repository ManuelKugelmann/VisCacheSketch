# Path-tracing building blocks — a reuse-maximizing plan

A staged plan for extracting reusable primitives so each new path-tracing
variant is a thin assembly over shared building blocks rather than a
fork-and-diverge copy.

## Current state (2026-05-27)

**Shared (active):**
- `PathTraceCommon/` — 5 modules (selectLightType helpers, LoadShadingData,
  GuideData, ColorType, IPathStateNRD-parameterized NRDHelpers).
- `ReSTIRCommon/` — Reservoir + LightReservoir + CellPool + PairwiseMIS +
  ReservoirIO + ReservoirBoilingFilter.
- `CacheCommon/` — CacheHash only (placeholder; VisCache hashmap still
  inside the VisCache plugin per `project_viscache_three_way_split`).

**Consumers (PT lineage):** PathTracerX, ReSTIRDIPass, ReSTIRDIReferencePass,
ReSTIRNEEPass.
**Consumers (BDPT lineage):** BDPTPass, ReSTIRBDPTPass.
**Consumers (legacy port):** ReSTIRPTPass, ReSTIRPTReferencePass (DQLin
flavor — different signatures, not part of the alignment cohort).

**Remaining duplication signal** (4 PT-lineage plugins):
- `PathTracerNRD.slang` (~279L × 3 redundant copies)
- `ResolvePass.cs.slang` (~203L × 3)
- `GeneratePaths.cs.slang` (~306L × 3)
- `ReflectTypes.cs.slang` (~50L × 3)
- `Params.slang` (~187L × 3, but conceptually plugin-owned)
- `PathTracer.slang` and `TracePass.rt.slang` differ but share architecture
- `PathState.slang` differs only in extension fields (e.g. K-RIS state)

## Layer architecture

Reuse increases as you go down. Each layer only references items in equal
or higher (lower-number) layers.

| Layer | Contents | Module home |
|------:|----------|-------------|
| 1 | Pure data types — enums, packed structs, host/device records | `PathTraceCommon` |
| 2 | Interfaces — `IPathState`, `IPathTracer`, `ISampleGenerator`, `IVisibilityQuery`, `ILightSampler` | `PathTraceCommon` |
| 3 | Generic helpers — parameterized over Layer-2 interfaces | `PathTraceCommon` + family commons |
| 4 | Compute / RT entry points — `[numthreads]`, `[shader("...")]` | per-pass (thin) |
| 5 | Concrete algorithm — `struct PathTracer`, `struct PathState`, ReSTIR resampling, BDPT vertex connection | per-pass |

Plugin-divergent code lives in Layer 5; Layer 3 helpers take Layer 5
concrete types via Layer 2 interface bounds.

## Building blocks — feasibility and priority

### Already extracted (Layer 1+3)

| Block | Status | Notes |
|-------|--------|-------|
| `ColorType` | shared | dispatches on COLOR_FORMAT macro |
| `GuideData` | shared | pure packed struct |
| `LoadShadingData` | shared | bit-identical bodies; hint policy stays per-pass |
| `coreGet*SelectionProbability` | shared | env/emissive/analytic uniform-or-zero |
| `NRDHelpers` | shared | parameterized `<P : IPathStateNRD>` |
| `evalMISImpl` | shared | switch on heuristic id |
| `LightSample` (base 6-field) | shared | `ILightSampleBase` interface |
| `LightType` enum | shared | env/emissive/analytic |

### Next-easy (Layer 1)

| Block | Estimated LoC | Blocker |
|-------|--------------:|---------|
| Bayer subframe tables + `subframeRemap`/`isActiveSubframeSlot` | ~40 × 3 redundant | currently in per-pass `Params.slang`; pure constants + helpers, no plugin coupling |
| `ColorFormat` / `MISHeuristic` enums + `kScreenTileDim` / `kMaxBounces` constants | ~40 × 3 | currently in per-pass `Params.slang`; host-device-shared, plugin-owned by convention |
| `PathTracerParams` struct (without StaticParams import) | ~80 × 3 | host C++ includes per-pass `Params.slang`; needs a #include redirect |

Path forward: split per-pass `Params.slang` into a thin wrapper that
`__exported import`s `PathTraceCommon/PathTracerParams.slang` and adds
`__exported import StaticParams;` for the plugin-local static specialization
constants. Host code keeps including the per-pass `Params.slang` — the
shared types are transitively visible.

### Medium (Layer 2+3) — interface-parameterized

#### `IPathState`

Methods PathTracerNRD reads from a PathState:

```slang
interface IPathState
{
    // already on PathState directly
    uint   getSampleIdx();
    uint   getVertexIndex();
    uint2  getPixel();
    bool   isTransmission();
    bool   isDeltaReflectionPrimaryHit();
    bool   isDeltaTransmissionPath();
    bool   isDiffusePrimaryHit();
    bool   isSpecularPrimaryHit();
    bool   isPrimaryHit();
    // mutating
    [mutating] void terminate();
    // accessors for fields PathTracerNRD reads/writes
    float3   getL();              [mutating] void addL(float3);
    float3   getThp();
    float3   getOrigin();         [mutating] void setOrigin(float3);
    float3   getDir();
    PackedHitInfo getHit();
    float    getPdfF32();         [mutating] void setPdfF32(float);
    float    getSceneLengthF32(); [mutating] void addSceneLength(float);
}
```

Conformance per plugin: 12-line `extension PathState : IPathState { ... }`
mostly forwarding to fields. Already proven for the NRD-subset
(`IPathStateNRD`, commit 30a374a2).

#### `IPathTracer`

Methods PathTracerNRD calls on `extension PathTracer`:

```slang
interface IPathTracer<P : IPathState>
{
    bool handleNestedDielectrics(inout ShadingData sd, inout P path);
    bool generateScatterRay(const ShadingData sd, const IMaterialInstance mi, inout P path);
    ITextureSampler createTextureSampler(const P path, const bool isPrimaryHit);
    bool hasFinishedSurfaceBounces(const P path);
    bool isDeltaReflectionAllowedAlongDeltaTransmissionPath(const ShadingData sd);

    // accessor for the NRD output buffer + demodulation flag
    NRDBuffers getOutputNRD();
    bool       getUseNRDDemodulation();
}
```

Conformance per plugin: forward each method to the existing `PathTracer`
implementation. The implementations already exist; we're just declaring
the interface and writing thin shims.

Risk: Slang's nested generics `IPathTracer<P : IPathState>` + accessing
`PathTracer` fields through interface methods may have inference quirks.
Prove with PathTracerNRD first; if it works, ReflectTypes/GeneratePaths
follow.

### Hard (architectural)

These are where forks deeply diverged and consolidation would require
rewriting algorithm logic, not just extracting helpers.

| Item | Why it's hard |
|------|---------------|
| `PathTracer.slang` (1254L × 4) | Each ReSTIR variant adds different reservoir logic inline — RIS proposal, temporal reuse, spatial reuse, K-RIS quota — interleaved with the trace loop |
| `TracePass.rt.slang` (~687L × 4) | RT entry point with `[shader]` attributes; binding layout differs across plugins |
| `StaticParams.slang` | Each plugin's compile-time constants differ (e.g. NEE adds K-quota knobs) — by design |

These are not Layer-3 helper candidates. They're Layer 5 algorithm code.
The way to reduce duplication here is *not* extraction but to enable
**composition**: a plugin should be ≈ "PathTracerX core + ReSTIR-DI
overlay" rather than a copy of PathTracerX with DI code interleaved.

## Phased roadmap

Each phase ends with a clean commit and full smoke. No half-state.

### Phase A — finish bit-identical extractions (1 commit each)

1. **Bayer tables + subframe helpers** → `PathTraceCommon/Bayer.slang`,
   per-pass `Params.slang` re-exports it.
   Cost: very low. Saves ~120 LoC.

2. **PathTracerParams struct + enums + constants** → `PathTraceCommon/PathTracerParams.slang`,
   per-pass `Params.slang` becomes wrapper.
   Cost: low (host #include indirection). Saves ~560 LoC.

### Phase B — `IPathState` interface (1 commit)

3. Define `IPathState` in `PathTraceCommon/IPathState.slang` (superset of
   `IPathStateNRD`). Per-pass `extension PathState : IPathState`.
   Cost: medium. No code-savings on its own; unlocks Phase C.

### Phase C — share PathTracerNRD via `IPathTracer<P : IPathState>` (1 commit)

4. Define `IPathTracer<P>` in `PathTraceCommon/IPathTracer.slang`.
   Per-pass `extension PathTracer : IPathTracer<PathState>`.
   Move `PathTracerNRD.slang` body to `PathTraceCommon`; each function
   generic over `<T : IPathTracer<P>, P : IPathState>`.
   Cost: medium-high. Saves ~830 LoC.

### Phase D — share compute entry-point inner structs (2 commits)

5. **ResolvePass body** — extract `struct ResolvePass { ... }` body to
   `PathTraceCommon/ResolvePassImpl.slang`. Per-pass `.cs.slang` keeps
   `cbuffer CB`, `[numthreads]`, `main()` entry, imports shared body.
   Cost: low (only depends on Phase A.2 Params split).
   Saves ~600 LoC.

6. **GeneratePaths body** — same pattern. Depends on Phase C
   (`IPathTracer` interface for PathTracer reference).
   Cost: medium. Saves ~900 LoC.

### Phase E — BDPT lineage commons (separate scope)

7. **`BDPTCommon` plugin** — `LightVertexCache`, `PathReservoir`-base,
   `PackedPathVertex`, recursive MIS helpers. Shared between BDPTPass
   and ReSTIRBDPTPass.
   Cost: medium. Saves ~400 LoC.

### Phase F — composition (out-of-scope architecture work)

8. **Algorithm overlay pattern** — design how a ReSTIR variant *composes*
   over a base path tracer rather than forks-and-edits it. This is the
   only way to share `PathTracer.slang` / `TracePass.rt.slang`. Likely
   requires Slang's `extension` + interface dispatch + careful state
   threading. Open research; not a near-term win.

## Cumulative savings estimate

Realistically achievable in this codebase, all phases:

| Phase | Savings |
|------:|--------:|
| A.1 + A.2 | ~680 LoC |
| C | ~830 LoC |
| D | ~1500 LoC |
| E | ~400 LoC |
| **Total** | **~3400 LoC** |

Plus the ~1500 LoC already extracted in tasks #22+#23, total ongoing
deduplication ≈ ~4900 LoC.

## Anti-patterns to avoid

- **Don't share files just because they're bit-identical today.** If the
  bit-identical state is incidental (different forks happen to be in
  sync), sharing locks in a coupling that future divergence will fight.
  Share when the surface is *intentionally* common.
- **Don't extract via `#include`.** Slang's import system has scope and
  type semantics; `#include` is text inclusion that bypasses both. Use
  `__exported import` re-export stubs to share content without forcing
  call-site rename.
- **Don't introduce abstractions ahead of need.** `IPathTracer<P>` is
  warranted because it unblocks 3 file extractions; `IBSDFSampler` is
  not warranted yet because no shared file needs it.
- **Don't break host C++ includes.** Falcor's host-device-shared files
  are also C++ headers. Splits must preserve `#include` paths from
  per-pass C++ to per-pass Params.slang; chain transitively through
  shared module if needed.

## Open questions

1. Slang interface dispatch performance vs hand-written code — assumed
   zero-cost via monomorphization, but worth measuring on PathTracerNRD
   (hot RT path) once landed.
2. ParameterBlock<P : IPathTracer<...>> — does Slang's binding reflection
   work through generic interfaces? Needs a probe before committing to
   ReflectTypes extraction.
3. Composability: even if Phase F is hard, can we at least share the
   trace-loop *skeleton* (camera ray gen, hit/miss dispatch, throughput
   update) and inject the per-plugin NEE / reservoir code via interface
   callbacks? Worth a feasibility sketch.

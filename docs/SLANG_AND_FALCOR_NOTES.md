# Slang & Falcor — version & migration notes

What's currently pinned, what was tested, where the docs live. Read first when chasing a shader-compile, reflection, or Falcor-host-API problem.

---

## Currently pinned

| Package | Version | File |
|---|---|---|
| Falcor | 8.0 (Aug 2024) + 2 post-release cherry-picks (already applied) | `Falcor/Source/Falcor/Core/Version.h` |
| Slang  | 2024.14.6 (Nov 2024) | `Falcor/dependencies.xml` |

Both are NOT the Falcor-defaults. Falcor 8.0 originally shipped with Slang 2024.1.34. We deliberately bumped Slang because newer Slang fixes accumulated warnings/strictness improvements over a year of releases. The bump required two slang-source fixes documented below.

---

## Why Falcor 7 → 8 broke so much (porting context)

Falcor 8.0 (Aug 19 2024) was a major architectural release, not a point bump. Anyone porting a Falcor 7 codebase (e.g. Shmaug/ReSTIR-BDPT, DQLin/ReSTIR_PT, NVlabs/conditional-restir-prototype) needs to apply roughly the same migration. See [PORTING.md](PORTING.md) for the ReSTIRPTPass port, and `Source/RenderPasses/ReSTIRBDPTPass/` commits 847381d / 26b456d for the BDPT port — the deltas are mechanical and stereotyped.

Documented breaking changes from the [Falcor 8.0 release notes](https://github.com/NVIDIAGameWorks/Falcor/releases/tag/8.0):

| Falcor 7 | Falcor 8 |
|---|---|
| `Scene::setRaytracingShaderData(ctx, var)` | `Scene::bindShaderDataForRaytracing(ctx, var["gScene"])` (note: pass `gScene` sub-var, not root) |
| `EmissivePowerSampler/Uniform/LightBVH` ctor `(ctx, ref<Scene>)` | `(ctx, ref<ILightCollection>)`. Same for `EmissiveLightSampler::update(ctx)` → `update(ctx, scene->getILightCollection(ctx))` |
| `Scene::getActiveLights` | `Scene::getActiveAnalyticLights` |
| `Scene::getActiveLightCount` / `getActiveLight` | removed (count active analytic lights via `getActiveAnalyticLights().size()`) |
| `Buffer::getElementSize()` | `Buffer::getStructSize()` |
| Buffer views: element ranges | byte ranges (`createBufferRange(byteOffset, byteSize)`) |

Slang-side breaks (most are Slang 2024.1.x → 2024.14.x; some Falcor 8 specific):

| Falcor 7 (Slang 2024.1.x) | Falcor 8 (Slang 2024.14+) |
|---|---|
| `HitInfo::getData()` | `HitInfo::pack()` |
| `prepareShadingData(v, mid, dir, lod)` | `prepareShadingData(v, mid, dir)` (LOD is internal) |
| `traceSceneRay<true>(ray, out hit, out hitT, flags, mask)` | `hit = traceSceneRay<1>(ray, out hitT, flags, mask)` (returns by value, template arg is `int`) |
| `EmissiveSampler.sampleLight(sg, out selectionPdf)` overload | removed — only `sampleLight(pos, normal, upperOnly, sg, out TriangleLightSample)` survives |
| `evalTriangleSelectionPdf(triIdx)` | `evalTriangleSelectionPdf(pos, normal, upperOnly, triIdx)` — Power/Uniform ignore geom args; LightBVH uses them |
| `BSDFProperties.eta` | removed — `ShadingData.IoR` is the new home |
| `CameraData.prevCameraW` / `Camera::computeRayPinholePrevFrame` | removed — prev-frame plumbing is now `CameraData.prevViewMat` / `prevPosW` only |
| `RWByteAddressBuffer::InterlockedAddF32` | NVAPI shader extension required — Falcor builds with `FALCOR_HAS_NVAPI=OFF` by default, use a 16-iter `InterlockedCompareExchange` CAS loop on the uint reinterpretation |
| `mLightVertexCache[i] = v` (via `__subscript` set) | not an l-value in 2024.14+; write through the underlying buffer field (`mLightVertexCache.lightVertices[i] = v`) |
| `[require(sm_6_6, …)]` on compute shaders touching scene vertex buffers | needs `compute` capability too: `[require(compute, sm_6_6, …)]` |

---

## Slang version-bump experiments

Tested versions (one branch each, full 17-pass smoke battery on CornellBox_1AreaLight):

| Version | Build | 17-pass smoke | Notes |
|---|---|---|---|
| 2024.1.34 (Falcor 8 default) | clean | 17/17 | Baseline. ReSTIRBDPT resolve-pass crash workaround in `BDPT.cs.slang` required (ShiftPath branch disabled). |
| **2024.14.6** (current pin) | clean | 17/17 | Two source fixes needed: l-value subscript + `compute` capability. Did not fix the ConnectToSuffix reflection bug. |
| 2025.5  | clean | 0/17 | Falcor's own `Scene/HitInfo.slang` breaks: `this = {};` no longer a valid zero-init in slang 2025+ (needs explicit arg). 3 sites in HitInfo.slang alone, more elsewhere. Falcor 8 source would need patching to align — too invasive. |
| 2026.9.1 (latest as of May 2026) | clean | 0/17 | Stricter constant-fold: BF_SET macro in `HostDeviceShared.slangh` overflows uint conversion. Also: `packSnorm2x16(float2)` becomes ambiguous (new overloads). Massive Falcor-side breakage. |

**Slang downgrade gotcha (2026-05-21):** when downgrading from 2025.x → 2024.14.6 (or any cross-version-API change), `build.bat --clean` did not remove precompiled headers (`Falcor.dir/Release/cmake_pch.pch`), causing `LNK2019 unresolved external symbol slang_createGlobalSession2`. Fixed: `--clean` now nukes `*.pch` and `cmake_pch.obj` explicitly in addition to CMakeCache + CMakeFiles. Symptom to recognize next time: linker references a Slang C-API symbol that doesn't exist in the current `external/packman/slang/include/slang.h`.

**Takeaway:** 2024.14.6 is the sweet spot between "stuck on Falcor's pinned version" and "Slang ABI has moved too far." It picks up ~10 months of slang fixes without breaking Falcor 8.0.

---

## The ConnectToSuffix reflection bug (open)

Symptom: With Falcor 8.0 + Slang 2024.1.34 OR 2024.14.6, `ComputePass::setVars(nullptr)` on the `ResolveLightTraceReservoirs` entry of `ReSTIRBDPTPass/BDPT.cs.slang` triggers a silent SIGSEGV during `ParameterBlock::ParameterBlock` construction (stack: `ProgramVars::create` → `ParameterBlock::ParameterBlock`).

Bisection (see commits `dde8bf8` and `d6e2424`):
- Stubbing the entire `ShiftPath` body to `return result;` → no crash → it's the body, not the signature
- Bottom half of `ShiftPath` body (camera-subpath shift) → crashes
- Reducing the suffix block to only `ConnectToSuffix(...)` → still crashes
- Stubbing the `ConnectToSuffix` body to `return result;` → no crash → it's `ConnectToSuffix` itself
- Stubbing the MIS-weight half of `ConnectToSuffix` (lines 175 onward) → still crashes → trip is in lines 87-175 (visibility check, camera-pdf, `SetNextVertex<true>`, `vertex.EvaluateReflectance`)
- Splitting the chained `.mis` access on `InitializeLightPath<true, true>(...)` return → didn't help

What we know:
- The Slang version doesn't matter (2024.1.34 and 2024.14.6 both crash identically)
- The shader compiles and links cleanly; the crash is during ProgramVars layout reflection
- Only `ResolveLightTraceReservoirs` trips it — `SampleCameraPaths` calls into the same templated helpers (`InitializeLightPath`, `ConnectToCamera`, …) without crashing

What we tried that did NOT work:
- Refactoring `ShiftPath`/`ConnectToSuffix` to out-param style → ran into a separate Slang IR bug (`InternalError: missing case for getting IR default value` on `out PathSample = {}`)
- Splitting chained method access on parameter-block method returns
- Slang version bump

What still needs to be tried (task #10):
- Move `ConnectToSuffix` outside `extension PathGenerator` and pass `gPathGenerator` explicitly
- Replace `RWStructuredBuffer<PathReservoir>` in `PathGenerator` struct with raw `RWByteAddressBuffer` + manual pack/unpack
- Slang issue tracker — file a minimal reproducer

**Root-cause pattern confirmed (2026-05-21):** ReSTIRPTPass `Source/RenderPasses/ReSTIRPTPass/Shift.slang` — the Falcor 8 working analogue — defines every shift function (`computeShiftedIntegrand`, `shiftAndMergeReservoir`, `mergeReservoir`, …) as a **free function** at file scope that takes `RestirPathTracerParams params` as an explicit argument. They are NOT extension methods on `ParameterBlock<PathTracer>`. BDPT's `PathShift.slang` wraps every function in `extension PathGenerator { ... }` making them parameter-block methods, and *that* is what Falcor 8's `ParameterBlock::ParameterBlock` reflection trips on for the resolve entry point. Other entry points (SampleCameraPaths, SampleLightPaths) survive because they touch fewer / smaller methods on the ParameterBlock.

**Plumbing fix** (algorithm unchanged):
1. Remove the `extension PathGenerator { ... }` wrapper in `PathShift.slang`
2. Rewrite each function as a free function. Member accesses like `mParams.xxx` become `gPathGenerator.mParams.xxx`; method calls like `Occluded(ray)` become `gPathGenerator.Occluded(ray)`
3. Callers in `BDPT.cs.slang` / `SpatialReuse.cs.slang` / `TemporalReuse.cs.slang` switch from `gPathGenerator.ShiftPath(...)` to `ShiftPath(...)`

**Refactor scope discovered (2026-05-21):** moving `ShiftPath` and `ShiftCausticPath` out of the `extension PathGenerator` block compiles to *many* `undefined identifier` errors — every PathGenerator-member identifier (`gBidirectional`, `gDisableCameraConnection`, `gShiftSuffixes`, `mParams`, `Occluded`, `GetShiftedSuffixVertex`, `InitializeLightPath`, `SetNextVertex`, `ShiftLightSubpath`, `ShiftPrefix`, `ConnectToSuffix`, `ShiftSuffix`, `EvalLightContribution`, `ConnectToCamera`, `PackLightSubpathVertex`, …) needs `gPathGenerator.` prefix; **AND** nested types like `PathState<bShift>` (defined inside `struct PathGenerator`) need `PathGenerator.PathState<bShift>` qualification. The refactor is mechanical but invasive (~30 sites across two functions). Same applies to refactoring block 1 (helpers ConnectToSuffix etc.) if needed. Estimated as a half-day of focused mechanical work + verification.

**Wrapper test ruled out (2026-05-21):** wrapping `gPathGenerator.ShiftPath(...)` in a free function `ShiftPathFree(...)` does NOT bypass the crash. Slang inlines through the wrapper so the reflection sees the same call graph. The fix must change the actual function *definition* context, not the call site.

**Free-function refactor ruled out (2026-05-21, commit 67f1a165):** moved `ShiftPath` and `ShiftCausticPath` out of `extension PathGenerator { ... }` into actual free functions at file scope. Their bodies now use `gPathGenerator.` prefix on every PathGenerator-member access. The refactor is mechanically clean and produces 17/17 smoke PASS — but **re-enabling the `gShiftLightPathsToPixelCenters` branch still crashes setVars**. The "extension method vs free function" hypothesis was therefore wrong. The trip is in the call-graph complexity reachable from the resolve entry point: `ShiftPath → ConnectToSuffix → Occluded / SetNextVertex / InitializeLightPath<true,true> / vertex.EvaluateReflectance / GetShiftedSuffixVertex / …`. Those helpers ARE still extension methods on PathGenerator. Refactoring the helpers too would require fully qualifying `PathGenerator.PathState<bShift>` everywhere — gnarly but possible. Alternative: inline ShiftPath's body into the resolve compute shader to break the cross-function-reflection chain.

Workaround in effect: the `gShiftLightPathsToPixelCenters` branch is commented out in `BDPT.cs.slang`. This disables only the optional sub-pixel re-projection optimization; the rest of the ReSTIR resampling pipeline is intact and renders 8 frames cleanly. See [project_restir_bdpt_port memory](../memory) for the running status.

### Feature-by-feature status (ReSTIRBDPTPass on Falcor 8 + Slang 2024.14.6)

| ReSTIRBDPT property | Status | Notes |
|---|---|---|
| `useBPT=True` (bidirectional light subpaths)                         | ✓ works   | core BDPT feature |
| `useResampling=True` (per-pixel ReSTIR reservoir merge)              | ✓ works   | tested 8-frame smoke |
| `useResampling=True` + `gShiftLightPathsToPixelCenters` enabled      | ✗ broken  | the ConnectToSuffix reflection bug; workaround = disable the branch |
| `useCausticReservoirs=True` (caustic reservoir buffer, no temporal)  | ✓ works   | tested standalone — 64-frame PASS via `scripts/ReSTIRBDPTPass_Caustic_Graph.py` |
| `useTemporalResampling=True`                                         | ✗ broken  | `TemporalReuse.cs.slang` reaches `ShiftPath` through the same reflection trip |
| `useCausticShift=True`                                               | ✗ blocked | requires `useTemporalResampling=True` |
| `spatialReusePasses>0`                                               | ✓ works   | tested 16-frame PASS — confirms the reflection trip is SPECIFIC to BDPT.cs.slang::ResolveLightTraceReservoirs, not to ShiftPath itself. SpatialReuse.cs.slang::main is a separate compute pass with a different call graph; its setVars reflects cleanly even though it calls into `ShiftPath` → `ConnectToSuffix` |

---

## Useful upstream resources

- [Slang Parameter Block guide](https://shader-slang.org/docs/parameter-blocks/) — official cross-platform parameter-block semantics
- [Slang Reflection API guide](http://shader-slang.org/slang/user-guide/reflection) — what's reflectable and what isn't
- [Slang Reflection API doc-update blog (Dec 2024)](https://shader-slang.org/blog/2024/12/18/reflection-api-doc-update/) — pointer to the rewritten docs
- [Falcor 8.0 release notes](https://github.com/NVIDIAGameWorks/Falcor/releases/tag/8.0) — the authoritative migration list
- [Falcor commits since 8.0](https://github.com/NVIDIAGameWorks/Falcor/commits/master) — 2 commits total (GBufferRT linearZ slope, GraphicsState leak); both already applied in our subtree as of 2026-05-21

---

## When to revisit

- New Slang release with a documented parameter-block reflection fix → try a bump
- New Falcor release tagged past 8.0 → cherry-pick relevant fixes
- ConnectToSuffix bug becomes a research-time blocker → file a minimal Slang reproducer

# Local Fixes to Vanilla Falcor

This file tracks bug fixes applied to the Falcor subtree that diverge from
NVIDIA's upstream Falcor 8.0. These should be reported upstream when possible.

---

## 1. ToneMapper: missing `exposureValue` in constructor properties

**File:** `Source/RenderPasses/ToneMapper/ToneMapper.cpp`
**Commit:** 8e6cf51 (2026-03-16)

`ToneMapper::parseProperties()` handled every property key except
`exposureValue`. The property constant (`kExposureValue`), member variable,
getter/setter, and pybind11 binding all existed, but the `else if` branch
in `parseProperties()` was missing. Passing `"exposureValue"` to
`createPass("ToneMapper", {...})` silently fell through to:

```
logWarning("Unknown property '{}' in a ToneMapping properties.", key);
```

**Fix:** Added the missing case:

```cpp
else if (key == kExposureValue)
    setExposureValue(value);
```

**Upstream status:** Not yet reported.

---

## 5. Falcor: add /EHsc for MSVC exception handling

**File:** `Source/Falcor/CMakeLists.txt`

MSVC 14.44+ (VS 2022) `ppltasks.h` and `<vector>` use C++ exception
handlers internally. Without `/EHsc`, the compiler emits warning C4530
("C++ exception handler used, but unwind semantics are not enabled").
Combined with `/WX` (warnings as errors), this breaks the build.

**Fix:** Added `/EHsc` to the PUBLIC MSVC compile options for the Falcor
target, enabling standard C++ exception handling with stack unwinding.

**Upstream status:** Not yet reported.

---

## 6. validate_headers: propagate COMPILE_OPTIONS to VH targets

**File:** `CMakeLists.txt` (root)

The `validate_headers()` function copies `INCLUDE_DIRECTORIES`,
`LINK_LIBRARIES`, `COMPILE_DEFINITIONS`, and `COMPILE_FEATURES` from the
original target to the VH validation target, but not `COMPILE_OPTIONS`.
This means `/EHsc`, `/WX`, `/W4` etc. set via `target_compile_options()`
do not propagate, causing C4530 warnings on the VH targets.

**Fix:** Added `COMPILE_OPTIONS` to the property copy loop.

**Upstream status:** Not yet reported.

---

## 2. setup.bat/sh: use VISCACHE_ROOT env var for git submodule update

**Files:** `setup.bat`, `setup.sh`

The original scripts used `git -C %~dp0\..\..` (bat) and
`git -C "${BASE_DIR}/../.."` (sh) to navigate to the git root for submodule
init. Since Falcor is a subtree inside the VisCacheSketch repo, this relative
path landed outside the repository, causing:

```
fatal: not a git repository (or any of the parent directories): .git
```

**Fix:** The parent scripts (`setup-build-system.bat/.sh`, `build.bat/.sh`)
now set a `VISCACHE_ROOT` environment variable pointing to the project root.
`Falcor/setup.bat/.sh` use `VISCACHE_ROOT` when available, falling back to a
plain `git submodule update` (no `-C`) when run standalone.

**Upstream status:** N/A (subtree integration issue, not an upstream bug).

---

## 3. IMaterialInstance / StandardBSDF: add evalBsdfAndPdf(lobeMask)

**Files:**
- `Source/Falcor/Rendering/Materials/IMaterialInstance.slang`
- `Source/Falcor/Rendering/Materials/BSDFs/StandardBSDF.slang`
- `Source/Falcor/Rendering/Materials/StandardMaterialInstance.slang`

ReSTIR PT shift mapping requires per-lobe-class PDF evaluation (e.g., "PDF
from diffuse lobes only") using the original lobe selection weights. Falcor 8's
`setActiveLobes()` zeroes disabled lobes and renormalizes the remaining weights,
which changes the PDF values and produces incorrect shift mapping Jacobians.

Ported `evalBsdfAndPdf(lobeMask)` from the NVlabs Conditional ReSTIR prototype
(Lin et al., SIGGRAPH 2023). The method evaluates BSDF and PDF simultaneously,
returning filtered results for lobes matching `lobeMask` alongside the all-lobe
PDF, using the original (pre-renormalization) lobe selection weights.

- `StandardBSDF::evalBsdfAndPdf()` — core implementation with per-lobe filtering
- `StandardMaterialInstance::evalBsdfAndPdf()` — world-to-local coordinate wrapper
- `IMaterialInstance::evalBsdfAndPdf()` — interface method (new)
- `MaterialInstanceBase::evalBsdfAndPdf()` — default stub returning zeros
- `ClothMaterialInstance::evalBsdfAndPdf()` — explicit stub (Slang doesn't
  inherit `[open]` base methods to satisfy interface requirements)
- `HairMaterialInstance::evalBsdfAndPdf()` — same

**Upstream status:** Enhancement, not a bug fix. Useful for any algorithm
needing per-lobe PDF decomposition without weight renormalization.

---

## 4. Emissive light samplers: restore skipRandomNumber()

**Files:**
- `Source/Falcor/Rendering/Lights/EmissivePowerSampler.slang`
- `Source/Falcor/Rendering/Lights/LightBVHSampler.slang`
- `Source/Falcor/Rendering/Lights/EmissiveUniformSampler.slang`
- `Source/Falcor/Rendering/Lights/EmissiveLightSampler.slang` (NullEmissiveSampler)

Falcor 4.x had `skipRandomNumber()` on the `IEmissiveLightSampler` interface.
Falcor 8 removed it. ReSTIR PT path replay needs to advance the random sequence
by the exact number of random numbers that `sampleLight()` consumes when
skipping an emissive light sampling step. Each sampler consumes a different
count: EmissivePower uses 1D+1D+2D=4, LightBVH uses 1D+2D=3, Uniform uses
1D+2D=3. Hardcoding a fixed skip causes random sequence misalignment.

Restored `skipRandomNumber()` as a non-interface method on each sampler struct.
Not added back to `IEmissiveLightSampler` (not needed — called via concrete
type `EmissiveLightSampler` which is a compile-time typedef).

**Upstream status:** Enhancement for path replay algorithms.

---

## 5. CudaInterop: fix CUDA 12.9 build + suppress LNK4098 on MSVC

**File:** `Source/Samples/CudaInterop/CMakeLists.txt`

Two issues:

1. **CUDA 12.9 build failure:** A bare `target_compile_options(... /wd4100)`
   passes `/wd4100` directly to nvcc. CUDA 12.9's nvcc is stricter and
   misinterprets the MSVC flag as a filename, causing:
   `nvcc fatal: A single input file is required for a non-link phase when an outputfile is specified`

2. **LNK4098 warning:** CUDA runtime statically links LIBCMT, conflicting
   with Falcor's dynamic CRT (MSVCRT).

**Fix:** Use generator expressions to route `/wd4100` correctly per language:

```cmake
target_compile_options(CudaInterop PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:/wd4100>
    $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=/wd4100>
)
target_link_options(CudaInterop PRIVATE /NODEFAULTLIB:LIBCMT)
```

**Upstream status:** Not yet reported.

---

## Proposed upstream improvement: FALCOR_PLUGIN_DIRS

Falcor has no built-in way to build external render passes without copying sources
into the Falcor tree or patching `Source/RenderPasses/CMakeLists.txt`. A
`FALCOR_PLUGIN_DIRS` CMake variable would allow projects to register external plugin
directories cleanly.

**Proposed API:**

```cmake
# In the consuming project's CMakeLists.txt or via -D on the command line:
set(FALCOR_PLUGIN_DIRS
    "${CMAKE_SOURCE_DIR}/Source/RenderPasses/VisCache"
    "${CMAKE_SOURCE_DIR}/Source/RenderPasses/ReSTIRPTPass"
)

# Then add_subdirectory(Falcor) — Falcor discovers and builds the external plugins.
```

**Implementation sketch** (in `Falcor/CMakeLists.txt`, after the `add_plugin()` function
definition and before `get_property(plugin_targets ...)`):

```cmake
# Build external plugins from FALCOR_PLUGIN_DIRS (user-provided list of directories).
# Each directory must contain a CMakeLists.txt that calls add_plugin().
if(DEFINED FALCOR_PLUGIN_DIRS)
    foreach(plugin_dir IN LISTS FALCOR_PLUGIN_DIRS)
        get_filename_component(plugin_name "${plugin_dir}" NAME)
        message(STATUS "Adding external plugin: ${plugin_name} from ${plugin_dir}")
        add_subdirectory("${plugin_dir}" "${CMAKE_CURRENT_BINARY_DIR}/external_plugins/${plugin_name}")
    endforeach()
endif()
```

This would eliminate the need for:
- Copying source files into the Falcor tree
- Patching `Source/RenderPasses/CMakeLists.txt`
- Complex integrate-plugins scripts

External plugins would use the same `add_plugin()` / `target_copy_shaders()` macros
and get included in `plugins.json` automatically via the existing `FALCOR_PLUGIN_TARGETS`
global property.

### Data, shaders, and scripts

Falcor already provides `target_copy_shaders(target subdir)` for `.slang` files.
External plugins also need conventions for data files (e.g. lookup tables, test
scenes) and scripts (e.g. render graph configs, smoke tests). Proposed companion
macros:

```cmake
# Copy Data/ subdirectory to ${FALCOR_OUTPUT_DIRECTORY}/data/<subdir>/
function(target_copy_data target subdir)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/Data")
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${CMAKE_CURRENT_SOURCE_DIR}/Data"
                "${FALCOR_OUTPUT_DIRECTORY}/data/${subdir}"
            COMMENT "Copying ${target} data files"
        )
    endif()
endfunction()

# Copy Scripts/ subdirectory to ${FALCOR_OUTPUT_DIRECTORY}/scripts/<subdir>/
function(target_copy_scripts target subdir)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/Scripts")
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${CMAKE_CURRENT_SOURCE_DIR}/Scripts"
                "${FALCOR_OUTPUT_DIRECTORY}/scripts/${subdir}"
            COMMENT "Copying ${target} scripts"
        )
    endif()
endfunction()
```

**Convention-based alternative:** Instead of explicit macro calls, `add_plugin()`
could auto-detect and deploy standard subdirectories:

```cmake
function(add_plugin target)
    # ... existing add_plugin() logic ...

    # Auto-deploy standard subdirectories if they exist
    foreach(asset_type IN ITEMS Data Scripts Scenes)
        string(TOLOWER "${asset_type}" asset_lower)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${asset_type}")
            add_custom_command(TARGET ${target} POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${CMAKE_CURRENT_SOURCE_DIR}/${asset_type}"
                    "${FALCOR_OUTPUT_DIRECTORY}/${asset_lower}/${target}"
                COMMENT "Deploying ${target}/${asset_type}"
            )
        endif()
    endforeach()
endfunction()
```

This way a plugin directory like:
```
MyPlugin/
  CMakeLists.txt      # calls add_plugin(MyPlugin)
  MyPlugin.cpp
  MyPlugin.slang      # deployed by target_copy_shaders()
  Data/               # auto-deployed to build/data/MyPlugin/
    lookup_table.txt
  Scripts/             # auto-deployed to build/scripts/MyPlugin/
    MyPlugin_Graph.py
  Scenes/              # auto-deployed to build/scenes/MyPlugin/
    TestScene.pyscene
```

would be fully self-contained — no external deploy scripts needed.

**Current workaround:** We add `add_subdirectory()` calls to `Falcor/CMakeLists.txt`
via `integrate-plugins.bat`, pointing to `Source/RenderPasses/*` with explicit binary
directories. Data and script deployment is handled by `deploy_to_release.sh`.

---

## 7. setup_vs2022.bat: add --host parameter for toolset architecture

**File:** `setup_vs2022.bat`

The original script hardcodes `host=x86` toolset. When a CMake cache exists
from a previous configure with `host=x64` (e.g. from CI or a VS x64 developer
prompt), reconfiguring fails with "generator toolset does not match".

**Fix:** Added `--host` parameter (default: `x86` for backward compatibility).
Usage: `setup_vs2022.bat --host x64` or `setup_vs2022.bat ci --host x64`.

**Upstream status:** Not yet reported.

---

## 13. ParameterBlock: cbuffer must be bound member-by-member

**Files:** callers that bind cbuffer-typed shader variables

Falcor 8's `ParameterBlock::setBuffer()` does not support binding a raw `Buffer`
to a `cbuffer` shader variable. Calling `rootVar["MyCBuffer"] = someBuffer` hits
the else branch in `ParameterBlock.cpp:506` which throws "Error trying to bind
buffer to a non SRV/UAV variable." `setBlob()` also rejects cbuffer types.

**Workaround:** bind cbuffer members individually:
```cpp
rootVar["MyCBuffer"]["gFieldA"] = valueA;
rootVar["MyCBuffer"]["gFieldB"] = valueB;
// ...
```

**Upstream status:** Falcor limitation. Consider fixing `setBuffer()` to accept
buffers typed as `ConstantBuffer<T>`, or `setBlob()` to support cbuffer types.

---

## 14. PathTracer: Bayer subframe gate in GeneratePaths

**Files:**
- `Source/RenderPasses/PathTracer/GeneratePaths.cs.slang` — active-slot gate
- `Source/RenderPasses/PathTracer/Params.slang` — adds `subframeIdx` field
- `Source/RenderPasses/PathTracer/PathTracer.cpp` — advances `subframeIdx`
  per dispatch, `frameCount` per logical frame, sets the gate define

A compile-time define selects an N×N Bayer pixel gate. When `N > 1`, each
dispatch shades only pixels whose
`bayerTable[(y%N)*N + (x%N)] == params.subframeIdx`. Inactive-slot threads
set `spp = 0` and skip path generation (prefix sum and warp reduction remain
active — required by pass invariants).

Bayer tables (low-discrepancy, temporally stable):

```slang
static const uint kBayer2x2[4]  = { 0, 2, 3, 1 };
static const uint kBayer4x4[16] = {  0,  8,  2, 10,
                                    12,  4, 14,  6,
                                     3, 11,  1,  9,
                                    15,  7, 13,  5 };
```

### Frame-counter split

`params.frameCount` represents a **logical frame** (= N² subframe dispatches).
`params.subframeIdx` cycles 0..N²−1 within a logical frame. In `endFrame`:

```cpp
mParams.subframeIdx++;
if (mParams.subframeIdx >= kSubframeCount) {
    mParams.subframeIdx = 0;
    mParams.frameCount++;      // logical frame boundary
}
```

Consumers that use `frameCount` for RNG / jitter get the same seed for all
N² subframes of one logical frame — all subframes of a logical frame share
the same camera jitter / sample stream.

### Current implementation (full-dispatch early-out)

Full-size dispatch per subframe; inactive-slot threads early-out. Cost:
N²−1 of N² threads do wasted work per subframe.

### TODO (optimization): reduced-size dispatch

Dispatch `ceil(W/N) × ceil(H/N)` groups; at shader entry, remap the threadID:

```slang
uint2 reducedPixel = deinterleave_8bit(threadIdx) + (tileID << kScreenTileBits);
uint2 pixel = reducedPixel * N + bayerInv[subframeIdx];
```

Downstream shader logic uses `pixel` as before — no other changes required.
The host-side loop in `PathTracer::execute()` wraps `generatePaths` +
`tracePass` in an N² loop, advancing `subframeIdx` each iteration; `resolve`
runs once at the end. Downstream passes (AccumulatePass, ToneMapper, NRD,
RTXDI) see a fully-populated frame and need no changes. Saves ~1/N² GPU
cost with identical output.

### Open items

- **RTXDI**: its `update()` currently runs N² times per logical frame from
  inside the PathTracer loop. Temporal reservoirs see sparse per-subframe
  coverage. Either move `update()` outside the loop (once on the fully
  populated sample buffer) or teach RTXDI the Bayer pattern.
- **ReSTIRPTPass**: still dispatches full-frame. Needs the same treatment —
  reduced N² dispatch, `subframeRemap()` at kernel entry, and a matching
  subframe loop in `execute()` / reuse passes.

**Upstream status:** The Bayer-subframe mechanism is a general pixel-write-
order tool — useful for anything that cares about intra-frame cell/hash
write ordering independently of per-pixel sample coverage.

---

## 15. PathTracer: native ReSTIR-PT integration (restirpt_2d port)

**Files:**
- `Source/RenderPasses/PathTracer/PathReservoir.slang` (new) — non-BPR
  PathReservoir struct, GRIS streaming-add helpers (`add`, `merge`,
  `mergeWithResamplingMIS`, `mergeInSamplePixel`, `prepareMerging`,
  `finalizeRIS`, `finalizeGRIS`).
- `Source/RenderPasses/PathTracer/PathShift.slang` (new) — pure-math
  `computeReconnectionJacobian` helper (no scene access — Jacobian-only).
- `Source/RenderPasses/PathTracer/PathState.slang` (extended) — added
  `rcVertexCapPosW` / `rcVertexCapFaceN` / `rcVertexCapHit` /
  `rcVertexCapLocked` (rcVertex selection state during path-walk),
  `primaryHitCapPosW` / `primaryHitCapFaceN` (primary-hit cache for
  cross-frame disocclusion in the temporal merge).
- `Source/RenderPasses/PathTracer/StaticParams.slang` — `USE_RESTIRPT`
  compile-time define.
- `Source/RenderPasses/PathTracer/Params.slang` — `RestirPathTracerParams`
  struct slot (field-for-field port, currently scaffold-only).
- `Source/RenderPasses/PathTracer/TracePass.rt.slang` — added
  `RESTIRPT_SPATIAL_PASS` define-gate around the raygen entry. When defined,
  the raygen calls `gPathTracer.runRestirPTSpatialReuse(pixel)` instead of
  the path-walking `gScheduler.run(pixel)`.
- `Source/RenderPasses/PathTracer/PathTracer.slang` — new globals (gated
  behind `USE_RESTIRPT`):
  - `RWStructuredBuffer<PathReservoir> gRestirPTReservoirs` — trace-pass
    output (one reservoir per pixel)
  - `RWStructuredBuffer<PathReservoir> gRestirPTReservoirsTemporal` —
    spatial-pass output (current frame, fed to history copy)
  - `RWStructuredBuffer<PathReservoir> gRestirPTReservoirsHistory` —
    previous frame's temporal reservoirs (read-only in spatial pass)
  - `Texture2D<float2> gRestirPTMotionVectors` — for temporal reprojection
  - `import Scene.RaytracingInline` — needed for `SceneRayQuery` visibility
    rays from the spatial-reuse raygen.
  
  And new method `runRestirPTSpatialReuse(uint2 pixel)`: performs GRIS
  spatial reuse with reconnection-shift + temporal merge entirely inside
  the RT raygen binding context (so `loadShadingData` and UAV writes work).
- `Source/RenderPasses/PathTracer/PathTracer.cpp` / `.h` — added a second
  `TracePass` instance `mpRestirPTSpatialPass` constructed with
  `"RESTIRPT_SPATIAL_PASS"` as an extra define, plus reservoir/motion
  buffer allocation and per-frame history copy.

### Why a second TracePass (RT raygen) instead of a compute pass?

The reference (`Source/RenderPasses/ReSTIRPTPass/SpatialReuse.cs.slang`)
runs spatial reuse from a compute pass. The same approach in our integration
TDR'd inside `loadShadingData` whenever its result fed any UAV write — even
when `loadShadingData` itself returned valid data. Multiple bisects across
sessions narrowed it to a Slang/DXC code-gen interaction with the compute-
pass binding context that we could not root-cause cleanly. Moving the
spatial-reuse kernel to an RT-pipeline raygen entry (binding context
identical to the existing trace pass) sidesteps the issue entirely:
`loadShadingData` + UAV writes coexist as expected. `SceneRayQuery` /
`traceVisibilityRay` work from raygen for the Reconnection-shift visibility
test.

### RIS finalize vs GRIS finalize — feedback amplification gotcha

`PathReservoir::merge()` includes `inReservoir.M * inReservoir.weight` in
its `w` accumulation (RIS form). `finalizeRIS` divides by `M·p̂` to balance
that M factor; `finalizeGRIS` divides only by `p̂` (designed for paths
that fold the M factor into MIS weights).

If you call `merge()` (M factor inside) and then `finalizeGRIS` (no /M),
the M factor is unbalanced. With temporal reuse and an M-cap of 30, the
history's effective contribution multiplies by ~30, and the per-frame
finalized weight grows by a constant factor. Iterated 32 times that's
exponential explosion (we observed 1000× output magnitude, OkLab error
0.515 vs vanilla 0.005, on a parity AB at SPP=32 Cornell_1AreaLight).

**Rule:** plain RIS path → `merge()` + `finalizeRIS`. GRIS-with-resampling-
MIS path → `mergeWithResamplingMIS()` + `finalizeGRIS`. Don't cross them.

### How rcVertex capture interacts with the path-walk

`PathState` carries the rcVertex selection state across bounces. The
path-walk picks the first secondary that satisfies the Lin 2026 §4
footprint criterion (currently approximated as "first rough secondary",
roughness-gated by `kSpecularRoughnessThreshold = 0.2f`). Once locked,
later bounces don't overwrite the rcVertex.

`writeOutput` (called at path end, gated by `USE_RESTIRPT`) packs the
captured rcVertex into the output reservoir alongside `path.L` (the
final radiance, soft-clamped at write to bound fireflies entering the
reservoir).

### Cbuffer per-field binding rule still applies

`RestirPathTracerParams` (in `Params.slang`) is a scaffold for the full
DQLin parameter surface. As of the initial integration only `useRestirPT`
on the static-params side is wired through. Any field added to the cbuffer
struct must be enumerated at every binding site (CLAUDE.md cbuffer rule).

**Upstream status:** Internal to VisCacheSketch — the DQLin reference
(`Source/RenderPasses/ReSTIRPTPass/`) is byte-frozen as the parity target;
this integration ports its algorithm into Falcor's PathTracer plugin.

---

## 9. CMakeLists: FALCOR_FLAT_OUTPUT to skip $<CONFIG> subdirectory

**File:** `CMakeLists.txt` (line 206)

VS2022 multi-config builds append `/$<CONFIG>` (e.g. `/Release`) to the output
directory, splitting binaries from scripts/data which deploy to the root. Setting
`-DFALCOR_FLAT_OUTPUT=ON` skips the config suffix so all configs output directly
to `FALCOR_RUNTIME_OUTPUT_DIRECTORY`.

**Fix:** Guard the `$<CONFIG>` genex with `AND NOT FALCOR_FLAT_OUTPUT`.

**Upstream status:** Enhancement for flat output layouts.

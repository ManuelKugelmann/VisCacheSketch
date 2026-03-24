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

## 13. VisCache cbuffer: per-member binding required

**Files:** `PathTracer.cpp`, `MinimalPathTracer.cpp`, `RTXDIPass.cpp`, `ReSTIRPTPass.cpp`

Falcor 8's `ParameterBlock::setBuffer()` does not support binding a raw `Buffer`
to a `cbuffer` shader variable. Calling `rootVar["MyCBuffer"] = someBuffer` hits
the else branch in `ParameterBlock.cpp:506` which throws "Error trying to bind
buffer to a non SRV/UAV variable." `setBlob()` also rejects cbuffer types.

**Fix:** Bind cbuffer members individually:
```cpp
rootVar["VisCacheParams"]["gTableCapacity"] = params.tableCapacity;
rootVar["VisCacheParams"]["gBootThreshold"] = params.bootThreshold;
// ... etc
```
The VisCache pass exports per-member values via `InternalDictionary` keys
(`vhfParam_tableCapacity`, etc.) so downstream passes can read and bind them.

---

## 9. CMakeLists: FALCOR_FLAT_OUTPUT to skip $<CONFIG> subdirectory

**File:** `CMakeLists.txt` (line 206)

VS2022 multi-config builds append `/$<CONFIG>` (e.g. `/Release`) to the output
directory, splitting binaries from scripts/data which deploy to the root. Setting
`-DFALCOR_FLAT_OUTPUT=ON` skips the config suffix so all configs output directly
to `FALCOR_RUNTIME_OUTPUT_DIRECTORY`.

**Fix:** Guard the `$<CONFIG>` genex with `AND NOT FALCOR_FLAT_OUTPUT`.

**Upstream status:** Enhancement for flat output layouts.

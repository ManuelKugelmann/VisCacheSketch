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

## 3. GLFW: sccache fails to cache PDB when /Zi and /Z7 conflict

**File:** `external/CMakeLists.txt`

When using `sccache` as a compiler launcher with Ninja on MSVC, GLFW
compilation fails because sccache tries to zip up the PDB file specified
by `/Fd`, but no PDB is actually created. This happens when `/Z7` is
appended to flags that already contain `/Zi` — the compiler uses `/Z7`
(last wins, embeds debug info in `.obj`), but sccache still expects the
PDB that `/Fd` points to.

**Fix:** Before `add_subdirectory(glfw)`, replace `/Zi` with `/Z7` in
`CMAKE_C_FLAGS_DEBUG`, `CMAKE_CXX_FLAGS_DEBUG`, and their RelWithDebInfo
counterparts. The original flags are restored after `add_subdirectory()`
so other targets are unaffected.

**Upstream status:** Not yet reported (upstream GLFW doesn't use sccache).

---

## 4. CudaInterop: suppress C4100 and LNK4098 warnings on MSVC

**File:** `Source/Samples/CudaInterop/CMakeLists.txt`

CUDA separable compilation generates device-link registration files
(`tmpxft_*_CudaInterop.device-link.reg.c`) with an unused
`prelinked_fatbinc` parameter, triggering MSVC warning C4100. The CUDA
runtime also statically links LIBCMT, conflicting with Falcor's dynamic
CRT (MSVCRT), producing linker warning LNK4098.

**Fix:** Added MSVC-only compile/link options:

```cmake
target_compile_options(CudaInterop PRIVATE /wd4100)
target_link_options(CudaInterop PRIVATE /NODEFAULTLIB:LIBCMT)
```

**Upstream status:** Not yet reported.

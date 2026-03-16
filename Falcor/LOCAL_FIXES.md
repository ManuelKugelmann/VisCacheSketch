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

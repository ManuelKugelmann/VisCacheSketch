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

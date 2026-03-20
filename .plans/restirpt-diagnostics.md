# ReSTIR PT VisCache Diagnostics

## Status: planned

## Goal
Add VISCACHE_DIAGNOSTICS support to ReSTIRPTPass so heatmaps work with the production renderer, not just PathTracer.

## Pre-existing bugs (fixed)
- [x] `mVCParams` struct missing `diagAccumWindow` in all 4 renderers (read past struct end)
- [x] `var` instead of `rootVar` for `gDiagAccumWindow` binding in PathReusePass/PathRetracePass
- [x] `tracePass()` missing `gVHFTable` + VisCacheParams binding (crash when `USE_VISCACHE_LIGHTSELECTION=1`)

## Files to modify

### ReSTIRPTPass.h
- Add `bool mVisCacheDiagnostics = false;`
- Add 8 `ref<Texture>` members: `mpVCDiag`, `mpVCDiagError`, `mpVCVarMaturityLevel`, `mpVCVarMaturityMu`, `mpVCAccumSaved`, `mpVCAccumTotal`, `mpVCRaySavedRatio`, `mpVCNoise`

### ReSTIRPTPass.cpp

**Dict reads (after line ~1547, where mVisCacheDirDistAddr is read):**
- Read `vhfDiagEnabled` flag from dict
- Read all 8 texture dict keys into member pointers
- Add `mVisCacheDiagnostics != wasDiag` to recompile condition

**Shader defines (in StaticParams::getDefines(), after line ~1972):**
- Add `VISCACHE_DIAGNOSTICS=1` when `owner.mVisCacheDiagnostics` is true

**Texture binding in 3 dispatch sites:**
- `tracePass()` (~line 1673): bind 8 textures at root var level
- `PathReusePass()` (~line 1808): same, using `rootVar`
- `PathRetracePass()` (~line 1903): same, using `rootVar`

Pattern (same for all 3 sites):
```cpp
if (mVisCacheDiagnostics)
{
    if (mpVCDiag)           rootVar["gVCDiag"]           = mpVCDiag;
    if (mpVCDiagError)      rootVar["gVCDiagError"]      = mpVCDiagError;
    if (mpVCVarMaturityLevel) rootVar["gVCVarMaturityLevel"] = mpVCVarMaturityLevel;
    if (mpVCVarMaturityMu)  rootVar["gVCVarMaturityMu"]  = mpVCVarMaturityMu;
    if (mpVCAccumSaved)     rootVar["gVCAccumSaved"]     = mpVCAccumSaved;
    if (mpVCAccumTotal)     rootVar["gVCAccumTotal"]      = mpVCAccumTotal;
    if (mpVCRaySavedRatio)  rootVar["gVCRaySavedRatio"]  = mpVCRaySavedRatio;
    if (mpVCNoise)          rootVar["gVCNoise"]          = mpVCNoise;
}
```

### ReSTIRPTPass/PathTracer.slang

**Import (after existing `import RenderPasses.VisCache.VisCache;` ~line 34):**
```slang
#ifdef VISCACHE_DIAGNOSTICS
import RenderPasses.VisCache.VisCacheDiagnostics;
#endif
```

**vcWriteDiag call at NEE shadow ray site (~line 1364-1378):**
- Only for bounce 0 (`path.getVertexIndex() <= 1`)
- After the existing vhfGate/vhfCommit block
- Guard with `#ifdef VISCACHE_DIAGNOSTICS`

## Scope limitation
Only the NEE shadow ray site in `PathTracer.slang` gets diagnostic calls (pixel coords available via `path.getPixel()`). The reconnection visibility in `Shift.slang` would need `uint2 pixel` threaded through `evalSegmentVisibilityWeight` → `computeShiftedIntegrandReconnection` → `computeShiftedIntegrand_` → `computeShiftedIntegrand` and all callers in 5 compute shaders. Deferred.

## Reference implementation
`Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp` lines 1244-1265, 1441-1451, 1548.

# VisCache Integration Summary

How VisCache integrates with each Falcor 8.0 renderer. All paths relative to repo root.

## Architecture

VisCache is an **upstream render pass** that exports GPU resources via `InternalDictionary`.
Downstream renderers read those resources, set compile-time defines, and bind buffers.
VisCache `.slang` modules **self-guard** with `#if USE_VISCACHE` internally, so consumer
passes import them unconditionally — zero `#if` guards at import sites.

```
  VisCache pass (upstream)
      |
      |-- dict["vhfTable"]              RWStructuredBuffer<VHFEntry>
      |-- dict["vhfParamsCB"]           cbuffer VisCacheParams (32 bytes)
      |-- dict["vhfEnableVisibilityCheck"]   bool
      |-- dict["vhfEnableLightSelection"]    bool
      v
  Renderer pass (downstream)
      |-- reads dict, sets defines, binds resources
      |-- shaders import VisCache modules unconditionally
```

## Compile-Time Defines

| Define | Scope | Purpose |
|--------|-------|---------|
| `USE_VISCACHE` | All renderers | Hash table buffer available; gates all VisCache code in self-guarding modules |
| `USE_VISCACHE_VISIBILITYCHECK` | All renderers | CV+RRR gating for shadow rays and point-to-point connections |
| `USE_VISCACHE_LIGHTSELECTION` | ReSTIR PT only | Cached mu biases NEE light candidate selection (unbiased RIS) |
| `USE_LOCAL_CVRRR` | ReSTIR PT only | Ablation: reservoir-local CV+RRR without hash table |

Implies: `USE_VISCACHE_VISIBILITYCHECK` => `USE_VISCACHE` (host logic ensures this).

## GPU Resources

### VisCacheParams cbuffer (32 bytes)

```
uint  tableCapacity     Power-of-two entry count
uint  bootThreshold     Min samples before trusting entry
float varThreshold      Bernoulli variance gate for write depth
float pMin              Min RR survival probability
float fireflyBudget     Contribution scale for adaptive pMin
uint  numLevels         Number of LOD levels in cascade
float cellCoarse        Coarsest level cell size (world units)
float cellFine          Finest level cell size (world units)
```

### Hash Table

`RWStructuredBuffer<VHFEntry> gVHFTable` — flat N-level spatial hash table.
Each `VHFEntry` is 8 bytes: `[fingerprint:32 | vis_count:16 | total_count:16]`.

## Core Shader API (`VisCache.slang`)

Two-phase pattern used by all renderers:

```slang
// Phase 1: lookup + RR decision
VHFGateResult g = vhfGate(posA, posB, xi);

if (g.shouldTrace)
{
    float V = traceRay(...);          // Only trace when cache says so
    vhfCommit(posA, posB, V, g);      // Phase 2: update cache + compute CV weight
    visWeight = g.visWeight;          // Unbiased CV+RRR estimate
}
else
{
    visWeight = g.visWeight;          // Cache confident — use cached mu
}
```

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `vhfGate(posA, posB, xi)` | VisCache.slang | Phase 1: cascade lookup + RR decision |
| `vhfCommit(posA, posB, V, gate)` | VisCache.slang | Phase 2: cascade write + weight |
| `vhfLookup(posA, posB)` | VisCache.slang | Read-only lookup (no RR) |
| `vhfDeterministicXi(posA, posB)` | VisCache.slang | Position-derived xi (no rng needed) |
| `vhfGateDeterministic(posA, posB, contrib)` | VisCache.slang | Gate with deterministic xi + firefly budget |
| `vhfEncodeDirection(dir)` | VisCache.slang | Encode far-field direction as position |

### Higher-Level Wrappers

| Function | File | Used By |
|----------|------|---------|
| `vcVisibility_DirDist(origin, dir, dist, sg)` | VisCacheTracing.slang | MinimalPathTracer |
| `vcVisibility_Ray<AlphaTest>(ray, sg)` | VisCacheTracing.slang | PathTracer |
| `vcVisibility_InlineRay(origin, dir, dist, sg, lum)` | VisCacheTracing.slang | RTXDIPass |
| `evalRevalidationCV(P, Q, bsdf, Lo, G, sg)` | ShadingCV.slang | ReSTIR PT (revalidation) |
| `evalDirectLightingCV(...)` | ShadingCV.slang | ReSTIR PT (NEE) |
| `vhfLightSelectionWeight(P, Q)` | ShadingCV.slang | ReSTIR PT (light selection) |
| `evaluateVisibility(P, Q, ..., sg)` | RevalidationCommon.slang | ReSTIR PT (3-way dispatcher) |
| `evalLocalCVRRR(P, Q, ..., sg)` | RevalidationCommon.slang | ReSTIR PT (ablation baseline) |

## Per-Renderer Integration

---

### 1. MinimalPathTracer

**Files:**
- `Falcor/Source/RenderPasses/MinimalPathTracer/MinimalPathTracer.cpp` — dict read, defines, binding
- `Falcor/Source/RenderPasses/MinimalPathTracer/MinimalPathTracer.h` — member variables
- `Falcor/Source/RenderPasses/MinimalPathTracer/MinimalPathTracer.rt.slang` — shader usage

**Host (`.cpp`):**
```cpp
// Read dict
mpVHFTable    = dict["vhfTable"];
mpVHFParamsCB = dict["vhfParamsCB"];
mVisCacheAvailable = (mpVHFTable && mpVHFParamsCB);
mVisCacheVisibilityCheck = mVisCacheAvailable && dict["vhfEnableVisibilityCheck"];

// Set defines
addDefine("USE_VISCACHE", mVisCacheAvailable ? "1" : "0");
addDefine("USE_VISCACHE_VISIBILITYCHECK", mVisCacheVisibilityCheck ? "1" : "0");

// Bind resources
rootVar["gVHFTable"]      = mpVHFTable;
rootVar["VisCacheParams"] = mpVHFParamsCB;
```

**Shader (`.rt.slang`):**
```slang
import RenderPasses.VisCache.VisCacheTracing;  // unconditional (self-guarding)

#if USE_VISCACHE_VISIBILITYCHECK
    float visWeight = vcVisibility_DirDist(origin, dir, distance, sg);
#else
    float visWeight = traceShadowRay(...) ? 1.f : 0.f;
#endif
```

**Coverage:** All NEE shadow rays.

---

### 2. PathTracer

**Files:**
- `Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp` — dict read, defines, binding
- `Falcor/Source/RenderPasses/PathTracer/PathTracer.h` — member variables
- `Falcor/Source/RenderPasses/PathTracer/TracePass.rt.slang` — callback definition
- `Falcor/Source/RenderPasses/PathTracer/PathTracer.slang` — call sites

**Host (`.cpp`):**
Same dict/define/binding pattern as MinimalPathTracer.

**Shader — callback (`TracePass.rt.slang`):**
```slang
import RenderPasses.VisCache.VisCacheTracing;

#if USE_VISCACHE_VISIBILITYCHECK
float traceVisibilityRayCV(const Ray ray, inout SampleGenerator sg)
{
    return vcVisibility_Ray<kUseAlphaTest>(ray, sg);
}
#endif
```

**Shader — call site (`PathTracer.slang`):**
```slang
#if USE_VISCACHE_VISIBILITYCHECK
    float visWeight = traceVisibilityRayCV(shadowRay, sg);
#else
    bool visible = traceVisibilityRay(shadowRay);
#endif
```

**Coverage:** All NEE shadow rays (multi-bounce).

---

### 3. RTXDIPass (ReSTIR DI)

**Files:**
- `Falcor/Source/RenderPasses/RTXDIPass/RTXDIPass.cpp` — dict read, defines, extra propagation
- `Falcor/Source/RenderPasses/RTXDIPass/RTXDIPass.h` — member variables
- `Falcor/Source/RenderPasses/RTXDIPass/FinalShading.cs.slang` — final visibility check
- `Falcor/Source/Falcor/Rendering/RTXDI/RTXDI.h` — `setExtraDefines()`, `setExtraBindings()`
- `Falcor/Source/Falcor/Rendering/RTXDI/RTXDI.cpp` — internal pass define/binding injection
- `Falcor/Source/Falcor/Rendering/RTXDI/RTXDIApplicationBridge.slangh` — `RAB_GetConservativeVisibility`

**Host — FinalShadingPass (`RTXDIPass.cpp`):**
Same dict/define/binding pattern. Defines set on `mpFinalShadingPass`.

**Host — RTXDI internal passes (`RTXDIPass.cpp`):**
```cpp
// Propagate to RTXDI's internal passes (testCandidateVisibility,
// spatial/temporal/spatiotemporal resampling)
DefineList visCacheDefines;
visCacheDefines.add("USE_VISCACHE", mVisCacheAvailable ? "1" : "0");
visCacheDefines.add("USE_VISCACHE_VISIBILITYCHECK", mVisCacheVisibilityCheck ? "1" : "0");
mpRTXDI->setExtraDefines(visCacheDefines);

mpRTXDI->setExtraBindings([vhfTable, vhfParams](const ShaderVar& rootVar) {
    rootVar["gVHFTable"]      = vhfTable;
    rootVar["VisCacheParams"] = vhfParams;
});
```

**RTXDI module (`RTXDI.h/cpp`):** `setExtraDefines()` triggers shader recompilation;
`setExtraBindings()` callback invoked in `bindShaderDataInternal()` for all internal passes.

**Shader — final shading (`FinalShading.cs.slang`):**
```slang
import RenderPasses.VisCache.VisCacheTracing;

#if USE_VISCACHE_VISIBILITYCHECK
    visWeight = vcVisibility_InlineRay(origin, dir, distance, sg, luminance(Li));
#else
    if (!rayQuery.traceVisibilityRay(ray)) { valid = false; }
#endif
```

**Shader — RTXDI bridge callback (`RTXDIApplicationBridge.slangh`):**
```slang
import RenderPasses.VisCache.VisCache;

bool RAB_GetConservativeVisibility(RAB_Surface surface, RAB_LightSample lightSample)
{
#if USE_VISCACHE_VISIBILITYCHECK
    float xi = vhfDeterministicXi(posA, posB);       // No rng needed
    VHFGateResult g = vhfGate(posA, posB, xi);
    if (!g.shouldTrace) {
        float resolveXi = frac(xi + 0.5f);           // Decorrelated
        return resolveXi < g.visWeight;               // Stochastic bool
    }
    bool visible = rayQuery.traceVisibilityRay(ray, RAY_FLAG_CULL_NON_OPAQUE);
    vhfCommit(posA, posB, visible ? 1.f : 0.f, g);
    return visible;
#else
    return rayQuery.traceVisibilityRay(ray, RAY_FLAG_CULL_NON_OPAQUE);
#endif
}
```

Note: `RAB_GetConservativeVisibility` returns `bool` (SDK constraint). The soft CV+RRR
weight is resolved to `bool` stochastically: `xi < mu` is unbiased in expectation.
Deterministic xi from cell coordinates provides temporal stability across resampling passes.

**Coverage:** All RTXDI visibility — candidate testing, spatial/temporal resampling, final shading.

---

### 4. ReSTIR PT (ReSTIRPTPass)

**Files:**
- `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp` — dict read, defines, binding
- `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.h` — member variables
- `Source/RenderPasses/ReSTIRPTPass/Shift.slang` — reconnection visibility
- `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang` — NEE light selection

**Host (`.cpp`):**
Sets three defines (most of any renderer):
```cpp
defines.add("USE_VISCACHE", mVisCacheAvailable ? "1" : "0");
defines.add("USE_VISCACHE_VISIBILITYCHECK", mVisCacheVisibilityCheck ? "1" : "0");
defines.add("USE_VISCACHE_LIGHTSELECTION", mVisCacheLightSelection ? "1" : "0");
defines.add("USE_LOCAL_CVRRR", mLocalCVRRR ? "1" : "0");
```

**Shader — reconnection shifts (`Shift.slang`):**

Uses the 3-way dispatcher from `RevalidationCommon.slang`:

```slang
import RenderPasses.VisCache.RevalidationCommon;

// evaluateVisibility() dispatches to:
//   USE_VISCACHE_VISIBILITYCHECK  -> evalRevalidationCV()    (hash table CV+RRR)
//   USE_LOCAL_CVRRR               -> evalLocalCVRRR()        (reservoir-local, no hash table)
//   neither                       -> traceShadowRay()        (vanilla baseline)
float vis = evaluateVisibility(P, Q, bsdf, Lo, G, neighborTargetPdf, pHatNoVis, camPos, sg);
```

**Shader — NEE light selection (`PathTracer.slang`):**
```slang
#if USE_VISCACHE_LIGHTSELECTION
    float selW = vhfLightSelectionWeight(origin, lightPos);
    // Bias NEE candidate selection toward visible lights
#endif
```

**Coverage:** Reconnection visibility (spatial/temporal reuse), NEE shadow rays, light selection.

---

## 3-Way Dispatcher (`RevalidationCommon.slang`)

Single entry point for all ReSTIR spatial/temporal reuse visibility:

```
evaluateVisibility(P, Q, bsdf, Lo, G, neighborTargetPdf, pHatNoVis, camPos, sg)
    |
    |-- USE_VISCACHE_VISIBILITYCHECK --> evalRevalidationCV(P, Q, bsdf, Lo, G, sg)
    |   Hash table CV+RRR. Best ray savings (spatial sharing across all pixels).
    |
    |-- USE_LOCAL_CVRRR --> evalLocalCVRRR(P, Q, bsdf, Lo, G, neighborTargetPdf, pHatNoVis, sg)
    |   Reservoir-local CV+RRR. No hash table. Ablation baseline.
    |   mu = clamp(neighborTargetPdf / pHatNoVis, 0, 1)
    |   Reuses gPMin/gFireflyBudget from VisCacheParams for fair A/B comparison.
    |
    |-- neither --> traceShadowRay(P, Q)
        Vanilla unconditional shadow ray. Baseline for measuring ray savings.
```

## Graph Scripts

Vanilla graph scripts accept `viscache=True` to add the VisCache pass (no code duplication):

| Renderer | Vanilla Script | VisCache Wrapper |
|----------|---------------|-----------------|
| MinimalPathTracer | `MinimalPathTracer_Graph.py` | `MinimalPathTracer_VisCache_Graph.py` |
| PathTracer | `PathTracer_Graph.py` | `PathTracer_VisCache_Graph.py` |
| RTXDI | `RTXDI_Graph.py` | `RTXDI_VisCache_Graph.py` |
| ReSTIR PT | `ReSTIRPT_Graph.py` | `ReSTIRPT_VisCache_Graph.py` |

Shared defaults in `viscache_defaults.py`. Ablation presets in `ReSTIRPT_Graph.py`.

## Ablation Switches

### Feature Toggles (downstream renderers)

These are **compile-time shader defines** set by downstream renderers. Toggling any
of these triggers shader recompilation. They control which VisCache features are active
in the rendering shaders.

| Define | Property Key (dict) | Default | Scope | Paper Section |
|--------|-------------------|---------|-------|---------------|
| `USE_VISCACHE` | (derived from buffer presence) | auto | All renderers | -- |
| `USE_VISCACHE_VISIBILITYCHECK` | `vhfEnableVisibilityCheck` | true | All renderers | S12 |
| `USE_VISCACHE_LIGHTSELECTION` | `vhfEnableLightSelection` | true | ReSTIR PT only | S11.1 |
| `USE_LOCAL_CVRRR` | (ReSTIRPTPass member) | false | ReSTIR PT only | Ablation A |

`USE_LOCAL_CVRRR` is the "no hash table" ablation baseline — uses reservoir-local
visibility estimate (`mu = clamp(targetPdf / pHatNoVis, 0, 1)`) instead of the hash
table. Reuses `gPMin` / `gFireflyBudget` from `VisCacheParams` for fair A/B comparison.

### Internal Ablation Toggles (VisCache pass)

These are **runtime host-side** toggles on the VisCache pass itself. They do NOT
trigger shader recompilation — the host skips dispatches or changes parameters.
All are set via `createPass("VisCachePass", {...})` properties and exposed in the GUI
under the "Ablations" group.

| Toggle | Property Key | Default | Paper | Effect When Disabled |
|--------|-------------|---------|-------|---------------------|
| B: Variance gate | `enableVisCacheVarianceGate` | true | -B | All inserts go to finest level only (no variance-gated depth selection) |
| C: Warp reduction | `enableVisCacheWarpReduction` | true | -C | Per-lane atomics instead of SM 6.5 WaveMatch coalescing |
| D: Decay sweep | `enableVisCacheDecay` | true | -D | No background decay — stale entries persist indefinitely |
| E: Pressure eviction | `enableVisCachePressureEvict` | true | -E | No pressure-scaled eviction during probe — cold entries never evicted |

### Ablation Presets (Graph Scripts)

`scripts/ReSTIRPT_Graph.py` defines named presets:

```python
ABLATIONS = {
    "minus_var":    {"enableVisCacheVarianceGate": False},    # -B
    "minus_warp":   {"enableVisCacheWarpReduction": False},   # -C
    "minus_decay":  {"enableVisCacheDecay": False},           # -D
    "minus_evict":  {"enableVisCachePressureEvict": False},   # -E
}

# Usage:
render_graph_ReSTIRPT(viscache=True, ablation="minus_decay")
```

`scripts/VisCache_Ablation.py` runs all ablation configs automatically for paper figures.
`scripts/VisCache_Heatmaps.py` captures diagnostic heatmaps crossed with ablation configs.

### Test Coverage

`tests/test_paper_ablations.py` (17 tests, no GPU required) validates:
- Toggle consistency across DI/GI/PT property keys
- All toggle combinations are valid
- Light-selection-only ablation (S11.1 without S11.3)
- Property round-trip for all 4 internal toggles (B-E)
- Decay-off semantics
- LOCAL_CVRRR ablation design

## CV+RRR Estimator

All paths use the same unbiased control variate + Russian roulette estimator:

```
E[mu + (V - mu) / p] = E[V]     for any p in (0, 1]
```

- `mu`: cached visibility estimate (from hash table or reservoir)
- `V`: actual visibility (0 or 1, traced when RR fires)
- `p`: survival probability, scaled by contribution to suppress fireflies

When `p = 1`: always trace (warmup / high-variance).
When `shouldTrace = false`: skip ray entirely, return `mu`.

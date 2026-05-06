# ReSTIRPTPass — historical commentary moved out of source

Per the cleanliness pass on 2026-05-06, source-code comments that referenced past
attempts, ladder-step result numbers, or `§N`-tagged backport history were
extracted from the source files and consolidated here. The remaining inline
comments are purely technical (what the code does + algorithm references).

The §-numbering convention (§1 NVlabs Inf/NaN guard, §5 NVlabs `nearFieldDistance`,
§12 #1 Lin-2026 footprint, §15 fireflyClampK soft-clamp, etc.) lives in
[`Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md`](../../Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md).
Each `§N` cited here points back to the same anchor in PORT_NOTES.md.

---

## Path-tracer body (`PathTracer.slang`)

### §12 #1 Lin 2026 footprint criterion (PathTracer.slang nextVertex)

The reconnection-vertex selection logic uses Lin et al. 2026 "ReSTIR PT
Enhanced" §4 footprint-based reconnection criterion:

  `1 / (p_{k-1} · G(x_{k-1}→x_k)) ≥ c · R_pri²`

with `c = 0.02` (paper-suggested, ablation-robust). `R_pri²` is the primary-hit
ray-cone footprint area (`||x0 − x1||² · cos(θ) / (4π)`), computed once at
the primary hit and stashed on `PathState.pathPrimaryFootprint2`. Replaces
DQLin's hand-tuned `nearFieldDistance × sceneRadius` distance test. Sites:
`PathTracer.slang::nextVertex` (two rcVertex selection sites),
`Shift.slang::computeShiftedIntegrandReconnection`.

### §12 #2 Lin 2026 RR-skip-during-replay

`terminatePathByRussianRoulette` early-returns when `path.enableRandomReplay`
is set. Without this, RR fires during replay paths and biases the resampler
toward shorter surviving paths. Lin 2026 §6.2.4 fix.

### §14 ADRRS scaffold (excised 2026-05-06)

PathState had `adrrsSplitHit/Origin/Dir/Thp/SgState/Length/QueueDepth`
fields and TracePass.cs.slang carried a `walkPathReplica` function plus a
drain loop. Capture hook fired AFTER `handleHit`, so the replica double-
counted the split-vertex's emission/NEE — biased. Correct hook needs a
path-walk-loop refactor (capture state BEFORE handleHit at the split vertex).
Excised from the reference; see PORT_NOTES.md §Future additions for the
re-implementation plan in `restirpt_2d/3d` ports.

---

## Reservoir merges (`PathReservoir.slang`)

### §10 magnitude clamps (retired)

DQLin's reservoir-merge weight clamps used a hybrid drop+clamp on `w`:
- `w > 1e2` → drop (M increments, weight skipped) — actively biased the
  selection; was diagnosed during the now-known-broken Sponza experiments
- `M ≥ 2 && w > 100 × this.weight` → clamp (relative-firefly cap)

Threshold sweep on the broken harness:
- abs=1e1: Cornell −4% / −10%, Sponza +326%
- abs=1e2: Cornell +0.14% / −1.85%, Sponza +2658%   ← chosen at the time
- abs=1e3: Cornell +3.3% / −0.02%, Sponza +19k%
- abs=1e4: Cornell +3.5% / +0.3%, Sponza +132k%

The Sponza numbers above are now known to be from the wrong-camera + wrong-GT
+ stale-cache harness (RPT00 fixed all three). The clamp's motivation was
chasing what turned out to be infrastructure bias, not algorithmic. Retired
on 2026-05-06; `add` / `merge` / `mergeWithResamplingMIS` carry only the
standard NaN/Inf/zero guard.

### §13 magnitude safety net at writeback

`if (weight < 0 || isnan(weight) || isinf(weight) || weight > 1e10) weight = 0`
at the reservoir-buffer-write boundary in TemporalReuse + SpatialReuse +
PathTracer::writeOutput. Also `F` zeroed when any channel is non-finite or
> 1e10. This is the last defensive boundary against the multi-frame static-
scene accumulation that the dynamic-scene-assumption ReSTIR PT was not
designed for.

---

## Output-stage soft-clamp (`TemporalReuse.cs.slang`, `SpatialReuse.cs.slang`)

### §15 fireflyClampK chroma-preserving soft-clamp

Replaces an earlier "hard fallback to directLighting on outlier" approach
that discarded legitimate indirect on indirect-dominated scenes. The current
form:

```
if (colorLum > params.fireflyClampK × max-channel(DL))
    color *= ceiling / colorLum;     // preserve chroma direction
```

Calibrated 2026-05-06 via the RPT01 ladder K-sweep on Cornell + Sponza:

| K | Cornell mean_err x1 | Sponza mean_err x4 | Cornell RMSE x1 |
|---:|---:|---:|---:|
| 30 (legacy) | 4.38 | 15.59 | 0.692 |
| 100 | 3.85 | 11.67 | 0.741 |
| **1000 (new default)** | **3.79** | **9.62** | 0.759 |
| ∞ (no clamp) | 3.79 | 9.61 | 0.816 |
| vanilla baseline | 6.36 | 11.50 | 0.804 |

K=30 was clipping legitimate Sponza indirect for ~6pp mean_err penalty.
K=1000 captures ~99% of K=∞'s mean_err benefit while still catching the
rare Cornell fireflies (RMSE 0.759 vs 0.816 at K=∞).

Comparison with RTXDI BoilingFilter: same intent (firefly suppression via
local-reference comparison), different mechanism — BoilingFilter compares
against spatial-neighbor mean and hard-drops; §15 compares against
per-pixel DL and soft-clamps preserving chroma direction. A spatial-
neighbor BoilingFilter analogue for path reservoirs is a candidate for
the `restirpt_2d/3d` ports.

---

## Build / API (`ReSTIRPTPass.cpp`, `ReSTIRPTPass.h`)

### `rejectShiftBasedOnJacobian` + `temporalUpdateForDynamicScene`

Both are derived from `mpScene->hasAnimation() && mpScene->isAnimated()`
in `setScene()`. This matches DQLin's defaults exactly. We tested forcing
them on for static scenes; neither reduced firefly count, and unconditional
`rejectShiftBasedOnJacobian=true` catastrophically broke the unsupported
`DI=false` config (0 → 57k Infs).

### Configuration support matrix

Verified on `CornellBox_1AreaLight` at 40-frame accumulation:

| Configuration                                                    | Status        | Notes                                            |
|------------------------------------------------------------------|---------------|--------------------------------------------------|
| ReSTIR mode + `disableDirectIllumination=true` + RTXDI feed      | ✅ DQLin canonical | Reference. RPT00 + RPT01 calibrated. |
| ReSTIR mode + `disableDirectIllumination=false` (no RTXDI feed)  | ❌ unsupported | Direct-light samples flow through GRIS shift; near-grazing reconnections produce ~57k Inf pixels. |
| PT-mode + `disableDirectIllumination=false`                      | debug only    | Matches vanilla PathTracer within 1.7% energy, 0 Infs, but bypasses GRIS resampling. |

### `pathThpMax` retired (was §8)

`PathBuilder::addEscapeVertex/addNeeVertex` previously clamped `pathWeight`
at `params.pathThpMax = 1e4` to bound 1/pdf chain growth. Retired with §10
once the harness was rooted out. The slot in `Params.slang::_retiredField0`
is kept for cbuffer ABI stability; remove in next ABI-breaking pass.

### `mReservoirResetPeriod` retired (was §9)

Periodic reservoir reset to amortize static-scene weight drift. Workaround
for the §10 clamps' M-vs-weight skew; with §10 retired the drift goes away.
C++ member retained out of habit; safe to drop in a future pass.

### `fireflyFilterThreshold` / `pathBuilder.fireflyFilterK` retired (was §11)

RTXPT-style adaptive K decay through BSDF-PDF chain. Implemented + retired:
the helper code (`fireflyFilter`, `computeNewScatterFireflyFilterK`,
`computeRayConeSpreadAngleExpansionByScatterPDF`) added complexity in
`Falcor8Compat.slang`, plumbing in PathBuilder, and a knob in Params, but
showed no measurable gain on Cornell/Sponza/32PL after the harness fixes.
The slot in `Params.slang::_retiredField1` was repurposed to `fireflyClampK`.

---

## Sources / repository pointers

| Repository                              | Falcor version | Path in this repo                                |
|-----------------------------------------|----------------|--------------------------------------------------|
| `DQLin_ReSTIR_PT`                       | 4.x            | `refs/DQLin_ReSTIR_PT/Source/RenderPasses/ReSTIRPTPass/` |
| `NVlabs_conditional_ReSTIR`             | 6.x            | `refs/NVlabs_conditional_ReSTIR/Source/Falcor/Rendering/ConditionalReSTIR/` |
| Lin et al. 2026 "ReSTIR PT Enhanced"    | paper text     | `docs/references/Lin2026_*.pdf` (no public code) |
| `NVIDIAGameWorks_RTXPT` (FireflyFilter) | reference      | `refs/NVIDIAGameWorks_RTXPT/Rtxpt/Shaders/PathTracer/PathTracerHelpers.hlsli` |

DQLin = algorithmic reference. NVlabs = Falcor-version-closer-to-us robustness
guards (§1-§7 of PORT_NOTES.md). Lin 2026 = paper-text-only backports (§12 #1
+ #2 implemented; #3 #4 + Stage A excised, see PORT_NOTES.md Future additions).

# ReSTIRPTPass — Falcor 4 → Falcor 8 Port Notes

A reference port of [DQLin's ReSTIR PT](https://github.com/DQLin/ReSTIR_PT)
from Falcor 4 to Falcor 8, with a small set of conservative safety guards
backported from NVIDIA's
[NVlabs/conditional-restir-prototype](https://github.com/NVlabs/conditional-restir-prototype)
(Falcor 6) and Lin et al. 2026 paper-text backports.

## What's in this reference (TL;DR)

The reference exercises **DQLin's full GRIS resampling pipeline** (canonical
ReSTIR mode + RTXDI direct-light feed, as `disableDirectIllumination=true`).
Validated end-to-end via Ladder step 00 at b ∈ {1, 4, 8} on Cornell + Sponza
(Ladder00 calls `run_baseline_reference_restirpt` natively; the standalone
`RPT00` step is a focused alias for ReSTIRPT-only iteration):

| scene · b · spp | metric | vanilla | restirpt | Δ |
|---|---|---:|---:|---:|
| Cornell_1AL b4 x1 | mean_err% | 6.36 | **3.79** | **−40%** |
| Cornell_32PL b4 x1 | RMSE | 0.755 | **0.605** | **−20%** |
| Cornell_32PL b4 x1 | PSNR dB | 46.79 | **48.72** | **+1.9** |
| Sponza b4 x1 | RMSE | 1.694 | **0.768** | **−55%** |
| Sponza b4 x1 | PSNR dB | 13.02 | **19.89** | **+6.9** |
| Sponza b4 x4 | RMSE | 0.845 | **0.684** | **−19%** |

Restirpt outperforms vanilla path-tracing at low SPP almost everywhere. Honest
exception: **Cornell_32PL b4 x4 RMSE** is +24% (0.926 vs 0.749) — without §15
firefly defense, the dense-point-light scene at 4 SPP has rare bright pixels
that vanilla averages out. Single-SPP and other SPPs / scenes are restirpt
wins. See `LADDERLOG.md` step 00 for the full table.

### Components included

| component | source | section below |
|---|---|---|
| GRIS resampling (canonical/temporal/spatial) | DQLin | (algorithm body) |
| Hybrid + reconnection shift | DQLin | (algorithm body) |
| `isIntegrandInvalid` Inf/NaN guards on shifted integrand | NVlabs F6 | §1 |
| `evalBsdfAndPdf` un-normalized partial PDF | NVlabs F6 | §2 |
| `isinf(w)` in reservoir merges | NVlabs F6 | §3 |
| Color guard before unconditional accumulation | NVlabs F6 | §4 |
| Scene-relative `nearFieldDistance` (×sceneRadius) | NVlabs F6 | §5 |
| Reservoir validity guards at write sites | this work | §6 |
| `finalizeRIS`/`finalizeGRIS` post-division re-guard | this work | §7 |
| Lin 2026 §4 footprint-based reconnection criterion | Lin 2026 | §12 #1 |
| Lin 2026 §6.2.4 RR-skip-during-replay | Lin 2026 | §12 #2 |
| Lin 2026 §6.3 vector-valued resampling weights (chroma noise reduction) | Lin 2026 | §12 #4 |

### Components present but disabled by default

Same status as the RTXDI BoilingFilter port — code present, default off,
opt-in via graph kwarg. Reference rendering uses the algorithm without them.

| component | knob | re-engage by |
|---|---|---|
| §15 chroma-preserving soft-clamp `K × max-channel(DL)` | `params.fireflyClampK` (default `1e9` ≡ disabled) | `render_graph_ReSTIRPT(fireflyClampK=1000)` |

### Components excised (moved to "Future additions")

These were attempted, reverted, or left as dead scaffolding. Removed from
the reference to keep it minimal and bug-for-bug-faithful to DQLin. The
forward implementation lives in our `restirpt_2d` / `restirpt_3d`
PathTracer-based ports (not in this reference). See [§Future additions](#future-additions)
for design + state per item.

- §8 path-throughput clamp (`pathThpMax`) — supplanted by §11+§12+§15
- §9 periodic reservoir reset — workaround for an indirectly-fixed problem
- §10 merge-time absolute+relative gates — clamps were biasing samples
- §11 RTXPT-style `FireflyFilter K` — heavy machinery, value unproven on our scenes
- §12 #3 forced NEE light reconnection (Lin 2026 §6.2.3) — not implemented (performance optimization, deferred)
- Stage A unification (Lin 2026 §5 supplemental) — needs ω_1 multi-sample MIS
- §14 ADRRS-without-adjoint splitting — capture hook AFTER handleHit double-counts; needs path-walk refactor

### Calibration knobs

| knob | default | role | source |
|---|---|---|---|
| `params.fireflyClampK` | `1e9` (off) | §15 ceiling when engaged | RPT01 K-sweep — see below |
| `params.specularRoughnessThreshold` | `0.2` | DQLin local-strategy roughness gate | DQLin upstream |
| `params.nearFieldDistance` | `0.03` (× sceneRadius) | NVlabs F6 reconnection gate | NVlabs F6 upstream |

`fireflyClampK` is added by this port and disabled by default. RPT01 ladder
K-sweep (b=4, vs `vanilla_b4_x4096`, lower is better) calibrates it for
opt-in use:

| K | Cornell mean_err x1 | Sponza mean_err x4 | Cornell RMSE x1 |
|---|---:|---:|---:|
| 30 | 4.38 | 15.59 | **0.692** |
| 100 | 3.85 | 11.67 | 0.741 |
| 1000 | **3.79** | **9.62** | 0.759 |
| **∞ (default off)** | **3.79** | **9.61** | 0.816 |
| vanilla baseline | 6.36 | 11.50 | 0.804 |

The reference uses K=∞ (off). Restirpt beats vanilla on every metric except
Cornell RMSE +1.5%. If a downstream consumer wants to claw back that RMSE,
engage K=1000 via `render_graph_ReSTIRPT(fireflyClampK=1000)`.

## Sources

| Repository                              | Falcor version | Path in this repo                                |
|-----------------------------------------|----------------|--------------------------------------------------|
| `DQLin_ReSTIR_PT`                       | 4.x            | `refs/DQLin_ReSTIR_PT/Source/RenderPasses/ReSTIRPTPass/` |
| `NVlabs_conditional_ReSTIR`             | 6.x            | `refs/NVlabs_conditional_ReSTIR/Source/Falcor/Rendering/ConditionalReSTIR/` |
| Lin et al. 2026 "ReSTIR PT Enhanced"    | paper text     | `docs/references/Lin2026_*.pdf` (no public code) |
| **Our port (Falcor 8)**                 | 8.0            | `Source/RenderPasses/ReSTIRPTPass/`              |

DQLin is the algorithmic reference. NVlabs is closer in time to Falcor 8 and
has already addressed several robustness issues DQLin's release left open.
Lin 2026 contributions (§12) are paper-text backports — Lin/Kettunen kept the
Enhanced features private; we re-derived from §4 and §6.

## Falcor 4 → Falcor 8 API adaptations

These are mechanical translations — no algorithmic change. Each site is
commented inline with a `[Falcor 8]` tag in the source.

| Area                          | Falcor 4 (DQLin)                         | Falcor 8 (this port)                                |
|-------------------------------|------------------------------------------|-----------------------------------------------------|
| Plugin registration           | `getPasses` / `getProjDir`               | `registerPlugin(PluginRegistry&)`                   |
| Buffer creation               | `Buffer::create(...)`                    | `mpDevice->createBuffer(...)`                       |
| Sample generator              | `SampleGenerator::create(type)`          | `SampleGenerator::create(mpDevice, type)`           |
| Asset resolution              | `findFileInDataDirectories`              | `AssetResolver`                                     |
| Material API                  | `import Rendering.Materials.MaterialShading` (free functions) | `Scene.Material.MaterialFactory.getMaterialInstance(...)` (interface) |
| BSDF sampling result          | `BSDFSample::wi` (Falcor 4 convention)   | `BSDFSample::wo` (Falcor 8 convention) — see `Falcor8Compat.slang` |
| Lobe flags                    | `SampledBSDFFlags::DiffR\|DiffT` (0x3) etc. | `LobeType::Diffuse` (0x11), `LobeType::SpecularOrDelta` (0x66) — Falcor 8 splits delta lobes from specular |
| BSDF lobe enumeration         | `getBSDFLobes(sd)`                       | `IMaterialInstance.getLobeTypes(sd)` — see `PathTracer.slang::getBSDFLobes` shim |
| Per-lobe BSDF PDF             | `bsdf.setActiveLobes(...)` then `bsdf.evalPdf(...)` | `mi.evalBsdfAndPdf(sd, wi, sg, lobeMask, pdfSingle, pdfAll)` — see `Falcor8Compat.slang::evalPdfBSDF`. **This is also an NVlabs algorithmic backport**: DQLin's `setActiveLobes` path renormalizes within the active subset, but ReSTIR PT shift Jacobians need *un-normalized* partial PDFs. NVlabs's `evalBsdfAndPdf` returns exactly that. |
| Roughness                     | `sd.linearRoughness`                     | `BSDFProperties.roughness` via `getRoughness(sd)` shim in `Falcor8Compat.slang` |
| Emission                      | `sd.emission`                            | `BSDFProperties.emission` (no longer on `ShadingData`) |
| IoR                           | `sd.eta` (relative)                      | `sd.IoR` (outside-medium absolute)                  |
| Specular transmission flag    | `sd.specularTransmission`                | Test lobe types via `IMaterialInstance.getLobeTypes` |
| Hit info construction         | `HitInfo h; h.unpack(packed); h.setValid()` | `HitInfo h = HitInfo(packedHit); HitInfo.packHeader(packed, HitType::Triangle)` |
| Camera previous-frame ray     | `Camera::computeRayPinholePrevFrame`     | Removed; we read `gScene.camera.data.prevPosW` directly and reconstruct |
| Camera position helper        | `gScene.camera.getPosition(usePrev)`     | `usePrev ? gScene.camera.data.prevPosW : gScene.camera.data.posW` |
| Ray construction              | `Ray(origin, dir, 0, tMax)` ctor         | Same struct, but `setValid()` and a few other helpers were removed |

## Algorithmic guards backported from NVlabs

These are the only **non-mechanical** changes vs DQLin's reference. Each is
a conservative safety check that NVIDIA itself added to their Falcor 6.x port,
not a deviation we invented.

### 1. `isIntegrandInvalid()` — discard non-finite shifted integrands

**Source:** `refs/NVlabs_conditional_ReSTIR/Source/Falcor/Rendering/ConditionalReSTIR/Shift.slang:26`

**Backport target:** `Source/RenderPasses/ReSTIRPTPass/Shift.slang::isIntegrandInvalid`

DQLin's reference has `isJacobianInvalid()` (rejects non-finite Jacobians) but
no equivalent check on the shifted integrand itself. When near-grazing
reconnection vertices produce `Inf` or `NaN` components in `dstIntegrand`,
those infinities flow into `PathReservoir.F` and persist through every
subsequent `mergeWithResamplingMIS` call (`weight += scalarF * J * w` becomes
`Inf` permanently). NVIDIA added this check explicitly when forward-porting
the algorithm to Falcor 6.x.

The check is unbiased — paths with `Inf`/`NaN` integrand were already invalid
samples that should never have entered the reservoir.

**Sites that gate on the check** (all in `Shift.slang`):

- `computeShiftedIntegrandRandomReplay` — guards `L` from `traceRandomReplayPath` before return.
- `computeShiftedIntegrandHybrid` — guards the final `Tp * rcTp` product (path throughput from `traceRandomReplayPathHybridSimple` can blow up through near-grazing surfaces, bypassing internal guards).
- `computeShiftedIntegrandReconnectionPathTree` (BPR) — replaces the inline `if (any(isnan||isinf)) return 0.f` at the BPR exit with the unified check (now also catches negative components).
- `computeShiftedIntegrandReconnection` — adds the missing guard at the main reconnection-path return site (DQLin had no check here at all). This is the dominant firefly source on Cornell.

### 2. `evalBsdfAndPdf` instead of `setActiveLobes` + `evalPdf`

Already listed in the API-adaptation table above for completeness, but worth
calling out as an algorithmic backport: the original DQLin code switched the
BSDF's active-lobe set with `setActiveLobes(...)` before calling `evalPdf`,
which **renormalizes** the PDF within the active subset. ReSTIR PT shift
Jacobians need the *un-normalized* partial PDF (the sum of `pLobe * lobePdf`
for selected lobes weighted by the original full-BSDF lobe selection).
NVlabs's `evalBsdfAndPdf(sd, wi, sg, lobeMask, pdfSingle, pdfAll)` returns
exactly that. Implemented in `Falcor8Compat.slang::evalPdfBSDF`.

### 3. `isinf(w)` in reservoir merges

DQLin's `PathReservoir.slang` merge functions guard the candidate weight `w`
against `NaN` and `0`, but not against `Inf`. NVlabs's port adds the `isinf`
check at every merge/add site (e.g.
`refs/NVlabs_conditional_ReSTIR/.../PathReservoir.slang:462`). With §1's
integrand guards in place, `w = scalarF * Jacobian * weight * misWeight`
should never produce `Inf` from a clean integrand, but the defensive check
matches NVlabs's pattern exactly and costs one extra fcmp.

Backport target: `Source/RenderPasses/ReSTIRPTPass/PathReservoir.slang` —
all four merge guard sites updated from
`if (isnan(w) || w == 0.f) return false;` to
`if (isnan(w) || isinf(w) || w == 0.f) return false;`.

### 4. Color guard before unconditional accumulation

**Backport target:** `Source/RenderPasses/ReSTIRPTPass/TemporalReuse.cs.slang::execute` (~line 301)

DQLin's `TemporalReuse.cs.slang` only guards `color = F * weight` against
`Inf`/`NaN` *inside* the `if (useDirectLighting)` branch. When
`useDirectLighting=false`, `outputColor[pixel] += color / SPP` runs
unguarded — and `F * weight` can be `Inf` even after `weight` is clamped, if
`F` itself was `Inf` from the shift step. We hoisted the guard out so it
fires regardless of the direct-lighting path.

### 5. Scene-relative `nearFieldDistance` threshold

**Sources:**
- DQLin: `refs/DQLin_ReSTIR_PT/.../Params.slang:152` —
  `float nearFieldDistance = 0.1f; //TODO: make this adaptive to spatial reuse size / scene size`
- NVlabs: `refs/NVlabs_conditional_ReSTIR/.../ConditionalReSTIR.slang:87` —
  `float nearFieldDistanceThreshold = 0.03f; // percentage of scene radius`,
  multiplied by `sceneRadius` at use sites; `sceneRadius = min(extent.x, extent.y, extent.z)`
  set from C++ via `mpScene->getSceneBounds().extent()`.

**Backport targets:**
- `Source/RenderPasses/ReSTIRPTPass/Params.slang::RestirPathTracerParams` —
  `nearFieldDistance` default changed `0.1f` → `0.03f` and now interpreted as
  a fraction of `sceneRadius`. New `sceneRadius` field added (replaces unused
  `uint2 dummy` padding; net struct size unchanged).
- `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp::setScene` — populates
  `mParams.sceneRadius = min(extent.x, extent.y, extent.z)` from scene bounds.
- `Source/RenderPasses/ReSTIRPTPass/Shift.slang::computeShiftedIntegrandReconnection`
  (was line 487) and
  `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang::nextVertex` (two sites,
  was lines 1120 and 1180) — multiply `params.nearFieldDistance` by
  `params.sceneRadius` at the comparison.

DQLin's hardcoded `0.1f` absolute world-units threshold is scene-scale variant:
on Cornell (shortest-axis extent ≈2.0) the threshold sits at 0.1, slightly
over-clamping shifts; on Sponza (≈30) and Bistro (≈50–100) the same 0.1 sits
far below where the reconnection Jacobian (`cos / dist²`) starts exploding,
allowing near-grazing reconnections through. NVlabs's port multiplies by
`sceneRadius` so the threshold scales with the scene; the same `0.03` fraction
gives 0.06 on Cornell, ~0.9 on Sponza, ~1.5–3.0 on Bistro. This is the most
plausible candidate for the residual ReSTIR-mode static-scene fireflies the
§1 integrand guards alone don't fully suppress on large scenes.

DQLin's params.slang carries an explicit `TODO: make this adaptive to spatial
reuse size / scene size` — this backport addresses that exact TODO with
NVlabs's solution.

### 6. Reservoir validity guards at write sites

**Backport targets:** `PathTracer.slang::writeOutput` (two `outputReservoirs[..] = ..` writes), `SpatialReuse.cs.slang` (~line 540 — `temporalReservoirs[centralOffset] = dstReservoir`), `TemporalReuse.cs.slang` (~line 300 — `outputReservoirs[centralOffset] = dstReservoir`).

The path-build sum-of-contributions can produce non-finite `pathReservoir.F`
via grazing `1/pdf` chains *before* any GRIS shift runs, and the existing
weight guards at the same write sites guarded only `weight`, not `F`. We zero
both fields when invalid (NaN, Inf, negative weight) AND clamp absurd-but-
finite magnitudes (`F > 1e10` or `weight > 1e10`) that would otherwise
overflow accumulation across multiple frames inside the static-scene
spatial+temporal merge cascade.

The §1 integrand guards in `Shift.slang` and the §3 `isinf(w)` merge guards
in `PathReservoir.slang` already guarded shift outputs and merge inputs. §6
is the analogue at the reservoir-buffer-write boundary.

### 7. `finalizeRIS` / `finalizeGRIS` post-division guard

**Backport target:** `PathReservoir.slang::finalizeRIS`, `finalizeGRIS`.

DQLin's reference checks `if (p_hat == 0.f) weight = 0.f` before the
`weight / p_hat` division — exact equality only, so tiny-but-nonzero `p_hat`
(e.g. 1e-30 from grazing reconnection integrand) divides through and
produces an Inf weight. Add a post-division `isnan/isinf/<0` re-guard so
the reservoir's `weight` never carries Inf or NaN to the next merge.

### 8. `[CLAMP-FOR-EARS]` per-sample F luminance ceiling

**Backport target:** `PathBuilder.slang::addEscapeVertex`, `addNeeVertex`
(top of function, before `pathReservoir.add` / `pathReservoir.F +=`).

Even with §1, §3, §6, §7 guards, multi-frame static-scene canonical mode
still overflows: each path's `pathWeight` can be a finite-but-large value
from a `1/pdf` chain, and `pathReservoir.F += pathWeight` accumulates these
over spatial+temporal merges across frames. After 30+ frames of the same
floor cluster contributing 1e6-scale values, sums hit float32 max → Inf.

DQLin's reference algorithm assumes **dynamic scenes**: M-cap + temporal
reprojection invalidates accumulating drift before it overflows. Static-
scene 30+ frame accumulation is outside DQLin's design envelope. Their
paper's bias discussion implicitly acknowledges this; the only clamp DQLin
applies (`path.pdf = min(path.pdf, 1e30f)` at PathTracer.slang:350) is a
legacy-BRDF guard, not a throughput guard.

We clamp `pathWeight` to `params.pathThpMax` (default `1e4f`) at the
PathBuilder add sites. **Biased** — undercounts legitimate-but-rare bright
paths above 1e4 luminance — but bounded. Sites are tagged `[CLAMP-FOR-EARS]`
to mark them as the hooks for the future EARS (Rath 2022) splitting/RR
replacement: the biased ceiling becomes an unbiased splitting decision once
the VisCache adjoint estimate is wired into the path-walk.

`pathThpMax = 1e4f` rationale: Cornell brightest highlight ≈ 84 cd/m²,
Sponza+Bistro HDR sun ≈ 1e3 cd/m². 1e4 leaves 10–100× headroom over real
brightness; values above are firefly artifacts, not real radiance.

### 9. Periodic reservoir reset

**Backport target:** `TemporalReuse.cs.slang` (right after the per-pixel
`temporalReservoir = temporalReservoirs[...]` read).

DQLin's algorithm assumes motion-induced reservoir disposal — under static
scenes the same per-pixel reservoir merges with itself every frame and the
weight/M state drifts upward. We zero `temporalReservoir.M`, `.weight`, `.F`
every `gReservoirResetPeriod` frames, with a per-pixel hash phase offset so
the population-wide reset is spread over time (smooth bias, not synchronized
flashes). Default 16 — Cornell stays clean at 32-frame accum without
sacrificing too much sample-history benefit.

C++ side: `mReservoirResetPeriod` member (ReSTIRPTPass.h), bound at the
PathReusePass cbuffer (ReSTIRPTPass.cpp ~line 1669).

### 10. `[CLAMP-FOR-EARS]` merge-time weight drop

**Backport target:** `PathReservoir.slang::add`, `merge`,
`mergeWithResamplingMIS` — drop a candidate if EITHER:
- absolute floor: `w > 1e4f`, OR
- relative gate: `M >= 2 && this.weight > 0 && w > 100 * this.weight`

after the existing NaN/Inf check.

§8 caps individual `pathWeight` at insertion. Merges multiply that already-
clamped F by `inReservoir.weight` (which is itself a sum of clamped
contributions from many resampled samples) and a Jacobian. The product can
still grow into the 1e8–1e30 range as 32-frame accumulation and spatial-
neighbor MIS pile up multiplicative factors. The merge-time drop is the last
defensive boundary before the candidate's `w` enters the reservoir's running
`weight += w` sum.

Two-gate design rationale:
- The absolute floor catches the FIRST extreme sample (relative gate skips
  M=0 since `this.weight=0`).
- The relative gate catches subsequent fireflies that don't exceed the absolute
  cap but are pathological compared to the reservoir's running state.

Same `[CLAMP-FOR-EARS]` marker as §8 — both replaced by EARS splitting once
the VisCache adjoint hookup lands.

**Verification (b=4 x1, 32-frame accum, canonical config):**

| scene                   | vanilla mean | restirpt mean | restirpt fmax | inf | delta    |
|-------------------------|--------------|---------------|---------------|-----|----------|
| CornellBox_1AreaLight   | 0.398        | 0.372         | 81            | 0   | -6.45%   |
| CornellBox_32PointLights| 0.067        | 0.054         | 7276          | 0   | -18.12%  |
| Sponza                  | 0.015        | 0.049         | 30.5          | 0   | +225.26% |

Cornell scenes: tight bias (-6 to -18%), usable as a quantitative reference.
Sponza: finite (no Infs) but 3× over-bias because the absolute 1e4 floor is
far too loose for Sponza's low-radiance scene scale (vanilla max=1.4). Per-
scene threshold tuning or scene-aware threshold derivation (e.g. from
emissive-light total flux) is the next step. **Functional canonical port
with caveat: Sponza-class low-HDR scenes need scene-aware thresholds.**

§10 retired in favor of §11 (RTXPT adaptive K). The merge-time absolute and
relative gates are removed; the `[CLAMP-FOR-EARS]` marker now lives on §11
and §8 only as the EARS replacement target.

### 12. Lin 2026 backports (Tier-1)

Source: Lin et al. 2026 "ReSTIR PT Enhanced"
(https://research.nvidia.com/labs/rtr/publication/lin2026restirptenhanced/).
No public code release; backported from paper text.

**#1 — Footprint-based reconnection criterion (Lin 2026 §4):** Replaces our
scene-dependent §5 `nearFieldDistance × sceneRadius` distance gate with the
scene-independent inequality

  `1 / (p_{k-1}(ω_{k-1}) · G(x_{k-1}→x_k)) ≥ c · R_pri²`

where `R_pri² = ||x_0 - x_1||² · cos(θ) / (4π)` is the primary-hit ray-cone
footprint area, `G = cos(faceN, ω) / dist²` is the geometric factor, and
`c = 0.02` is paper-suggested (hardcoded, no UI knob — c-ablation in the
paper showed 0.02 is robust across scenes). Sites:

- `PathTracer.slang::handleHit` (~line 1056) — compute `R_pri²` once at primary hit, stash on `PathState.pathPrimaryFootprint2`.
- `PathTracer.slang::nextVertex` (two rcVertex selection sites) — replace distance test with footprint criterion.
- `Shift.slang::computeShiftedIntegrandReconnection` — same, using `srcReservoir.cachedJacobian.x` as the source's cached `p_{k-1}` proxy.

Verification (b=4 x1, 32-frame canonical, with §10 still active for safety):
shift in bias from §1-§11 baseline is small (Cornell -6.45 → -6.58%, 32PL
-18.12 → -18.33%, Sponza +225 → +226%). The criterion is stricter near
delta lobes (high p) and looser at glossy/diffuse bounces, but on these
scenes the existing §11 + §10 already constrain the sample population
enough that the criterion change is mostly cosmetic. Expected impact
shows at higher bounce counts and glossy-corridor scenes (Lin 2026's
test scenes — not in our current set).

**#2 — RR at initial sample only, never during replay (Lin 2026 §6.2.4):**
DQLin's `terminatePathByRussianRoulette` was being invoked from both
initial path generation and from `traceRandomReplayPath` /
`traceRandomReplayPathHybridSimple` during the resampling stage. RR during
replay can randomly kill valid reused paths, biasing the resampler toward
shorter paths that survive RR. Lin 2026 fix: gate RR to initial only via
`if (path.enableRandomReplay) return false` at function entry.

Verification: small/no measurable effect at b=4 on our 3 scenes — RR
rarely fires at b=4 in steady state (most paths die from envelope, not
luminance). Expected to matter more at higher bounces or HDR scenes
where RR-pdf accumulates significantly.

**Open / Pending:**
- **#3 — Forced NEE light reconnection (Lin 2026 §6.2.3):** replay-side
  re-sampling of NEE lights causes shift validity failures. Fix: hydrate
  LightSample from the source reservoir's stored light-index instead of
  calling `generateLightSample` afresh in replay. Touches
  `traceTemporalUpdate` and `traceRandomReplayPath` NEE-terminating cases.
  Likely to materially improve hybrid-shift acceptance rate on
  multi-light scenes.

- **#4 — Vector-valued resampling weights (Lin 2026 §6.3):**
  IMPLEMENTED 2026-05-06 (corrected derivation). The May 2026-05-05 attempt
  was reverted with catastrophic results — see "Prior attempt (reverted)"
  below for the wrong derivation. Corrected math now ships:

  **Math.** Per-candidate `w_vec_i = m_i × F(X_i) × |J_i| × W_src,i` (vector
  in F, scalar in everything else). At every merge site, mirror the scalar
  `w_scalar_i = lum(F_i) × J_i × inReservoir.weight × misWeight` with
  `w_vec_i = F_i × J_i × inReservoir.weight × misWeight`. The
  `inReservoir.weight` factor is a SCALAR (the source pixel's already-
  finalized scalar UCW); scalar × vector = componentwise broadcast preserves
  the per-merge-step invariant `lum(weightVec) = weight`. Vector × vector
  was the prior bug — would create radiance² units and dark-pixel blowups.

  **Finalize.** Same scalar denominator as the scalar form: `weightVec /=
  (lum(F_chosen) × M)` for `finalizeRIS`, `weightVec /= lum(F_chosen)` for
  `finalizeGRIS`. Same scalar criterion ⇒ invariant survives finalize.
  `prepareMerging` un-finalize: `weightVec *= lum(F_chosen) × M`.

  **Sites.** All four merge accumulators (`add`, `merge`,
  `mergeWithResamplingMIS`, `mergeInSamplePixel`), both finalize variants,
  `prepareMerging`, plus pairwise-MIS post-divide at SpatialReuse:411
  (`weightVec /= (validNeighborCount + 1)`). Output sites
  (TemporalReuse:303, SpatialReuse:337/413/532) replace `F × weight` with
  `weightVec` directly.

  **BPR gate.** All `weightVec`-touching code is gated `#if !BPR`. BPR
  mode already accumulates a vector value in `pathReservoir.F` directly —
  it doesn't need a parallel `weightVec`. Struct field is omitted under
  BPR; `pathTreeReservoirSize` (128B) unchanged. `baseReservoirSize` bumped
  88B → 100B for non-BPR.

  **Verification (2026-05-06, Cornell_1AL + Sponza, b∈{1,4,8}):** scalar
  luminance metrics preserved bit-exactly; mean_err and artifact_5 show small
  improvements from chroma marginalization. BPR variants unchanged.

  | scene · variant | scalar baseline | with §6.3 vector | Δ |
  |---|---|---|---|
  | Cornell restirpt_b4 mean_err x1 | 3.789% | **3.731%** | −1.5% |
  | Cornell restirpt_b4 art5 x1    | 25.42% | **24.75%** | −2.6% |
  | Cornell restirpt_b4 RMSE x1    | 0.816  | 0.816 | match |
  | Cornell restirpt_b8 mean_err x1 | 3.788% | **3.726%** | −1.6% |
  | Sponza restirpt_b4 mean_err x1 | 15.012% | **15.003%** | −0.06% |
  | Sponza restirpt_b4 RMSE x1    | 0.768  | 0.768 | match |
  | restirpt_bpr_* (all)          | (any) | unchanged | BPR-gated ✓ |

  The luminance invariant `lum(color_v) = lum(color_s)` holds by construction:
  per-merge invariant `lum(weightVec) = weight` is linear in lum, and the
  output `× toScalar(F)` factor recovers the `Σw/M` luminance the scalar form
  produces. Cornell shows the biggest chroma-marginalization win because its
  saturated walls have richer chroma signal; Sponza's dim indirect content
  has less to marginalize. BPR mode is gated `#if !BPR` and produces
  bit-identical output regardless of §6.3.

  Outstanding: per-channel `chroma_var` metric added to baseline CSV schema
  this session — populates from next ladder run forward. Multi-scene
  extension (Cornell_32PL + BistroInterior) pending.

  ### Prior attempt (reverted 2026-05-05)

  Added `float3 weightVec` and accumulated `in_F × J × W × misWeight` as
  documented above. **Bug 1**: finalize divided by `M` only, not by
  `lum(F_chosen) × M` — dropped the `1/p_hat` factor. **Bug 2**: PORT_NOTES
  claimed UCW propagation went vector × vector, which would explain Sponza
  +1920% via radiance² units. Result was Cornell 1AL +20%, 32PL +28%,
  Sponza +1920% — reverted same day. The corrected derivation (above)
  identifies both bugs and ships the right form.

- **Stage A unification (Lin 2026 §5 supplemental):**
  ATTEMPTED + REVERTED 2026-05-05. Switched canonical config to
  `disableDirectIllumination=false`, `useRTXDIDirect=false`,
  `useDirectLighting=false` (no external DI feed; internal NEE handles
  primary-hit direct light). Combined with §12 #1 footprint criterion as
  Lin 2026 prescribed.

  Result: 200k+ Infs on all 3 scenes — even with §12 #1 active, d=2 paths
  whose rcVertex is at x_1 fail the GRIS shift. The supplemental's full
  multi-sample MIS weight `ω_1 = M·p_1 / (M·p_1 + p_2)` is needed to make
  d=2 + d≥3 share the path tree correctly; Stage A "minimal" without that
  weight is incorrect at the boundary.

  Reverted to canonical config (RTXDI feed mode + `disableDirectIllumination=true`).

**Status (2026-05-06):** §12 #1, #2, #4 active in the reference port. #3
(forced NEE reconnection) deferred — paper claim is performance, not
quality, and our current performance is fine. Stage A unification still
pending — needs the supplemental §5 `m_1 = M·p_1/(M·p_1+p_2)` MIS weight
at the d=2 boundary; not yet attempted under the corrected derivation
framework. Canonical port state matches PORT_NOTES TL;DR table:
Cornell_1AL b4 mean_err 3.79%, Sponza b1 RMSE −59% / +7.7 dB PSNR vs
vanilla. The earlier "Sponza +289%" claim was from the wrong-camera /
wrong-GT / stale-cache harness retired with §10 in 2026-05-06; current
RPT00 numbers are clean and validated.

### 11. RTXPT-style adaptive firefly filter K

**Source:** `refs/NVIDIAGameWorks_RTXPT/Rtxpt/Shaders/PathTracer/PathTracerHelpers.hlsli`
— `FireflyFilter`, `ComputeNewScatterFireflyFilterK`,
  `ComputeRayConeSpreadAngleExpansionByScatterPDF`.

**Backport targets:**
- `Falcor8Compat.slang` — three new helpers `fireflyFilter`,
  `computeNewScatterFireflyFilterK`, `computeRayConeSpreadAngleExpansionByScatterPDF`
  (verbatim port of RTXPT's formulas).
- `PathState.slang::PathState` — new `fireflyFilterK` field, default 1.0.
- `PathTracer.slang::generateScatterRay` — call
  `computeNewScatterFireflyFilterK(path.fireflyFilterK, result.pdf, 1.0)`
  after each BSDF sample to update K along the path.
- `PathBuilder.slang::addEscapeVertex` / `addNeeVertex` — replace the §8
  flat `pathThpMax` luminance clamp with `fireflyFilter(pathWeight,
  params.fireflyFilterThreshold, fireflyFilterK)`. New trailing arg
  `fireflyFilterK` (default 1.0 for safety) plumbed from the 6 PathTracer.slang
  call sites passing `path.fireflyFilterK`.
- `Params.slang` — new `float fireflyFilterThreshold = 1e3f` (replaces
  `pathThpMax` semantically; `pathThpMax` field retained but unused —
  candidate for removal next pass).
- §6 magnitude clamps in PathTracer/Spatial/TemporalReuse downgraded to
  Inf/NaN-only (no `> 1e10` magnitude check) since §11 bounds upstream.
- §10 merge-time absolute+relative gates retired (PathReservoir.slang
  add/merge/mergeWithResamplingMIS) — §11 bounds the candidates that flow in.

**How K decays:** for each BSDF bounce with PDF `p` and lobe-selection
probability `lobeP`,
```
angle = ConeSpread(p, 1.0)         // cone-spread angle from PDF
K_new = max(minK, K_old * (32 / (32 + angle²)) * sqrt(lobeP))
```
Low-pdf bounces (grazing, Dirac-like): angle large → K crashes. High-pdf
bounces (diffuse hemisphere ~uniform): angle small → K barely changes.
Rare-path concentration is detected through the PDF chain alone — no cache,
no scene query, fully local.

**Verification (b=4 x1, 32-frame canonical):** TODO — rebuild + test pending.

## Runtime scene-derived parameters

`ReSTIRPTPass::setScene()` derives two boolean params from the loaded scene
rather than from user options. This matches DQLin's defaults exactly — we
flipped through the alternatives during 2026-04-30 and reverted.

```cpp
bool sceneIsDynamic = mpScene->hasAnimation() && mpScene->isAnimated();
mParams.rejectShiftBasedOnJacobian = sceneIsDynamic;
mStaticParams.temporalUpdateForDynamicScene = sceneIsDynamic;
```

- `rejectShiftBasedOnJacobian` — gates the `|J|<11` clamp in
  `Shift.slang::computeShiftedIntegrandReconnection`. DQLin's reference
  defaults it to `false` ("can be helpful for dynamic geometry"). We tested
  forcing it on for static scenes and for the canonical DI-disabled config;
  neither reduced the static-scene firefly count, and unconditional-true
  catastrophically broke the DI=on+ReSTIR branch (0→57k Infs). Left at DQLin's
  default.
- `temporalUpdateForDynamicScene` — gates the temporal-reservoir light-sample
  re-test. Unconditionally true would re-shadow-ray every reused reconnection
  vertex even on static geometry; DQLin only enables this when the scene
  itself has animation.

## Supported configurations

See `ReSTIRPTPass.h` (above the `disableDirectIllumination` field) for the
authoritative list. Verified on `CornellBox_1AreaLight` at 40-frame accumulation:

| Configuration                                                    | Status        | Notes                                            |
|------------------------------------------------------------------|---------------|--------------------------------------------------|
| **ReSTIR mode + `disableDirectIllumination=true` + RTXDI feed**  | ✅ DQLin canonical | **The reference config.** After §1-§10 backports: 0 Inf on Cornell + Sponza + Cornell32PL, mild-to-moderate biased (Cornell -6 to +15%, Sponza +225%). Larger-scene threshold tuning is the open work. Wired as `restirpt_b{N}` in Ladder00. |
| ReSTIR mode + `disableDirectIllumination=false` (no RTXDI feed)  | ❌ unsupported | Direct-light samples flow through GRIS shift; near-grazing reconnections to floor cluster produce ~57k Inf pixels. The Jacobian-rejection clamp (`rejectShiftBasedOnJacobian`) interacts badly with cached Jacobians in this branch and is disabled here. |
| PT-mode + `disableDirectIllumination=false`                      | debug only    | Matches vanilla `PathTracer` within 1.7% energy, 0 Infs — but **bypasses GRIS resampling** and so does not exercise the ReSTIR-PT algorithm. Useful only for verifying the path-tracing pipeline of the plugin still produces parity with vanilla. Not a meaningful ReSTIR-PT reference and **not exposed in Ladder00** as a baseline. |

`rejectShiftBasedOnJacobian` is set by `setScene()` to match DQLin's default —
animated geometry only. We tested forcing it on for static scenes; it didn't
suppress the firefly count and made the unsupported `DI=false` config
catastrophically worse, so we left DQLin's behavior unchanged.

## Ablation / debug test infrastructure

- `scripts/ReSTIRPT_Graph.py` — exposes `pathSamplingMode`, `useRTXDIDirect`,
  `useDirectLighting`, and `disableDirectIllumination` so any of the
  configurations in the matrix above (and their ablation cousins) can be
  built without recompiling. PT-mode wraps the same pass with resampling
  bypassed — it routed the bisection that isolated the firefly to GRIS shift
  rather than path generation.
- `scripts/ReSTIRPT_Baseline_Test.py` — single-cell harness used by
  `.scripts/restirpt_baseline_run.sh`. Each invocation processes one
  `(VARIANT, BOUNCE)` pair across all scenes to stay under Slang's
  per-process permutation budget. Variants:
  `vanilla`, `restirpt` (canonical), `restirpt_no_rtxdi`,
  `restirpt_no_direct`, `restirpt_pt_mode`, `restirpt_pt_mode_with_rtxdi`,
  `restirpt_pt_mode_di_on`, `restirpt_di_on` — these are the bisection
  variants that produced the support matrix.

## Future additions

Items attempted, reverted, or left unfinished. Excised from the **DQLin
reference port** to keep it minimal and bug-for-bug faithful. Forward
algorithmic work happens in our `restirpt_2d` / `restirpt_3d` PathTracer-
based ports (analogues of the existing `restir_2d` / `restir_3d` DI ports
under `Falcor/Source/RenderPasses/PathTracer/restirpt/`), which are simpler
to extend than DQLin's multi-pass Falcor 4 pipeline. This section documents
the design + state of each item so the future port can pick up directly.

### §12 #3 — Forced NEE light reconnection (Lin 2026 §6.2.3)

Replay-side `generateLightSample` re-samples a fresh light, which doesn't
match the source reservoir's stored light index → shift validity gates
fail → resampler rejection. Lin's fix: hydrate `LightSample` from the
reservoir's stored `pathFlags.lightType + lightPdf + rcVertexHit + rcVertexWi[]`
instead of re-sampling. Touches `traceTemporalUpdate` and the NEE-terminating
case of `traceRandomReplayPath`. Expected to lift hybrid-shift acceptance
rate on multi-light scenes. **Not implemented.**

### §12 #4 — Vector-valued resampling weights (Lin 2026 §6.3)

`PathReservoir::merge` currently bookkeeps `weight` as a scalar (luminance-
only resampling decision). Lin's enhancement maintains a parallel `float3
weightVec` accumulator (`Σ m_i × F_i × W_i × |J|`) so the chosen-sample's
chroma noise is averaged across the merge stream rather than carried by
the single chosen `F`. **Attempted + reverted** — our re-derivation of
the Talbot-form normalization broke output (Cornell +20%, Sponza +1920%).
Lin's supplemental Eq. §5 (`ω_1 = M·p_1 / (M·p_1 + p_2)`) likely factors
into the vector accumulation, not just at NEE; needs careful re-read.

### Stage A unification (Lin 2026 §5 supplemental)

Drop the external RTXDI direct-light feed, let internal NEE handle primary
direct (so paths don't double-count). Combined with §12 #1 footprint
criterion. **Attempted + reverted** — d=2 paths whose rcVertex is at x_1
fail the GRIS shift, producing ~200k Inf pixels per scene. The full
multi-sample MIS weight `ω_1 = M·p_1 / (M·p_1 + p_2)` is needed for d=2 +
d≥3 to share the path tree correctly. The "minimal Stage A" attempt
without that weight is mathematically incorrect at the boundary.

### §14 — ADRRS-without-adjoint splitting

Vorba 2016 ADRRS / Lin §6.2.4: when path throughput exceeds 1, push a
replica snapshot for later replay. A path that would have produced a
firefly through luminance amplification gets split into two half-throughput
paths instead. **Attempted + reverted** — capture hook fired AFTER
`handleHit`, so the replica double-counted the split-vertex's emission/NEE
(violates unbiasedness). Correct hook needs a path-walk-loop refactor in
`TracePass.cs.slang` to capture state BEFORE `handleHit`. Scaffold removed
from the reference (commit excises `PathState.adrrs*` fields, the
`walkPathReplica` function, and the drain loop in `tracePath`).

### §11 — RTXPT-style adaptive FireflyFilter K

Verbatim port of NVIDIA RTXPT's `FireflyFilter`,
`ComputeNewScatterFireflyFilterK`, and `ComputeRayConeSpreadAngleExpansion-
ByScatterPDF` from `refs/NVIDIAGameWorks_RTXPT/`. Heavy machinery: per-
path-bounce K decay tracked through the BSDF chain, gates `pathWeight` at
`addEscapeVertex`/`addNeeVertex`. **Implemented + retired** — the canonical
algorithm + §1, §3, §6, §7 NVlabs guards already keep Cornell + Sponza Inf-
free; §11 added complexity (helpers in `Falcor8Compat.slang`,
`pathBuilder.fireflyFilterK` plumbing, `Params.slang::fireflyFilterThreshold`)
without measurable gain on our 3 test scenes. Code reverted; the slot in
`Params.slang` was repurposed to `fireflyClampK` (§15).

### §10 — Merge-time absolute + relative weight clamps

Hybrid `if w > 1e2 || (M ≥ 2 && w > 100×this.weight) drop`. Diagnosed from
threshold sweeps when we mistakenly thought ReSTIRPT was producing 18% bias
on Sponza. The clamps were ACTIVELY BIASING the resampler — `M += inReservoir.M`
runs but `weight += w` skipped on drops, so `finalize`'s `weight/(p_hat × M)`
under-estimates by the drop-fraction. Once the bias was traced to the
test-harness (wrong camera, wrong GT, stale cache), the clamp's motivation
disappeared. **Retired**; code paths only carry the standard NaN/Inf/zero
guard.

### §8 — `pathThpMax` path-throughput clamp

`PathBuilder::addEscapeVertex/addNeeVertex` clamp `pathWeight` at
`params.pathThpMax = 1e4` to bound 1/pdf chain growth across spatial+
temporal merges. **Retired** — Lin 2026 footprint criterion (§12 #1) +
§13 1e10 Inf/NaN safety net at writeback are sufficient. Slot in
`Params.slang` (`_retiredField0`) kept for cbuffer ABI stability.

### §9 — Periodic reservoir reset

Every `gReservoirResetPeriod` frames, zero `temporalReservoir.M/.weight/.F`
with per-pixel hash phase offset to amortize. Workaround for static-scene
weight drift. **Retired** — root-caused as the `pathThpMax` and `§10` clamps
biasing the M counter; with those retired the drift goes away. C++ side
retains `mReservoirResetPeriod` member out of habit; can drop in a future
ABI-breaking pass.

### §15 — Calibration vs. dropping

Currently the §15 chroma-preserving soft-clamp at `K × max-channel(DL)` is
the only firefly defense beyond the §13 Inf/NaN safety net. K is now
parameterized as `params.fireflyClampK` (default `30.0`) and exposed
through `render_graph_ReSTIRPT(fireflyClampK=...)`. **Calibration TODO**:
ladder sweep K ∈ {10, 30, 100, 300, 1000, ∞} per scene per bounce in
RPT01, pick the value minimizing weighted RMSE+PSNR across the scene set,
bake as the new default. Open question: whether to retire §15 entirely if
K=∞ wins (= no clamp).

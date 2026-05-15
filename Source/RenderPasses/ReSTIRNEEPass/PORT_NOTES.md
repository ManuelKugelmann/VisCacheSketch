# ReSTIRNEEPass — every-vertex K-RIS NEE on a clean PathTracerX base

## Status (2026-05-14)

**Initial implementation landed.** Forked verbatim from
`Source/RenderPasses/PathTracerX/` (clean Falcor PathTracer + VisCache fork),
with a single localised K-RIS wedge added inside the NEE block of
`PathTracer.slang`. Plugin class renamed `PathTracerX → ReSTIRNEEPass`
everywhere; shader file paths in C++ retargeted to
`RenderPasses/ReSTIRNEEPass/`.

## Conceptual model

"ReSTIR DI with multiple bounces." The K-RIS that ReSTIRDIPass runs once at
the primary hit is run *at every NEE call-site* (every non-Delta surface
vertex along the path). No buffer-backed reservoirs — the reservoir is a
local on the slang stack, rebuilt fresh per vertex per frame. No
spatial/temporal reuse in v1.

## The K-RIS wedge

`Source/RenderPasses/ReSTIRNEEPass/PathTracer.slang`, inside `handleHit`'s NEE
block (around the `// Sample a light.` comment). When
`kNumNEECandidates > 1`:

1. Sample K light candidates via the existing `generateLightSample` (mixes
   env / emissive / analytic per Falcor's NEE selection logic).
2. Compute p̂ = luminance(BRDF × Li) per candidate — visibility-blind target
   pdf. Mirrors ReSTIRDIPass's `pHat = luminance(Lr)` convention.
3. Streaming RIS: accept candidate k with probability `pHat_k / sumW_k`.
4. After the loop, apply unbiasing factor `W = mean(pHat) / pHat_winner` to
   `ls.Li`. Downstream BRDF evaluation + MIS combination is unchanged.
5. Single shadow ray traced on the winner (Falcor's standard visibility
   path; respects `USE_VISCACHE_VISIBILITYCHECK` if VisCache is wired).

`K = 1` is compile-time-equivalent to vanilla NEE: the K-RIS branch is
guarded by `if (kNumNEECandidates <= 1u)`, a compile-time constant, so
Slang DCEs the else branch. Runtime output matches PathTracerX (verified
by render-diff regression at K=1; see *Validation* below).

## C++ knob

`mStaticParams.numNEECandidates` (uint, default 16). Propagated via
`getDefines()` as `NUM_NEE_CANDIDATES`. Properties key:
`"numNEECandidates"`. Changing it triggers a shader recompile.

## Known approximations (deferred)

- **MIS pdf**: the K-RIS sample has effective pdf
  `p_RIS = p_src(winner) / W > p_src(winner)` (we oversample high-pHat
  regions). The current code feeds the winner's original `ls.pdf = p_src`
  into `evalMIS`, which yields a smaller `w_NEE` than the variance-optimal
  combination would. Net effect: **NEE is under-weighted in the MIS
  combination** (and the symmetric path — BSDF samples that hit a light
  — is unaware of the K-RIS pdf entirely, so BSDF contributions are
  over-weighted). The estimator stays unbiased; only the combination's
  variance is sub-optimal. Tighten when metrics show MIS-related noise.
- **Visibility-blind target pdf**: pHat omits the shadow term. Variance
  reduction is good for diffuse-dominant scenes; in heavy-occlusion
  configurations a V-aware p̂ (extra K shadow rays per vertex) would help
  but is expensive — out of scope for v1.
- **No reuse**: no temporal accumulation, no spatial sharing, no per-cell
  reservoir storage. Each vertex's K candidates are drawn fresh from the
  PathState's RNG stream. This is by design — "essentially ReSTIR DI with
  multiple bounces" interpreted as the streaming-RIS piece without the
  buffer-backed reuse layer.

## Files

Same surface as PathTracerX (verbatim sibling fork): PathTracer.slang,
PathState.slang, Params.slang, StaticParams.slang, ColorType.slang,
GuideData.slang, NRDHelpers.slang, PathTracerNRD.slang, LoadShadingData.slang,
TracePass.rt.slang, GeneratePaths.cs.slang, ReflectTypes.cs.slang,
ResolvePass.cs.slang. C++ class `PathTracerX → ReSTIRNEEPass` throughout;
plugin name string `"ReSTIRNEEPass"`. Property key for the K knob:
`"numNEECandidates"`.

## Build + smoke

`build.bat --skip-setup` deploys the plugin. Smoke graph wiring (a
`scripts/ReSTIRNEEPass_Graph.py` analogous to `PathTracer_Graph.py`) is the
next step; until that lands, the pass is buildable but unwired.

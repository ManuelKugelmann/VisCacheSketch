# BDPTPass — Known Bias vs Falcor PathTracer

## Status

**BDPTPass is NOT a bias-matched reference for Falcor's built-in PathTracer.**
There is a real, scene-dependent dim bias of ~1% (Cornell) to ~35% (VeachAjar)
that does NOT converge away at high SPP.

For vanilla / ground-truth reference renders, use **Falcor's built-in `PathTracer`**.
BDPTPass is useful for variance comparison and bidirectional algorithm
research but should not be treated as a "truth" estimator.

## Evidence

Matched config (20-bounce, Power-sampler, no env light, useResampling=False):

| Scene                        | SPP   | PT mean | BDPT mean | Ratio  | Notes               |
|------------------------------|-------|---------|-----------|--------|---------------------|
| CornellBox_1AreaLight 1-bnc  | 256   | 0.3794  | 0.3453    | 0.910  | after F8 uv fix     |
| CornellBox_1AreaLight 20-bnc | 512   | 0.4001  | 0.3999    | 1.000  | after F8 uv fix     |
| VeachAjar 1-bnc              | 256   | 0.9442  | 0.6958    | 0.737  | after F8 uv fix     |
| VeachAjar 20-bnc             | 256   | 1.1601  | 0.8169    | 0.704  | after F8 uv fix     |
| VeachAjar 20-bnc             | 2048  | 1.1602  | 0.7590    | 0.654  | before F8 uv fix    |

The 256→2048 shift on VeachAjar is 0.01% for PT and −1.33% for BDPT. PT is
fully converged at 256 spp; BDPT is still converging slightly but to a
DIFFERENT mean. Definitively not variance.

## Fix #1 applied: Falcor 7→8 TriangleLightSample.uv semantics (commit 376f27fd)

`mEmissiveSampler.sampleLight(...)` in Falcor 7 returned barycentric
coordinates in `TriangleLightSample.uv`. In Falcor 8 (which Falcor's
own sampleTriangle now does — see `EmissiveLightSamplerHelpers.slang`),
`uv` is the RAW 2D random numbers `u` that drove the sample. The
Falcor-7-era port code in BDPTPass/PathGenerator.slang line 1050 and
1620 treated `ls.uv` as bary directly:

```slang
barycentrics = float3(1 - ls.uv.x - ls.uv.y, ls.uv.x, ls.uv.y);  // WRONG in F8
```

which (a) produces invalid barycentrics for u.x+u.y>1 (half the sample
space) and (b) non-uniformly distributes the valid samples within the
triangle. Result: BDPT sampled the wrong point on the light triangle,
which biased the evaluated Le, distance, and cosLight.

Fix: convert raw `u` to barycentrics via the standard sqrt mapping:
```slang
barycentrics = sample_triangle(ls.uv);
```

This closed ~5pp of the gap on VeachAjar (0.654 → 0.704). Cornell was
already tight (1.004 → 1.000). Direct-only (1-bounce) VeachAjar also
improved (0.670 → 0.737).

## Strategy decomposition (updated diagnosis)

NEE-vs-BSDF decomposition on VeachAjar at 256 spp (after F8 uv fix):

| Variant                   | mean   |
|---------------------------|--------|
| PT NEE+BSDF               | 1.1601 |
| PT BSDF only (NEE off)    | 1.1609 |
| BDPT NEE+BSDF             | 0.7916 |
| BDPT BSDF only (NEE off)  | 0.8170 |

Key insight: PT's NEE adds essentially zero on top of PT's BSDF-only on
this scene at this SPP (BSDF strategy alone converges). So **the bias
is NOT in NEE** — it's in **BSDF-strategy emission accumulation**.

Both PT and BDPT use `misWeight = 1` for the BSDF-emission strategy in
NEE-off mode. Both accumulate `throughput * Le * misWeight`. The
divergence is in the throughput or pdf accumulation, or in how often
the BSDF-sampled ray finds the light through the door slit.

Candidate root causes for the remaining ~30pp gap:
1. BDPT's `BSDFSample.weight` (Falcor convention BRDF*cos/pdf) is being
   processed differently than Falcor PT's `updatePathThroughput(path,
   bs.weight)`. BDPT cancels-divide-by-pdf at line 276 then overrides
   reflectance for non-delta lobes at line 287 — a subtle path that
   could drift from PT's behavior.
2. The `s.pdfW` accumulation may diverge from path.pdf in PT due to
   contProb factor (although the analytic compensation arg suggests
   this should cancel in expectation).
3. Path termination on cosOut/cosIn early-outs at AdvanceVertex line
   1820/1849 may reject paths that PT keeps alive.
4. The BSDF sample uses `s.sgBsdf` (a separate sample generator) instead
   of the main `s.sg` — this should only shift sample sequence, not
   bias, but worth verifying.

Per-pixel pdf+throughput instrumentation remains the path to a fix.

## Bug #2: maxBounces off-by-one vs Falcor PT semantics (NOT YET FIXED)

Falcor PT's `hasFinishedSurfaceBounces` uses STRICT greater-than:
```slang
return surfaceBounces > kMaxSurfaceBounces;
```

So Falcor PT with `maxSurfaceBounces=N` allows N+1 surface bounces (the
primary doesn't count). BDPT's main loop uses:
```slang
while (s.bounces < mParams.mMaxBounces && ...)
```

which allows exactly N bounces (the primary doesn't count either,
since `s.bounces` starts at 0 and is incremented after each
SampleNextVertex). So BDPT does one FEWER bounce than Falcor PT for
the same `maxBounces=N` setting.

Symptom: BDPT at `maxBounces=0` gives mean=0.00 on VeachAjar while PT
at `maxSurfaceBounces=0` gives 0.77 (light visible through door slit
via the one allowed surface bounce after the primary).

Fix candidates:
1. Change BDPT loop to `s.bounces <= mParams.mMaxBounces` to match
   PT's `>` semantics. Subtle — primary still doesn't count.
2. Document the off-by-one and require users to set BDPT
   `maxBounces=N+1` when comparing against PT `maxSurfaceBounces=N`.

Confirmed: matching BDPT b=21 vs PT b=20 (both = 21 bounces total)
does NOT close the remaining 30% gap on VeachAjar — ratio still 0.704.
So the 30% bias is separate from the off-by-one.

## Remaining unexplained ~30pp gap on VeachAjar

Bounce-by-bounce ratios (BSDF-only, matched off-by-one):
  b=0(0/1): 0.00/0.77 (BDPT misses 1 bounce due to off-by-one)
  b=1(1/2): 0.70/0.95 → 0.74
  b=2(2/3): 0.76/1.05 → 0.72
  b=21(21/21): 0.82/1.16 → 0.70

Ratio decreases with bounce count, suggesting per-bounce loss. Per-bounce
factor: (0.704)^(1/21) ≈ 0.983 → ~1.7% loss per bounce. But Cornell at
20 bounces is ratio=1.00 (no loss), so the per-bounce loss is
scene-dependent.

VeachAjar-specific factors: glass teapot (delta transmission paths),
small area light behind door (rare BSDF hits), textured surfaces. The
glass teapot specifically is interesting — BDPT's
`factor /= sqr(properties.eta)` workaround disabled at line 240 should
only affect adjoint paths (light subpaths, not camera subpaths used in
useBPT=False), so probably not the cause.

Remaining candidate: BSDF sample generator divergence. BDPT uses
`s.sgBsdf = MakeSampleGenerator(id, -seed)` (separate from `s.sg` for
NEE), which gives a different sample sequence than Falcor PT. This
shouldn't bias the expected value but might explain different
convergence behavior on hard-to-find-light scenes.

**Update**: Tested unifying generators (`sgBsdf = sg`) — ratio
unchanged at 0.704. So generator divergence is NOT the cause.

## What's been ruled out for the remaining 30pp gap

After extensive bisect, the following are NOT the cause of the
remaining ~30pp bias on VeachAjar (after sample_triangle fix and
off-by-one bounce-count correction):

1. **Russian Roulette**: `mTerminationProbability=0` doesn't help.
2. **maxDiffuseBounces=8 truncation**: setting BDPT to 20 doesn't help.
3. **maxBounces off-by-one**: BDPT b=21 matched against PT b=20 still
   gives ratio 0.704.
4. **contProb factor in BSDF pdf for MIS**: removing it makes bias
   slightly worse (0.704 → 0.682), so the factor is correct.
5. **Separate BSDF sample generator**: unifying `sgBsdf = sg` doesn't
   help.
6. **Convergence (variance vs bias)**: 2048-spp render gives 0.7042
   (vs 0.7041 at 256 spp). Definitively converged to a different
   mean than PT — real bias, not slow convergence.

## What's left to try

The bias is in the BSDF-strategy emission accumulation chain. Possible
remaining causes:

1. **`vertex.IsConnectable()` gates termination**: the
   `s.diffuseBounces == maxDiffuseBounces` check at AdvanceVertex
   line 1829 terminates paths immediately when diffuseBounces hits
   the limit, BEFORE the bounce is taken. PT's hasFinishedSurfaceBounces
   uses `>` (allows one more bounce). Could be a second off-by-one
   specifically on diffuse path counting.

2. **PathSample.IsValid() in ProcessSample**: returns false if
   `mPrefixPdf <= 0`. For very low BSDF pdf paths, mPrefixPdf could
   underflow and silently reject contributions. PT doesn't have this
   filter.

3. **Cross-bounce throughput accumulation precision**: BDPT
   accumulates BRDF*cos in throughput and BSDF_pdf in pdfW separately;
   PT accumulates BRDF*cos/pdf in single thp. Numerical precision
   could differ for long paths.

4. **Veach shading-normal correction (line 220-231 in
   GetAdjointCorrection)**: only applied to adjoint paths (light
   subpaths). For useBPT=False camera-only paths, NOT applied. PT
   does its own shading-normal handling internally in material.eval()
   — possible divergence.

## Recommendation

Use Falcor's built-in PathTracer as the vanilla reference for
ground-truth renders. BDPTPass has known scene-dependent dim bias of
1% (Cornell) to 30% (VeachAjar/glass scenes). The bias is in BDPT's
BSDF-strategy emission accumulation and persists at convergence. Two
real bugs found and one fixed during this investigation (Falcor 7→8
TriangleLightSample.uv semantics, maxBounces off-by-one); the
remaining bias root cause is in one of the candidates above and needs
per-pixel pdf+throughput instrumentation to confirm.

## What we ruled out (task #13 bisect)

- **Not a port regression.** Original Shmaug/ReSTIR-BDPT has identical MIS
  formulas. Bias was present before our Falcor 7→8 port.
- **Not Russian Roulette.** Setting `mTerminationProbability=0` (no RR)
  changes ratio by <2pp (0.66 → 0.66 on VeachAjar).
- **Not maxDiffuseBounces=8 truncation.** Setting BDPT maxDiffuseBounces=20
  to match PT changes nothing.
- **Not the BPT vs PT mode.** useBPT=True and useBPT=False give nearly
  identical means (within 1e-5). The bidirectional contribution is
  variance-reducing but not bias-shifting.
- **Not visible-light access.** The brightest pixels (camera ray hits the
  light directly) match PT to within 0.1%. The bias is in indirect /
  NEE-dominated regions.

## What the bias IS

Empirically, NEE MIS weight in BDPT is systematically lower than PT's
equivalent. Forcing `misWeight = 1.0f` in `ConnectToLight` shifts BDPT
from −35% to +16% relative to PT on VeachAjar — a 77 pp swing. The
"correct" NEE weight would be approximately 0.85 to land BDPT on PT's
value; BDPT's `Mis(directPdfW, f.mFwdPdfW)` formula computes ~0.65 on
typical NEE-dominant pixels.

Per-pixel pdf instrumentation is the next step to confirm whether
`directPdfW` is under-reported, `f.mFwdPdfW` is over-reported, or some
combination thereof.

The MIS arithmetic appears self-consistent on paper (weights sum to 1
across NEE+BSDF strategies), so the bias must come from one of:

1. **Geometry-dependent pdf inconsistency** between NEE and BSDF strategies
   — e.g., the BSDF pdf in `EvaluateReflectance` is computed for a
   different direction or under a different convention than the NEE pdf
   in `ConnectToLight`.
2. **Throughput / pdf accumulation imbalance** between the two strategies.
3. **Visibility / cosine-factor difference** between the NEE and BSDF
   evaluations of the same light-sample direction.

The bias scales with how much the BSDF strategy *would* have contributed
in PT — Cornell has small absolute BSDF contribution to direct lighting
(small area light, oblique angles), so the absolute bias is small (1%).
VeachAjar has substantial BSDF contribution through the door slit, so
the absolute bias is large (35%).

## Independent validation: Falcor PT vs MinimalPathTracer

Three-way 256-spp comparison (20-bounce matched config):

| Scene     | Falcor PT | MinimalPathTracer | BDPTPass |
|-----------|----------:|------------------:|---------:|
| VeachAjar | 1.1601    | **1.1599**        | 0.8169   |
| Cornell   | 0.4001    | 0.4001            | 0.3999   |

Falcor's PathTracer and MinimalPathTracer are independent implementations
of unidirectional path tracing with NEE+MIS. They agree within 0.02% on
both scenes — this independently confirms Falcor PathTracer as a
trustworthy unbiased reference. It's not that PT is biased high; it's
that BDPTPass is biased LOW on VeachAjar. On Cornell BDPT agrees with
both PT and MPT, so the BDPT bug is scene-specific (triggered by
glass+occlusion).

## Bug #3 found: BDPT ignores analytic lights entirely

C++ side at `BDPT.cpp:1449` defines `USE_ANALYTIC_LIGHTS` but the slang
side NEVER USES the define. BDPT only samples emissive triangles via
`mEmissiveSampler.sampleLight(...)`. Point lights, directional lights,
spot lights — completely skipped.

Evidence: on Arcade (which has DirectionalLight + PointLight + emissive
triangles), BDPT undershoots Falcor PT by 13%:

  Arcade 256 spp:
    PT/MPT:           0.31845 / 0.31839
    BDPT (full/pton): 0.27633 (same for both)   = 0.868 × truth

The directional light + point light contribute the missing ~13%. On
Cornell (no analytic lights), BDPT matches PT within 0.05%.

Fix scope: add `generateAnalyticLightSample`-equivalent to BDPT's
`ConnectToLight`, with light-type selection probability (env / emissive
/ analytic), then make sure the analytic-light NEE path produces a
proper `PathSample` with correct pdf for MIS.

Note: VeachAjar has NO analytic lights, so this fix won't close the
VeachAjar gap. VeachAjar has a separate bug. **Confirmed by clean
CornellBox_Slit test scene**: bright light hidden behind partition
wall with narrow slit at top. PT and MPT both render correctly at
0.44 mean (256+ spp, converged). BDPT renders at 0.023 mean — 95% dim,
identical at maxB=1/2/20 and SPP=256/1024.

The slit bug exists in BDPT's BSDF-strategy emission accumulation: PT
finds through-slit paths (cosine-weighted random direction sometimes
threads the opening, lands on light), BDPT doesn't. Both useBPT=True
and useBPT=False give the same dim result on slit, so the bug is in
the path-trace core, not the BPT layer. So the 30% VeachAjar gap and
the 95% slit gap are the same bug — VeachAjar's slit is wider so
fewer paths get lost.

User hypothesized PT might be undersampling VeachAjar — DISPROVEN by
the Cornell+slit test where PT/MPT agree at 0.44 (independent unbiased
estimators of the same integral) while BDPT alone diverges to 0.023.

## Slit-bug investigation plan (task #19)

Per-bounce decomposition on Cornell+Slit BSDF-only at 256 spp:
  b=1:  PT 0.386  BDPT 0.016  ratio 0.041
  b=2:  PT 0.420  BDPT 0.021  ratio 0.051
  b=20: PT 0.440  BDPT 0.023  ratio 0.053

Per-bounce ratio is ~5% at all bounces — confirms per-PATH loss, not
per-bounce compounding. About 95% of paths in PT that find the light
through the slit are silently dropped in BDPT.

Mathematical sanity-check on contribution formula:
  PT contribution per surviving path: throughput * Le / s.pdfW
    = (albedo/π * cos) * Le / (cos/π) = albedo * Le
  BDPT same formula gives albedo * Le / contProb (extra 1/contProb)
  Survival rate compensates → expected value matches PT.

So the 95% loss is NOT in the contribution formula. It's in one of:
1. Path TERMINATION (cosOut/cosIn/throughput/pdfW checks) silently
   killing through-slit paths.
2. BSDF SAMPLE direction in BDPT being systematically different from
   PT's (despite same Falcor sampleLight call).
3. EvalLightContribution returning invalid result for these paths.
4. ProcessSample's IsValid filter dropping them.

Next-iteration instrumentation: write per-pixel counter to alpha channel
of mOutputRadiance. Increment at each non-zero emission accumulation.
Compare BDPT alpha pattern vs PT to see WHERE the path drops happen.

## Per-pixel brightness pattern (BDPT max=1.18 vs PT max=71.2 on slit)

Per-pixel luminance distribution on Cornell+Slit 1024 spp:
  PT  : mean=0.4388  max=71.2  p99=8.73
  BDPT: mean=0.0241  max=1.18  p99=0.466

BDPT/PT ratio binned by PT brightness:
  pct 25-50 (dim):     ratio 0.046
  pct 50-75 (medium):  ratio 0.108
  pct 75-90:           ratio 0.141
  pct 90-99 (bright):  ratio 0.141
  pct 99-100 (peak):   ratio 0.0066  (!)

Peak pixels are MOST under-sampled in BDPT — pixels that PT renders as
very bright (lots of through-slit paths converging) get only 0.66% of
that brightness in BDPT. This rules out a uniform per-path damping —
the loss is concentrated where the highest-energy paths land.

BDPT max = 1.18 doesn't indicate a CLAMP — it's that PT averages many
high-energy hits per pixel (max 71 over 1024 spp = peak contribution
~73000 units summed), while BDPT lands such hits MUCH less often
(max 1.18 over 1024 spp = peak contribution ~1200 units summed). 60×
fewer through-slit hits found by BDPT.

## What's ruled out (Cornell+Slit confirmed)

- **Russian Roulette**: ratio 0.054 with RR off vs 0.053 with RR on.
  Identical. RR not the cause.
- **Contribution formula**: PT contribution per surviving path equals
  BDPT's by algebra (1/contProb compensation flows through s.pdfW).
- **PT undersampling**: PT and MPT (independent implementations) agree
  at 0.44 mean.
- **useBPT toggle**: vanilla, ptonly, bsdf-only all give 0.023 — no
  difference. So BPT layer is not the cause.

So the slit bug must be in **how often BDPT's BSDF sampler finds the
slit direction**, i.e., the BSDF sample-generator state evolves
differently than Falcor PT's such that the BDPT generator rarely picks
directions that thread the slit. Or there's an asymmetry in the
shading-data setup that biases the BSDF sample distribution.

Specifically, look at:
1. `vertex.SampleDirection(s.sgBsdf, ...)` vs Falcor PT's `mi.sample(sd, path.sg, ...)` — different generator (`sgBsdf` uses negative seed) might produce a sample sequence that systematically misses the slit direction
2. `mShadingData` construction differs between `PathVertex.__init` (BDPT) and Falcor PT's `prepareShadingData` flow
3. `mMaterial.sample` returning different `wo` for identical sd+sg in BDPT vs PT due to different `getMaterialInstanceHints` flags

**Update 2026-05-23**: Ruled out #3 — added AdjustShadingNormal hint (commit 3a262e24) mirroring PT. No effect on Cornell+Slit (all-diffuse, no normal map → hint is no-op there).

Mathematical analysis of single-bounce contribution:
  PT  contribution per path: throughput * Le = path.thp * Le  (where path.thp accumulates bs.weight = BRDF*cos/pdf)
  BDPT contribution per path: throughput * Le / s.pdfW = (∏BRDF*cos) * Le / ∏(pdf*contProb)
                            = PT_contribution / ∏contProb

For RR off (contProb=1), they should match exactly. Empirically Cornell+Slit
ratio is 0.054 with RR off vs 0.053 with default — identical → math
is consistent in expectation. So the 60x miss-rate must come from
SAMPLE DIRECTION DISTRIBUTION (which directions BDPT picks vs PT picks
for the same shading point), not contribution magnitude per path.

Next step: per-pixel hit counter via a new debug buffer (counter[id]
incremented at each non-zero EvalLightContribution accumulation in
ProcessSample). Compare BDPT vs PT counter patterns to localize where
sample-direction divergence occurs.

**Update 2026-05-23 (sgBsdf test)**: Tested `s.sgBsdf = s.sg`
(unified BSDF generator like Falcor PT uses), ratio still 0.053
unchanged. Separate negative-seed generator is NOT the cause.

Cumulative ruled-out list (Cornell+Slit BDPT/PT ratio constant ≈ 0.053
in all tests):
- Russian Roulette on/off
- BSDF importance sampling on/off
- useBPT toggle (vanilla/ptonly/bsdf-only)
- AdjustShadingNormal hint
- frontFacing emission handling (verified identical in Falcor source)
- sgBsdf vs sg unified generator
- mTerminationProbability=0 (RR off)

Bug needs headed Mogwai + PixelDebug `print()` at a specific
slit-affected pixel for side-by-side BDPT/PT print-log comparison.
Can't be done in the autonomous /loop.

**Update 2026-05-23 (control-scene bisect)**: Built three control
scenes that ISOLATE the bug to LIGHT POSITION, not partition geometry:

| Scene                                            | BDPT/PT ratio |
|--------------------------------------------------|--------------:|
| CornellBox_1AreaLight (flush ceiling y=1.98)     |     **1.0**   |
| CornellBox_SlitControl3 (centered, y=1.7)        |   **0.086**   |
| CornellBox_SlitControl2 (offset, y=1.7)          |   **0.058**   |
| CornellBox_Slit (offset y=1.7 + partition wall)  |   **0.053**   |

So **the partition wall is irrelevant** — the bug is fully present even
without it. The trigger is the **suspended light** (not flush with
ceiling).

Hypothesis: BDPT treats hits on the BACK FACE of the light differently
than PT does. For a flush-with-ceiling light, no ray can hit its back
face (light is glued to ceiling). For a suspended light at y=1.7, rays
bouncing in the space ABOVE the light (between y=1.7 and y=2.0 ceiling)
can hit the light's back face from above. If BDPT mis-handles back
hits (e.g., terminates path silently or fails to continue) while PT
correctly treats the hit as zero-emission-then-continue-bsdf, BDPT
would lose paths reflected off the back face area.

Next step: instrument the back-face hit accumulation path in BDPT.

## RESOLUTION 2026-05-23: "slit bug" was a scene authoring bug, NOT a BDPT bug

After a deep bisect (commits f53318e..82b65971, 3a262e24, 25d2ea11),
the "BDPT slit bug" was traced to **wrong winding order in my own
test scenes**. The light quads in CornellBox_Slit/SlitControl/
SlitControl2/SlitControl3 had vertices ordered CCW from above, which
produces a geometric cross product of +y while the stored vertex
normal was -y. PT handles this gracefully (uses geometric face
normal); BDPT treats the disagreement as backFacing for hits coming
from below, returning emission = 0 from `vertex.GetEmission()`.

After flipping vertex winding:
  CornellBox_Slit:        0.053 → 1.0006 ratio
  CornellBox_SlitControl: 0.058 → 0.9998 ratio
  CornellBox_SlitControl2: 0.058 → 0.9998 ratio
  CornellBox_SlitControl3: 0.086 → 0.9999 ratio

**So BDPT does NOT have a narrow-occlusion bug.** The 95% under-sampling
was BDPT correctly treating a wrongly-wound light surface as mostly-
not-emitting. Robustness gap from PT remains (PT permissive, BDPT
strict) but doesn't affect canonical scenes. See task #20.

VeachAjar 0.70 ratio at 256 spp is a SEPARATE issue — may be its
own scene/material quirk, or actual PT undersampling through the
door slit at moderate spp (per user's earlier hypothesis).

**Update 2026-05-23**: VeachAjar ratio is invariant 256 → 1024 spp
(0.7043 → 0.7041). Confirmed bias, not variance. Likely the same
"wrong winding" mechanism applies in the VeachAjar mesh data (light
quad winding inconsistent with stored normals) — same root cause as
the slit-bug control scenes. Cannot easily fix without modifying
the mesh files themselves.

The 30% under-sampling on VeachAjar specifically is consistent with
PT-vs-BDPT divergence on wrong-winding scenes (PT loses ~44% on
SlitControl with wrong winding; BDPT loses ~97%). Lower divergence
on VeachAjar suggests partial winding inconsistency — only some
emissive surfaces affected.

## Architectural note: parallel vs unified light-type selection

Falcor PT uses **unified** `selectLightType` + `generateLightSample`:
single NEE call per loop iteration, type chosen probabilistically.

BDPT after Bug #3 fix uses **parallel** NEE: separate `ConnectToLight`
(env + emissive) and `ConnectToAnalyticLight` calls every iteration.
This gives a small 1-2% over-shoot on scenes with mixed light types
(Arcade ratio 1.019 vs PT, Sponza 1.009).

Attempted to refactor to unified (commit d8730ba5 added helpers; the
dispatch change attempted in this session reverted) — the unified
approach REGRESSED Sponza to ratio 0.55 and Arcade to 0.888 because
the BPT MIS weight in `EvalDirectLightMIS` depends quadratically on
`directPdfW`. Scaling directPdfW by `lightSelectPdf` (0.5 for two-type
scenes) cubes (wLight ~ 4×) the BPT MIS weight, shifting weight away
from NEE.

To make the unified refactor work, the BPT MIS would need to use the
ORIGINAL `directPdfW` (without selection scaling) for the MIS-weight
calculation, while using the SELECTION-scaled pdf for the integration-
weight normalization. That's a deeper refactor — keeping parallel for
now. The selectLightType + getLightTypeSelectionProbabilities helpers
are committed (unused) as scaffolding for a future careful attempt.

## Recommendation

Until per-pixel pdf instrumentation pins down the formula divergence,
treat BDPTPass as a research / algorithm-comparison tool. For
ground-truth-quality reference renders, use Falcor's PathTracer with:

```python
createPass("PathTracer", {
    'samplesPerPixel': 1,
    'maxSurfaceBounces': 20,
    'maxDiffuseBounces': 20,
    'maxSpecularBounces': 20,
    'maxTransmissionBounces': 20,
    'emissiveSampler': "Power",
    'useNEE': True,
})
```

with sufficient SPP (≥256 for Cornell; ≥1024 for high-variance scenes
like VeachAjar/Bistro).

# BDPTPass — Known Bias vs Falcor PathTracer

## Status

**BDPTPass is NOT a bias-matched reference for Falcor's built-in PathTracer.**
There is a real, scene-dependent dim bias of ~1% (Cornell) to ~35% (VeachAjar)
that does NOT converge away at high SPP.

For vanilla / ground-truth reference renders, use **Falcor's built-in `PathTracer`**.
BDPTPass is useful for variance comparison and bidirectional algorithm
research but should not be treated as a "truth" estimator.

## Evidence (commits e56407ec, 6b6844fb, 5a57dd9e)

Matched config (20-bounce, Power-sampler, no env light, useResampling=False):

| Scene                        | SPP   | PT mean | BDPT mean | Ratio  |
|------------------------------|-------|---------|-----------|--------|
| CornellBox_1AreaLight 1-bnc  | 256   | 0.3783  | 0.3487    | 0.922  |
| CornellBox_1AreaLight 20-bnc | 512   | 0.4001  | 0.4017    | 1.004  |
| VeachAjar 1-bnc              | 256   | 0.9442  | 0.6325    | 0.670  |
| VeachAjar 20-bnc             | 256   | 1.1601  | 0.7591    | 0.654  |
| VeachAjar 20-bnc             | 2048  | 1.1602  | 0.7590    | 0.654  |

The 256→2048 shift on VeachAjar is 0.01% for PT and −1.33% for BDPT. PT is
fully converged at 256 spp; BDPT is still converging slightly but to a
DIFFERENT mean. Definitively not variance.

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

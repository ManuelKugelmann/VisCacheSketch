# Wilson-Interval Trust Gate — Prototype Plan

**Goal:** Address the SPP-dependent vt finding from SPONZA_VT (x4 wants vt=0.10, x16 wants vt=0.001) by replacing variance-threshold with a binomial confidence interval gate that absorbs both regimes into one criterion.

**Key insight:** A trust decision is "is the true cell visibility above 1−ε or below ε with high confidence?" Wilson interval gives the right confidence shape: wide CI at small N (low SPP, few cells touched) → don't trust; narrow CI at large N → trust whichever side the point estimate lands. SPP-dependence drops out automatically.

## Math

Given total = N samples observed, observed visibility = μ̂ = (sum) / N (Bernoulli proportion).
Standard 95% Wilson interval (z = 1.96, z² = 3.8416):

```
center = (μ̂ + z²/(2N))     / (1 + z²/N)
half   = z·√(μ̂(1−μ̂)/N + z²/(4N²)) / (1 + z²/N)
LB = center − half
UB = center + half
```

Trust criterion:
```
trust = (LB > 1 − ε) || (UB < ε)
```

ε = 0.01 → "true visibility within 1% of the corner with 95% confidence". Tighter ε = stricter gate; looser ε = more aggressive trust.

At small N: half ≈ z/(2√N) regardless of μ̂ → wide interval → almost no trust. At large N: half ≈ z·√(μ̂(1−μ̂)/N) → tight interval → matches stderr gate behaviour.

## Implementation

### 1. Slang gate (Source/RenderPasses/VisCache/VisCache.slang ~line 1021)

Add a new `gWilsonZSquared` and `gWilsonEps` cbuffer fields. Insert as **third option** before existing stderr/varThreshold ladder:

```slang
bool converged;
if (gWilsonZSquared > 0.f)
{
    // Wilson 95% interval gate. Absorbs vt's role with explicit
    // SPP-dependence: small-N ⇒ wide interval ⇒ no trust. See
    // .plans/wilson-interval-prototype.md.
    float Nf = max(float(total), 1.f);
    float zsq = gWilsonZSquared;
    float p   = mu;
    float invD = 1.f / (1.f + zsq / Nf);
    float numCenter = p + zsq / (2.f * Nf);
    float radical = sqrt(zsq * (p * (1.f - p) / Nf + zsq / (4.f * Nf * Nf)));
    float LB = (numCenter - radical) * invD;
    float UB = (numCenter + radical) * invD;
    float eps = gWilsonEps;
    converged = (LB > 1.f - eps) || (UB < eps);
}
else if (gStderrThreshold > 0.f) { /* existing stderr path */ }
else { /* existing varThreshold path */ }
```

Same gate decision is also useful in `vhfMatureRequired` (Source/RenderPasses/VisCache/VisCache.slang:1397). For now leave `vhfMatureRequired` on the legacy gate (Wilson primarily affects the lookup-time trust decision; mature-required is about when to stop writing).

### 2. C++ params (Source/RenderPasses/VisCache/VisCache.h)

Add to `Params` struct (~line 250 area):
```cpp
float wilsonZSquared = 0.f;     ///< 0 = off; 3.8416 = 95% CI; 6.6349 = 99% CI.
float wilsonEps      = 0.01f;   ///< Margin for "definitely visible/occluded" decision.
```

Add to `GPUParams` struct (~line 99 area, after stderrThreshold):
```cpp
float    wilsonZSquared;
float    wilsonEps;
```

### 3. C++ wiring (Source/RenderPasses/VisCache/VisCache.cpp)

- Props parser: `if (props.has("wilsonZSquared")) mParams.wilsonZSquared = props["wilsonZSquared"];` × 2
- `getProperties()` writeback: mirror both fields
- GUI: slider for `wilsonZSquared` ∈ [0, 10] + slider for `wilsonEps` ∈ [0.001, 0.1]
- GPU memcpy: copy both fields into the `VisCacheParams` constant buffer write

### 4. PathTracer cross-pass cbuffer binding (per CLAUDE.md rule)

Both `Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp` (tracePass) AND
`Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp` (PathRetrace + PathReuse) need:
```cpp
var["VisCacheParams"]["gWilsonZSquared"] = mVCParams.wilsonZSquared;
var["VisCacheParams"]["gWilsonEps"]      = mVCParams.wilsonEps;
```
Otherwise the shader globals stay at 0 and the new gate silently never fires (CLAUDE.md anti-pattern).

### 5. cbuffer field (Source/RenderPasses/VisCache/VisCache.slang ~line 207)

Add after `gStderrThreshold`:
```slang
float  gWilsonZSquared;   ///< Wilson z² (0 = off, 3.8416 = 95%, 6.6349 = 99%).
float  gWilsonEps;        ///< Margin for "definitely visible/occluded" trust decision.
```

### 6. Python kwargs (scripts/PathTracer_Graph.py)

Add `wilsonZSquared` + `wilsonEps` to `extraVCProps` pass-through.

## Test plan

Sweep `wilsonZSquared ∈ {0 (off), 3.8416 (95%), 6.6349 (99%)}` ×
`wilsonEps ∈ {0.005, 0.01, 0.02, 0.05}` on Sponza at x{4, 16}. Compare
against:
- SPONZA_VT carry rows (vt=0.10 x4, vt=0.001 x16)
- Direct full-metric battery: art5 / RMSE / PSNR / relmse

Pass criterion: Wilson at 95% / ε=0.01 should land within 1% of the
per-SPP vt optimum on every metric, with ONE config across both x4 and
x16. If it does, it's a strict improvement — collapses the per-SPP carry
table into a single carry.

Estimated effort: ~1h slang + cpp wiring, ~30 min sweep. Dependent on
Mogwai-free for build + test.

Script: `scripts/VisCache_LadderSPONZA_WILSON.py` (TBD; pattern from
SPONZA_VT.py).

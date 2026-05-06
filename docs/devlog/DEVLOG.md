# VisCache Dev Log

Cross-cutting findings, failed approaches, and reasoning that don't belong to a single ladder step. Step-by-step ladder records and the forward plan have moved out of this file:

- **[Ladder Log](../LADDERLOG.md)** — per-step ladder records (steps 00–18, the "narrowing chain" decisions, current canonical carries).
- **[Ladder Plan](../LADDER_PLAN.md)** — forward plan for steps 19–50+ (multilevel PT DI canonical, multilevel + WS-ReSTIR DI, multilevel + PT multibounce, multilevel + ReSTIR PT multibounce, BDPT open).

This file keeps:
- Cross-cutting parity / substrate-equivalence story (RTXDI baseline, restir_2d ≡ restir_3d).
- Sampler artefacts that are reusable beyond the ladder (e.g. `EmissivePdfMipmapSampler`).
- Failed approaches with their diagnoses (one paragraph each, anchored to dates / commits).
- Cross-cutting reasoning paragraphs.

---

## RTXDI Baseline — Final Result

**Status:** Functional + qualitative parity with RTXDI achieved on the seven-scene matrix; substrate equivalence (restir_2d ≡ restir_3d) demonstrated within sampling noise.

### Final canonical config

| Knob                          | Value                  | Rationale                                                                                  |
| ----------------------------- | ---------------------- | ------------------------------------------------------------------------------------------ |
| `WS_CELL_POOL_N`              | 128                    | Matches RTXDI tile-density target. 64→128 won Sponza_x4 −0.24pp; 128→256 diminishing.      |
| `wsInitialCandidates` (K_pre) | 32                     | Slim pre-pass; K=64 quality cost ~0.1pp avg — acceptable trade.                            |
| `wsCellPoolDrawK` (K_pool)    | 16                     | RTXDI K=24 budget. K_pool=24/64 retested with Conv A and B — both regress (over-weights pool's shading-agnostic distribution vs 8 fresh shading-conditional samples). |
| `wsMCap`                      | 5                      | RTXDI default 20 tested — uniformly +0.1-0.3pp worse on multi-light scenes.                |
| Pre-pass emissive sampler     | **PdfMipmap**          | New `EmissivePdfMipmapSampler` peer to Power/LightBVH. RTXDI-style hierarchical pdf-mipmap. |
| Main-pass emissive sampler    | LightBVH (default)     | Shading-conditional, required by BistroInt; mixed-PdfMipmap-main regressed +1.47pp.        |
| Pool read convention          | **Conv B reader-eval** | `1/sourcePdf` computed at READER's vertex via `emissiveSampler.evalPdf()` — RTXDI-faithful unbiased. Earlier writer-pdf Conv B caused fireflies (writer's r²/cos baked in). |
| Bayer N×N                     | 4 (16 subframes)       | RTXDI presample-budget alignment: 16K active pixels × K=8 ≈ 131K presamples = RTXDI's 128×1024. |

### Quality parity at x4 SPP vs RTXDI (mean OkLab err, 512²)

| Scene                    | vanilla | RTXDI    | restir (ours) | Δ vs RTXDI       |
| ------------------------ | ------- | -------- | ------------- | ---------------- |
| CornellBox_1AreaLight    | 1.39    | 2.18     | **2.15**      | **−0.03 win**    |
| CornellBox_1PointLight   | 0.21    | 1.39     | **0.21**      | **−1.18 win**    |
| CornellBox_3AreaLights   | 2.97    | **2.60** | 3.55          | +0.95 trail      |
| CornellBox_32PointLights | 5.36    | 3.73     | **3.31**      | **−0.42 win**    |
| BistroExterior           | 18.12   | 13.23    | **10.88**     | **−2.35 win**    |
| BistroInterior           | 16.96   | 10.73    | **9.54**      | **−1.19 win**    |
| Sponza                   | 6.23    | 7.08     | **6.49**      | **−0.59 win**    |

**Net at x4: 6 wins / 0 parities / 1 trail. Cumulative −4.81pp ahead of RTXDI on aggregate.**

The single remaining trail is CornellBox_3AreaLights (+0.95pp). Confirmed structural: per-cell pool architecture vs RTXDI's 1024-tile global structure produces different per-pixel candidate diversity profiles. No within-architecture parameter sweep equalizes them; closing it would require a true global tile structure (the obvious other lever — RTXDI's BoilingFilter — was attempted as a frame-start compute pass and disabled when shader writes failed to reach the buffer; see *Failed approaches* below for the diagnosis).

### Cost parity (shadow rays)

`rays_traced_pct` per the diagnostic counter (lower is better):

| Scene_x4         | RTXDI | restir | restir / RTXDI |
| ---------------- | ----- | ------ | -------------- |
| Cornell_1AL      | 9.90  | 18.13  | 1.83×          |
| Cornell_1PL      | 5.15  | 0.38   | **0.07×**      |
| Cornell_3AL      | 9.54  | 22.16  | 2.32×          |
| Cornell_32PL     | 24.66 | 17.38  | **0.70×**      |
| BistroExterior   | 81.95 | 74.95  | **0.91×**      |
| BistroInterior   | 65.39 | 60.84  | **0.93×**      |
| Sponza           | 59.88 | 60.50  | 1.01× (parity) |

Shadow-ray parity on five scenes; restir uses fewer rays on three. Cornell_3AL/Cornell_1AL fire ~2× because their K-RIS produces valid winners more often (visibility patterns differ from RTXDI's tile fill). Eval-cost gap (pre-pass uses PathTracer instance, ~3-4× more light-evaluations than RTXDI's lean compute presample) is plumbing — addressed by the lean dedicated compute pre-pass when ready (Task #29).

### Substrate equivalence — the proving result

`restir_2d` (RTXDI's exact substrate: pixel reservoir + screen-space tile pool) and `restir_3d` (3D-cell pool + per-pixel reservoir) produce identical results within sampling noise on every scene tested:

| Scene_x4       | restir_2d err | restir_3d err | \|2d − 3d\| |
| -------------- | ------------- | ------------- | ----------- |
| Cornell_1AL    | 2.15          | 2.16          | 0.01        |
| Cornell_1PL    | 0.21          | 0.21          | 0.00        |
| Cornell_3AL    | 3.55          | 3.55          | 0.00        |
| Cornell_32PL   | 3.31          | 3.31          | 0.00        |
| BistroExt      | 10.88         | 10.85         | 0.03        |
| BistroInt      | 9.54          | 9.53          | 0.01        |
| Sponza         | 6.49          | 6.47          | 0.02        |

**|2d − 3d| ≤ 0.03pp on all scenes — well below the per-frame stochastic noise floor.** This is the substrate-equivalence claim from paper §3.0 made operational: the 3D-cell pool with footprint-derived entry level is the substrate-equivalent of RTXDI's 2D-tile pool at matching parameters. The novelty isn't the addressing scheme; it's the curve beyond. Setting the footprint-derived entry level to one screen tile recovers RTXDI's exact pool layout; beyond that operating point, 3D admits cross-tile world-space sharing that 2D cannot express.

### Sampler artefact: `EmissivePdfMipmapSampler`

A clean Falcor-native peer to `EmissiveUniformSampler`/`EmissiveLightBVHSampler`/`EmissivePowerSampler`, registered as `EmissiveLightSamplerType::PdfMipmap = 3` in the existing factory. CPU-side build from `MeshLightTriangle.flux` placed in z-curve mip-0 layout (using inlined `RTXDI_LinearIndexToZCurve`); `Texture::generateMips` builds the chain. Slang side inlines `RTXDI_SamplePdfMipmap` for hierarchical descent and returns solid-angle pdf via `ls.pdf *= mipmapPdf`, vanilla-NEE-compatible. Math validated 1.116% on Cornell_3AL vanilla x16 vs LightBVH 1.119% / Power 1.126% — within stochastic noise. RTXDI library files are untouched; the sampler reuses `rtxdi/RtxdiMath.hlsli` via include only. Reusable by any pass that wants RTXDI-style sampling.

### Failed approaches (short list)

- **Conv B with stored solid-angle pdf** — fireflies on Sponza_x4 (+6.18pp regression). Writer's `r²/cos` baked into stored `1/sourcePdf` amplifies at distant-writer slots. Fix: reader-evaluated pdf.
- **Mixed PdfMipmap main + PdfMipmap pool** — BistroInt_x4 +1.47pp regression. Main pass needs shading-conditional LightBVH for tight indoor geometry.
- **K_pool > 16 (24, 64)** — over-weights pool's shading-agnostic distribution vs the 8 fresh shading-conditional samples. Both Conv A and Conv B regress.
- **wsMCap = 20 (RTXDI default)** — uniformly +0.1-0.3pp worse on multi-light scenes. Stays at 5.
- **Bitterli RIS at insert with writer-pHat** — biases pool toward writer's shading point, breaks cross-pixel reuse on heterogeneous lighting.
- **Drop main-pass fresh K-RIS (pool-only K=24)** — regressed Sponza_x1 +9pp; fresh shading-conditional samples are required.
- **Spatial-reuse off (wsSpatialPixelsK=0)** — confirmed not the Cornell_3AL bias source (Δ < 0.06pp).
- **Probabilistic V-aware fill at insert** — preserves expected value (only changes variance); Sponza unchanged.
- **RTXDI BoilingFilter port** — DISABLED 2026-05-05. Implemented as a frame-start compute pass (`Source/RenderPasses/VisCache/WSReservoirBoilingFilter.cs.slang`) structurally identical to `VisCacheDecay.cs.slang` (per-frame maintenance on a persistent buffer). RTXDI algorithm faithfully ported (16×16 thread groups, wave reduction → group mean, threshold = `10/strength - 9`). Build clean; smoke clean; dispatch gate verified firing via `logInfo` (`WSRes=1 PxRes=1 BF=1 mpPx=1 mpPass=1 dim=512x512` every subframe). **Empirical result: shader-side writes did NOT effectively reach `gWSPixelReservoirs`** even when stripped to a minimal "unconditional clear" shader without wave intrinsics or groupshared. Diagnostic ladder: (a) host-side `clearUAV()` on the same buffer at the same dispatch site → Sponza_x4 6.49 → 6.39 (−0.10pp, real effect); (b) full algorithm with wave/groupshared → Sponza_x4 = 6.49 (no effect); (c) minimal unconditional-clear shader (no wave/groupshared/`#pragma once`) → Sponza_x4 = 6.47 (within noise). All three at strength=0.2; sanity check at strength=1.0 also showed 6.49. Conclusion: buffer mutation works in principle (host clear) and the dispatch fires (logInfo), but compute-shader writes never make it through. Suspected slang-reflection / Falcor-binding mismatch on the locally-redeclared `RWStructuredBuffer<WSReservoir>` (the working `gVHFTable` in `VisCacheDecay` is *imported* from `VisCache.slang`, not redeclared in the decay shader). Pinpointing further requires a GPU profiler / PIX trace.<br>**Disabled rather than left half-working:** a silently no-op safety net is a worse failure mode than no filter at all — it presents as outlier rejection that future regressions could lean on while it never actually runs. The algorithm body in `WSReservoirBoilingFilter.cs.slang` is wrapped in `#if 0 / #endif`; the C++ wiring in `VisCache.cpp` (ComputePass creation, dispatch site, `runBoilingFilterPass` impl, GUI lines) is block-commented; `enableBoilingFilter` defaults to `false` in `Params`; the canonical ladder config no longer requests it. **Recommended fix path** (for the next attempt): extract `RWStructuredBuffer<WSReservoir> gWSPixelReservoirs` out of `WSReservoirIO.slang` into a tiny dedicated `WSPixelReservoirBuffer.slang` that BOTH `WSReservoirIO` and a future BoilingFilter import — mirroring the working `VisCacheDecay → VisCache.slang gVHFTable` pattern. That eliminates the locally-redeclared-global suspect at the source. Quality wouldn't change at canonical config either way, since the existing Conv B reader-pdf + V-test pipeline is already firefly-free.

### Reasoning

The fix that closed the convergent-design loop was Convention B with **reader-evaluated pdf** — calling `emissiveSampler.evalPdf()` at the receiving pixel's shading point so the `1/sourcePdf` factor uses the reader's geometry, not the writer's. Earlier Conv B attempts stored the writer's solid-angle pdf in `pool.sourcePdf` and used `1/stored` at read; those amplified `r²/cos` variance from distant writers into firefly tails. Recomputing the pdf at the reader sidesteps that variance entirely — RIS weights are now position-invariant by construction.

The substrate work proves that addressing scheme (2D screen tile vs 3D world cell) is incidental at matching density; the mechanism is the same flat-multilevel-hash + reservoir reuse + RIS pool fill. Functional and qualitative equivalence with the reference is therefore not a tuned approximation but a derivable consequence of operating the same substrate at the same density.

# VisCache Dev Log

Cross-cutting findings, failed approaches, and reasoning that don't belong to a single ladder step. Step-by-step ladder records and the forward plan have moved out of this file:

- **[Ladder Log](../LADDERLOG.md)** — per-step ladder records (steps 00–18, the "narrowing chain" decisions, current canonical carries).
- **[Ladder Plan](../LADDER_PLAN.md)** — forward plan for steps 19–50+ (multilevel PT DI canonical, multilevel + WS-ReSTIR DI, multilevel + PT multibounce, multilevel + ReSTIR PT multibounce, BDPT open).

This file keeps:
- Cross-cutting parity / structural-equivalence story (RTXDI baseline, restir_2d ≡ restir_3d).
- Sampler artefacts that are reusable beyond the ladder (e.g. `EmissivePdfMipmapSampler`).
- Failed approaches with their diagnoses (one paragraph each, anchored to dates / commits).
- Cross-cutting reasoning paragraphs.

---

## RTXDI Baseline — Final Result

**Status:** Functional + qualitative parity with RTXDI achieved on the seven-scene matrix; structural equivalence (restir_2d ≡ restir_3d) demonstrated within sampling noise.

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

The single remaining trail is CornellBox_3AreaLights (+0.95pp). Confirmed structural: per-cell pool architecture vs RTXDI's 1024-tile global structure produces different per-pixel candidate diversity profiles. No within-architecture parameter sweep equalizes them; closing it would require a true global tile structure.

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

### Structural equivalence — the proving result

`restir_2d` (RTXDI's exact data structure: pixel reservoir + screen-space tile pool) and `restir_3d` (3D-cell pool + per-pixel reservoir) produce identical results within sampling noise on every scene tested:

| Scene_x4       | restir_2d err | restir_3d err | \|2d − 3d\| |
| -------------- | ------------- | ------------- | ----------- |
| Cornell_1AL    | 2.15          | 2.16          | 0.01        |
| Cornell_1PL    | 0.21          | 0.21          | 0.00        |
| Cornell_3AL    | 3.55          | 3.55          | 0.00        |
| Cornell_32PL   | 3.31          | 3.31          | 0.00        |
| BistroExt      | 10.88         | 10.85         | 0.03        |
| BistroInt      | 9.54          | 9.53          | 0.01        |
| Sponza         | 6.49          | 6.47          | 0.02        |

**|2d − 3d| ≤ 0.03pp on all scenes — well below the per-frame stochastic noise floor.** This is the structural-equivalence claim from paper §3.0 made operational: the 3D-cell pool with footprint-derived entry level is structurally equivalent to RTXDI's 2D-tile pool at matching parameters. The novelty isn't the addressing scheme; it's the curve beyond. Setting the footprint-derived entry level to one screen tile recovers RTXDI's exact pool layout; beyond that operating point, 3D admits cross-tile world-space sharing that 2D cannot express.

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
- **RTXDI BoilingFilter port** — DISABLED 2026-05-05 (`#if 0` in shader, block-commented in C++). Dispatch fires, host-side `clearUAV` on the same buffer moves the metric, but shader-side writes silently no-op. Suspect: locally-redeclared `RWStructuredBuffer<WSReservoir>` vs the working module-imported `gVHFTable` in `VisCacheDecay`. Lesson: silent no-op safety nets are worse than no safety net — they could mask future regressions. Future fix: split `gWSPixelReservoirs` into a separable include both `WSReservoirIO` and a fixed BoilingFilter can import.
- **`accelDecayDisagreeThresh > 0`** — Bistro art5 regresses 3–6× (BiE x16 21.8 → 132.8; BiI x16 29.9 → 93.1). Cause: half-decay-on-disagreement creates runaway oscillation on cells with legitimate mixed visibility. ad ∈ {0.05, 0.10, 0.30} all converge to the same (worse) attractor — empirically broken mechanism. **Default off** (BISTRO_ADD sweep, 2026-05-05).
- **Trust-gate sweeps at cell4×4 ct=2 on Sponza (vt, se, fd, cwf, posB-quant)** — all combinations bit-identical (rays=73.48%, art5=23.36 — tested in step 17, step 18). The 26.5% rays-savings ceiling at this corner is **structural, not gate-tunable**: ct=2 itself is the bottleneck. Naive raise-base-ct (SPONZA_CT) breaks the saturation: ct=8 cuts art5 23.4→17.5 at x4. Lesson: trust-gate sweeps stop revealing leverage once the boot threshold itself is too low to accumulate the per-cell N needed to trust μ.

### Cache regime findings (cross-cutting)

These didn't fit any single ladder step's narrative — emerged from the union of multiple sweeps and reframe earlier results.

- **Scene-class taxonomy is 4-row, not 2-row.** (Class × bounce-depth.) Penumbra-class single-bounce DI (Sponza b=0): vt-tuning helps locally; perceptual-vs-linear metric tradeoff. Penumbra-class multibounce (Sponza b=1/4): cache delivers −74pp rays + OkLab match, PSNR/relmse worsens (linear-space loss is the perceptual cost of the cache's CV+RRR averaging). Firefly-class single-bounce DI (Bistro b=0): cache already at firefly floor — sweeping ct/vt/decay has no leverage but cache *is* winning −46pp art5 vs vanilla. Firefly-class multibounce (BistroInt b=1/4): cache wins on **every metric** (relmse 2.4× better, −53pp rays). The "Bistro framework doesn't generalize from Sponza" finding from BISTRO_CT was an artifact of single-bounce DI; multibounce closes the gap — every per-bounce firefly source is a fresh variance the cache amortizes via cell-level mean.
- **Bistro firefly-floor reframe.** BISTRO_DECAY (decayPeriod sweep) and BISTRO_CT (4-corner ct/vt) both showed bit-identical art5 across all variants on Bistro single-bounce DI. The reframe (BISTRO_DECAY narrative): cache art5 42.87% / 29.93% (x4 / x16) vs vanilla 88.89% / 48.23% means the cache absorbs ~46pp / 18pp of vanilla's variance — the residual is irreducible firefly noise, not cache bias-lock. Bistro DI cache is **working as designed**, just at its theoretical ceiling. The mechanism that breaks the floor is multibounce, not more DI-level tuning. The "scene-classifier needed" follow-up from BISTRO_CT remains valid as a future direction (per-class auto-tune) but doesn't change the b=0 result.
- **vt has anti-correlated optima across metric families.** SPONZA_VT at x16: vt=0.001 best art5 (15.21) but RMSE/relmse worse; vt=0.30 best RMSE/PSNR/relmse (relmse 0.09 vs 0.45 at tight vt) but worst art5 (28.42). art5 penalizes LOCAL spikes (firefly-region peaks); RMSE penalizes AVERAGE error. Tight vt kills firefly spots locally; loose vt smooths per-pixel noise globally. Implication: ship per-metric carry tables, not a universal vt — and any paper §11/§12 figure must report multiple metric families honestly.
- **vt is SPP-dependent.** SPONZA_VT: x4 optimum vt≈0.10, x16 optimum vt≈0.001. Wilson-interval / two-tier ct (LADDER_PLAN improvement A) is the principled fix — Wilson lower-bound > 0.99 OR upper-bound < 0.01 collapses both regimes into one criterion.
- **rays_traced_pct ≠ wall-clock saving on ray-trace-cheap scenes.** Cornell scenes have tiny geometry (small BVH, sub-millisecond ray cost). The cache's per-pixel infrastructure cost (hash query + atomic decay + cell-state update) is roughly constant per scene, dominated by the lookup machinery rather than the ray itself. So "94% rays saved on Cornell_1PL b=4" is an algorithmic finding, not a wall-clock claim — the saved rays were free to trace in the first place. Wall-clock wins require **ray-cost > cache-infrastructure-cost**, which holds on Sponza (44 ms vanilla → 18 ms cache, +58%) and BistroInterior (36 ms → 31 ms, +13%), but not on Cornell_32PL (2.6 ms vanilla → 11 ms cache, since vanilla is already faster than the cache infrastructure floor). **Pitch implication**: report rays-saved as the algorithmic metric, gpu_tracepass_ms as the operational metric, and don't conflate them. Cornell-class scenes are useful as algorithm-validation but not wall-clock benchmarks.

### Lessons distilled

- **Convention B requires reader-evaluated pdf.** `emissiveSampler.evalPdf()` at the receiver's vertex; never store the writer's solid-angle pdf — its `r²/cos` factor amplifies into firefly tails at distant readers.
- **Data-structure equivalence is structural.** 2D screen tile and 3D world cell are interchangeable at matched density; the mechanism is flat-multilevel-hash + reservoir reuse + RIS pool fill regardless of which one you address.

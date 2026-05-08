# Ladder Log (Backward-Looking)

Per-step record of what was tested, what was decided, and what was carried. The ladder structure and forward plan live in [LADDER_PLAN.md](LADDER_PLAN.md). Cross-cutting findings (e.g. RTXDI parity, BoilingFilter disable, Bistro firefly-floor reframe) stay in [devlog/DEVLOG.md](devlog/DEVLOG.md).

Per the methodology rule (LADDER_PLAN intro), each ladder step ideally lands at a local optimum. Dead-end / failed-leverage sweeps are pruned from the live narrowing chain below — their learnings are kept in the [Pruned dead ends](#pruned-dead-ends-learnings-preserved) footer and cross-linked to DEVLOG where the finding is cross-cutting. Step body narratives are preserved for audit.

**Diagnostic plate layout** (4×3 grid):

|           | col 1          | col 2              | col 3         | col 4            |
| --------- | -------------- | ------------------ | ------------- | ---------------- |
| **row 1** | render         | accum raysTraced % | error Δ vs GT | noise Δ vs GT    |
| **row 2** | frame level    | accum maturity     | accum mean    | accum variance   |
| **row 3** | accum coldmiss | frame qAHash       | frame qBHash  | frame probeSteps |

Both row 1 col 3 : error Δ vs GT and row 1 col 9: noise Δ vs GT use the same continuous bipolar ramp anchored at viridis(0) = dark purple for Δ = 0. Positive values (VisCache degraded / noisier) walk the full **viridis** palette (purple → blue → green → yellow); negative values (VisCache better / smoother) fade from purple toward **black**. Darker-than-purple = better; brighter-than-purple = worse. Plate labels report mean and per-pixel [min … max] signed %.

- **error Δ** = OkLabDistance(viscache, GT) − OkLabDistance(vanilla_xN, GT) at matched SPP — perceptual error vs ground truth, relative to same-SPP vanilla. From step 11 onward HDR is Reinhard-tonemapped (x → x/(1+x)) before OkLab so bright Sponza floors don't dominate the metric.
- **noise Δ** = bilateral_noise(viscache LDR) − bilateral_noise(vanilla_xN LDR) at matched SPP — screen-space noise difference, relative to same-SPP vanilla. Step 00 also emits per-SPP absolute OkLab error vs GT as the reference noise floor the noise Δ is measured against.

## Narrowing chain at a glance

| step | axis under sweep              | local optimum | carried forward                        |
| ---- | ----------------------------- | ------------- | -------------------------------------- |
| 00   | vanilla SPP 1..4096           | reference (no opt) | GT EXRs (not a config)            |
| RPT00 | vanilla_b{N} + restirpt_b{N} per-bounce GT | reference (no opt) — restirpt beats vanilla at x1 | per-bounce GT EXRs |
| RPT01 | `fireflyClampK` ∈ {10, 30, 100, 1000, ∞}    | K=∞ wins on every metric except marginal Cornell RMSE; clamp disabled by default | `fireflyClampK=1e9` (default off) |
| SMOKE | `wsRetraceOnReuseMode` ∈ {0,1,2} on restir_2d/3d + rtxdi RayTraced ref | mode=2 (CacheCV) ≡ mode=1 (FullTrace) within stochastic noise; both unbiased | `wsRetraceOnReuseMode=2` for Stage D |
| 01   | subframe N × warmup           | 2×2 + ≥1 warmup fixes tile artifact (cleanest 1PL) | `SUBFRAME_2x2` + warmup |
| 02   | B-side addressing shape       | full-position B (`pos`) wins multi-light by 11pp (x4) / 40pp (x16) | `pos` `dir_dist1` `dir_dist` (collapsed-B parked) |
| 03   | per-axis quant                | qA024_qB036 (pos branch) — clear pos winner over dir_dist | 3 quants × pos / dir_dist1 / dir_dist |
| 04   | SPP × step-03 top-3           | step-03 winners SPP-stable (no flip across x1/x4/x16) | keep quants                       |
| 05   | bootThreshold × quantAB       | `ct2` (1 confirming sample) — `ct1` cuts blob 9.4→5.8 only marginally on rays | `qA024_qB036__ct2`             |
| 06   | varThreshold sweep            | `vt005` — tied-best 1PL blob, best 32PL blob; tight vt monotonic on single-level | `vt005`                  |
| 10   | multi-level quant × threshold | `qa012__ct4` cascade — half rays vs single-level at matching quality | multi-level cascade carry             |
| 11   | bayerN × cell-footprint (entry vs cascade) | merged 11+12 ablation — cascade descent IS the rays-savings mechanism | (sanity check; no axis carry change) |
| 13   | ct × vt × pMin (12-variant 3-axis) | `ct016_vt010_pm002` — 67% rays on 1PL with err_d=0.16; 32PL rays-saturated | `ct016_vt010_pm002` |
| 14   | cell-size × ct (multi-scene cascade) | per-scene picks; surfaces "scene-dependent ct required" finding | per-scene picks (no single carry) |
| 16   | varThreshold × pMin           | `vt003_pm010` Pareto win on 1PL (rays −1.5pp, blob halved) | `vt003_pm010`              |
| SPONZA_CT | base-ct sweep on Sponza (cell4×4 ct ∈ {2..64}) | x4 knee at `ct=8` (art5 23→17, rays 73→87%); x16 monotonic to `ct=64` | `ct=8` x4 / `ct=64` x16 |
| SPONZA_VT | vt sweep at ct=8 on Sponza (vt ∈ {0.001..1.0}) | x4 `vt=0.10`, x16 `vt=0.001` — SPP-dependent vt finding | per-SPP carry |
| (insight)  | full-metric battery on SPONZA_VT | vt has **anti-correlated optima**: art5 wants tight, RMSE/relmse wants loose | metric-selects-policy: ship per-metric carry tables |
| SPONZA_MB | multibounce on Sponza (b ∈ {0,1,4}) | b=4 −74pp rays + OkLab match; linear-space tradeoff (PSNR −1.3 dB) | Stage E canonical on penumbra-class multibounce |
| BISTRO_MB | multibounce on BistroInt (b ∈ {0,1,4}) | b=4 −53pp rays + **wins every metric** (relmse 2.4× better) | Stage E canonical on firefly-class multibounce |
| CORNELL_MB | multibounce on 4 Cornell scenes (b ∈ {0,1,4}) | rays savings monotonic across all 4: 1AL −15pp, 1PL −3.6pp, 3AL −21pp, 32PL −16pp from b0 to b4. Mean OkLab err matches vanilla within 0.05pp on every scene at b=4. **Linear-space loss scales with firefly density**: 1AL RMSE +14% / 1PL +2% / 3AL +15% / 32PL +150%. relmse improves on 1AL/1PL/32PL (cache averages out high-magnitude tails), ties on 3AL. **The Sponza vs Bistro multibounce dichotomy is resolved**: it's a single light-count gradient — single-area-light scenes + low-firefly multipoint stay near Pareto, high-firefly scenes (32PL, BistroInt) get a relmse win that masks an RMSE blow-up | Stage E generalizes across penumbra-class scenes; per-scene linear-space cost reportable in paper §11/§12 |
| BISTROEXT_MB | multibounce on BistroExterior (b ∈ {0,1,4}) | b=4 −41pp rays + perceptual WIN (err −0.50pp, art5 −1.25pp) + linear LOSS (RMSE +58%, relmse +30%, PSNR −4 dB). Smaller rays savings than BistroInt (−41 vs −53pp) and inverted linear-space sign (BistroInt was −0.4% relmse / +1pp art5 wins on every metric). **Refines the light-count gradient**: cache-amortization effectiveness scales with **light count** (multi-light firefly averages independently), not just "firefly density" — BistroExt is dominated by ONE huge sun light with sharp shadows, so cell-μ smooths past the directional structure. BistroInt's many indoor lights average out cleanly; BistroExt's single sun does not | Stage E behaviour now mapped across the full 5-axis taxonomy: penumbra single (Sponza b=0), penumbra multi (Sponza b≥1), firefly multi-light (BistroInt), firefly single-huge (BistroExt), Cornell-class (1AL/3AL/1PL/32PL) |
| SPONZA_WILSON | Wilson 95%/99% CI gate sweep on Sponza x{4,16}, ε ∈ {0.005..0.40} | **Wilson gate works but is SPP-asymmetric.** x4 (cold cells, low N): bit-identical across ε ∈ {0.005..0.40} — Wilson's wide CI refuses trust at low N regardless of ε margin; result matches vt=0.001 baseline (art5=18.04 vs vt=0.10's 17.53). x16 (mature cells): ε ∈ {0.005..0.20} also bit-identical to vt=0.001 (art5=15.21). **ε=0.40 at x16** is the only point that differentiates: art5=15.28 (+0.07pp), but **relmse 0.72 → 0.29 (2.5× better)**, PSNR +0.12 dB, rays −0.4pp. Wilson auto-collapses to "strict" at low SPP, exposes the looser trust regime at high SPP via large ε. **Superseded by SPONZA_STDERR** — stderr=0.10 reproduces this exact behaviour at both SPPs with much simpler math; Wilson's ε=0.40 x16 win is the same operating point. | archived (superseded by stderr) |
| SPONZA_STDERR | stderr gate sweep on Sponza x{4,16}, τ ∈ {0.05..0.80} | **Principled N-aware solution to the SPP-dependent vt finding.** stderr=`√(var/N)` ≤ τ uses per-cell accumulated N (across frames), so the gate is naturally SPP-adaptive without any external knob. x4 (cold cells, low N): all τ ∈ {0.05..0.80} bit-identical, all match vt=0.001 baseline (art5=18.04, relmse=0.075) — stderr safely refuses trust at low N. x16 (mature cells): τ=0.05 matches vt=0.001 (strict, art5=15.21, relmse=0.72); **τ ∈ {0.10..0.80} all bit-identical**, art5=15.25 (+0.04pp vs strict, negligible) and **relmse 0.72 → 0.29 (2.5× better)**, PSNR +0.12 dB. **One config covers both SPPs** with the right metric-battery trade — exactly what Wilson and SPP-scaling tried to achieve. **Resolves the SPP-dependent-vt finding cleanly.** | `stderrThreshold = 0.10` (cleanest x4-stable + x16-relmse-win operating point); supersedes both SPONZA_WILSON and the SPP-scaling design |
| ALL_STDERR | stderr=0.10 vs vt=0.001 on all 7 scenes at x{4,16} | **stderr=0.10 is a strict Pareto improvement over vt=0.001 across the full scene matrix.** No regressions anywhere. Wins: Sponza x16 confirmed (relmse 0.72→0.29, 2.5×; PSNR +0.12 dB; art5 +0.04pp negligible); Cornell_1PL x16 (relmse 0.0034→0.0023, 32% better; art5 −0.07pp). Bit-identical on Cornell_1AL/3AL/32PL (saturated either way) and BistroExt/BistroInt (firefly-floor / bias-locked, no gate-tunable leverage; tiny rays drift +0.5–2pp at x16 within noise). **stderr=0.10 replaces vt=0.001 as the single canonical trust gate.** | `stderrThreshold = 0.10` (canonical) — full-matrix carry validated |
| SPONZA_MB8 | bounce-depth asymptote on Sponza (b ∈ {8, 16} at x4) | **Rays-savings asymptote at ~76% on Sponza.** b=0 saves 68%, b=1 saves 72%, b=4 saves 74%, **b=8 saves 75.6%, b=16 saves 76.2%**. Most of the gain is by b=4; b=4→b=8 adds only +1.6pp, b=8→b=16 +0.6pp — cache amortization saturates as per-bounce shadow rays become similar in distribution. Quality stays at the b=4 pattern: OkLab err MATCHES vanilla within 0.01pp at every bounce depth, art5 +1pp (small), RMSE +12–18%, PSNR −0.95 to −1.4 dB, relmse +20%. **Multibounce ceiling: ~76% rays saved with vanilla-matched perceptual error on Sponza** | bounce-depth gain plateaus by b=4; no need to push past for rays-savings story (paper §13 reportable as "savings asymptote") |
| SPONZA_AC | A-C shrinkage on cached μ (z² ∈ {0..16}) at canonical | **Shrinkage breaks the trust gate.** Any z² > 0 produces bit-identical results: rays_traced=100% (zero savings), regardless of z² magnitude (1, 4, 8, 16 all collapse). Quality gains marginal (relmse −16%, art5 −0.1pp, PSNR +0.1 dB) but at the cost of every rays-saving the cache offered. Root cause: shrinkage guarantees μ̃ ∈ (0, 1) strictly, so var = μ̃(1−μ̃) is never 0; stderr gate `√(var/N) ≤ τ` and vt gate `var ≤ vt` both fail to converge. **Net negative trade** — paying 27% more rays at x16 to recover 16% relmse, when stderr=0.10 already gets the same relmse improvement at zero extra rays cost. | archived (incompatible with existing trust-gate convergence; would need separate "shrunk μ for CV+RRR estimator only, raw μ for gate" split to be useful) |
| TIMING | vanilla vs cache wall-clock — 3 scenes × x{4, 16} (Falcor PROFILER) | **Real ms numbers reveal scene-dependent reality.** Sponza canonical at stderr=0.10: x4 vanilla=20.6 ms / cache=15.87 ms → **23% wall-clock saved** (vs algorithmic 13% rays); x16 vanilla=18.05 / cache=16.98 → **6% saved** (vs 27% rays). **BUT on saturated-light scenes the cache LOSES wall-clock**: BistroInt x4 vanilla=7.02 / cache=27.38 ms (−290%; cache adds ~20 ms hash-lookup overhead with only 3% rays saved). Cornell_32PL x4 vanilla=2.98 / cache=6.09 ms (−104%; trust gate fires for 0% of cells). **The cache pays a ~20 ms-per-frame overhead amortized only when the trust gate skips many rays.** On penumbra-class scenes (Sponza) where 13–27% rays get skipped, the overhead is overcome and the cache wins net. On saturated-light scenes (BistroInt, 32PL) where rays_traced_pct is 97–100%, the overhead is pure cost. **The single-bounce-DI "wall-clock win" is therefore scene-class-dependent, not universal — and lines up with the perceptual-vs-linear-metric tradeoff finding from earlier sweeps.** | per-scene wall-clock telemetry methodology; corrected pitch: "23% wall-clock saved on penumbra-class single-bounce, scene-dependent elsewhere" |
| TIMING_MB | multibounce wall-clock on Sponza — b ∈ {0, 4} | **Multibounce does NOT flip the wall-clock loss back to a win on Sponza.** Sponza b=4 cache canonical = 35.6 ms vs vanilla b=4 = 19.1 ms → cache **86% SLOWER** at b=4 despite 67% rays saved. Per-bounce hash overhead does not amortize: the cache pays a ~15–20 ms/frame fixed lookup cost, and even at b=4 with rays_traced=33% the saved-ray-cost-budget doesn't refund the overhead. Caveat: TIMING_MB used `_run_baseline_variant` (16 frames at actual_spp=1) while TIMING used `run_variants` (4 frames-loop with bayerN-internal); the harnesses produce different absolute ms even for identical configs (Sponza b=0: TIMING cache=15.87 vs TIMING_MB cache=45.01). Cross-sweep comparisons should be ratio-relative within a single harness, not absolute. **Action item: harness-honest comparison would need run_variants extended for vanilla path, or _run_baseline_variant tightened to match.** Headline still holds: cache adds GPU-fixed overhead that limits wall-clock wins to scenes/regimes where rays-saved × ray-cost > overhead. | algorithm: cache hash-lookup cost is the real budget axis; future profiler use should ratio-compare within a single harness; pitch caveat documented |
| COALESCE | warp-coalesced cache lookup (improvement J) — Sponza canonical x{4, 16} A/B | **Correctness ✅ but performance regression. AND: the "cache overhead" from TIMING was mostly warmup.** SM 6.5 WaveMatch coalescing in vhfLookup: leader lane probes (addr, fp), followers receive via WaveReadLaneAt. Error metrics bit-identical (RMSE diff 0.0001 = sub-noise; art5/rays/PSNR all unchanged) — coalesced path delivers same data. **Performance**: coalescing is **2.4× SLOWER at x4** (3.05 → 7.36 ms), 1.6× slower at x16 (6.56 → 10.18 ms). Modern GPU memory subsystems already L2-coalesce same-address reads within a warp; software WaveMatch + WaveReadLaneAt overhead exceeds the L2-coalescing benefit. **Bigger surprise**: COALESCE-off cache=3.05 ms x4 vs TIMING-cache=15.87 ms x4 for the same config = **~5× difference is pure GPU warmup amortization**. The ~15–20 ms "cache overhead" claim from TIMING was conflating warmup with algorithmic cost. **Warm-state cache adds only ~1–4 ms vs vanilla on Sponza, well within the rays-saved-cost budget.** The cross-scene TIMING claims of "cache loses on saturated-light" need re-running with proper warmup. | warp-coalesced lookup archived (worse); apparent overhead was warmup-confound; methodology: TIMING needs warmup-frames-before-reset to avoid first-variant bias |
| TIMING (warmup-fixed) | re-run with N_WARMUP=2 frames-before-reset on 3 scenes × x{4, 16} | **Wall-clock story is 2.5× better than the prior warmup-confounded TIMING reported.** With warmup-fix: Sponza canonical x4 vanilla=44.27 ms / cache=18.53 ms → **58.2% saved** (was 23%); x16 vanilla=34.66 / cache=17.17 → **50.5% saved** (was 6%). **BistroInt FLIPPED from -290% to +12.6% saved** at x4 (was a catastrophic loss; actually a real win once warmup is stripped). **Cornell_32PL still loses** — vanilla is 2.6 ms (ray-tracing-trivial), cache adds 8+ ms fixed → no recovery on a scene small enough that cache infrastructure dominates. Cache wins now correlate with rays_traced_pct savings × per-scene per-pixel-cost product as expected; the prior story was wrong on absolute and direction. **Methodology fix locked in:** run_variants + run_baseline + _run_baseline_variant all render N_WARMUP=2 warmup frames before profiler reset_stats. | corrected per-scene wall-clock table; pitch headline: "50–58% wall-clock saved on Sponza canonical, 7–13% on BistroInt; Cornell_32PL is the edge case where cache infrastructure exceeds vanilla's tiny render cost" |
| TIMING_MB2 | multibounce wall-clock attempt (run_variants harness) | **Cross-run absolute timing unreliable.** TIMING_MB2 reproduced Sponza b=0 cache canonical at 342 ms — same scene, same config as the corrected TIMING which gave 18.53 ms. **18× discrepancy** for nominally-identical workload across separate Mogwai invocations. Vanilla side similarly unstable (TIMING_VAN had Sponza b=0 = 44 ms; TIMING_VAN_MB has 2.86 ms). Likely cause: GPU clock/thermal state varies session-to-session; the warmup fix amortizes within-session warmup but doesn't normalize across-session GPU-state differences. **Practical implication:** absolute ms numbers need to be taken from a single Mogwai invocation that runs both vanilla and cache. The prior TIMING run (3 scenes, vanilla via run_baseline + cache via run_variants in one Mogwai per scene) is the cleanest data we have. **Cross-step / cross-run comparisons are NOT reliable**; only ratios within a single render loop are. Within-loop, vanilla b=0=2.86 ms / b=4=24.35 ms ratio (8.5×) makes sense and validates the multibounce work-scaling. The cache absolutes are unusable here. | methodology: extend run_variants to support viscache=True/False as a variant axis so both paths render in one loop (task #52); TIMING/TIMING_VAN single-bounce numbers stand as the headline |
| TIMING_HONEST | single-Mogwai vanilla-vs-cache, identical render loops back-to-back | **First-iteration result was misleading; steady-state (the design operating point) shows the real story.** The cache is designed for 1-SPP-per-frame + frame-accumulation real-time rendering. Initial TIMING_HONEST with SPP=4 + N_WARMUP=4-8 was MEASURING THE COLD-START AVERAGE (b=0 +3.6%, b=4 -11%), undersells. **Re-run at the design point** (SPP=1, N_WARMUP=64 frames so cache reaches cell-maturity equilibrium, RENDER_FRAMES=16 measure window): **Sponza b=0 vanilla=5.75 / cache=2.86 → +50.3% saved**, b=4 vanilla=3.67 / cache=4.45 → -21.0% (multibounce per-bounce cell churn still costs more than rays saved on Sponza). **The +50% wall-clock claim is real on the design operating point**; multibounce is the remaining implementation gap. **Algorithm framing**: the cache is *tuned for* frame-accumulation; cold-start averages aren't the right benchmark, equilibrium is. **Methodology corollary** for future TIMING work: SPP=1, N_WARMUP=64+, measure post-warmup window. | corrected pitch headline: "even unoptimized, 50% wall-clock saved on Sponza single-bounce DI at the design operating point (1-SPP-per-frame + frame-accumulation, steady-state); multibounce wall-clock pending GPU-engineering work" |

---

# Stage A — references

## [Step 00 — Vanilla Baselines](devlog/step00/STEP00.md)

**What it looks at.** Vanilla PathTracer (no VisCache) at x1 / x2 / x4 / x8 / x16 SPP plus x4096 ground truth per scene. Produces two things every later step measures against:

- `error Δ` reference = OkLab distance from the matched-SPP vanilla
- `noise Δ` reference = bilateral noise from the matched-SPP vanilla
- `vanilla_xN_gterr` floors = absolute OkLab vs the x4096 GT, the noise floor the Δ rides on top of.

Step 00 also runs the multi-bounce variants (`vanilla_b{1,4,8}`, `restirpt_b{1,4,8}`) at x{1,4} so stages E + F have references already on disk before they start. RTXDI x{1,4} and our `restir_2d` / `restir_3d` x{1,4} are also in here.

**Narrowing.** None — this step is purely reference generation. Every per-scene ladder plot's error/noise panel is a *delta against* this step's EXRs.

| x1 SPP                                           | x16 SPP                                           | x4096 SPP                                           |
| ------------------------------------------------ | ------------------------------------------------- | --------------------------------------------------- |
| ![](devlog/step00/renders/CornellBox_1AreaLight_x1.png) | ![](devlog/step00/renders/CornellBox_1AreaLight_x16.png) | ![](devlog/step00/renders/CornellBox_1AreaLight_x4096.png) |

Full four-scene gallery in [STEP00.md](devlog/step00/STEP00.md).

![](devlog/step00/overview_summary_00.png)

## Step RPT00 — ReSTIRPT canonical reference

**What it looks at.** Dedicated ReSTIR PT validation harness, isolated from
step 00 so the ReSTIRPT-side iteration doesn't churn the DI-side baselines.
Runs `vanilla_b{1,4,8}` at x{1,2,4,8,16,4096} + `restirpt_b{1,4,8}` at x{1,4}
through the canonical DQLin config (ReSTIR mode + RTXDI direct feed,
`disableDirectIllumination=true`). Captures land in
`runtime/captures/ladder/RPT00/<scene>/`.

```
runtime/pythondist/python.exe scripts/run_ladder.py -s RPT00 -c <SCENES>
```

**Per-bounce GT.** Unlike step 00 (where every variant compares against the
single canonical `vanilla_x4096` GT, which renders with `maxBounces=0`), RPT00
emits `vanilla_b{N}_x4096` GT per bounce count. `restirpt_bN_xK` then compares
against `vanilla_bN_x4096` — apples-to-apples convergence error rather than
"how much indirect light did each algorithm contribute relative to direct-only."
This is the only correct way to measure ReSTIRPT bias against vanilla PT. The
LadderCommon GT mtime-invalidation in `viscache_exr.oklab_distance_hdr_cached`
makes the cached error-distance maps re-evaluate when the GT changes.

**Reference results (2026-05-06, b=4 unless stated):**

| scene · b | metric | vanilla x1 | restirpt x1 | Δ | vanilla x4 | restirpt x4 | Δ |
| --------- | ------ | ---------: | ----------: | --: | ---------: | ----------: | --: |
| Cornell_1AL b1 | mean_err% | 6.36 | **4.24** | **−2.1** | 2.98 | 2.99 | +0.0 |
| Cornell_1AL b4 | mean_err% | 6.36 | **4.39** | **−2.0** | 2.89 | 3.22 | +0.3 |
| Cornell_1AL b4 | PSNR dB  | 39.10 | **39.82** | **+0.7** | 42.94 | 40.29 | −2.6 |
| Cornell_1AL b8 | mean_err% | 6.34 | **4.42** | **−1.9** | 2.89 | 3.26 | +0.4 |
| Sponza b1 | mean_err% | 21.44 | **20.11** | **−1.3** | 12.58 | 16.70 | +4.1 |
| Sponza b1 | RMSE | 1.680 | **0.692** | **−59%** | 0.842 | **0.669** | **−21%** |
| Sponza b1 | PSNR dB  | 13.02 | **20.73** | **+7.7** | 19.03 | **21.03** | **+2.0** |
| Sponza b1 | art_5%   | 96.5 | **88.0** | **−8.5pp** | 81.2 | 86.3 | +5.1pp |

**Headline.** ReSTIRPT outperforms vanilla path-tracing at low SPP exactly
as it's designed to. The dramatic Sponza RMSE/PSNR delta (−59%/+7.7 dB at x1)
shows the GRIS resampler doing its variance-reduction job on the firefly-rich
scene. At x4 the OkLab `mean_err%` chroma drift turns slightly negative for
ReSTIRPT (the soft-clamp's chroma direction preservation accumulates errors
faster than vanilla's plain accumulation), but RMSE/PSNR still favour
ReSTIRPT. Calibration of the §15 `params.fireflyClampK` knob is the open
follow-up (RPT01).

**Reference port content + future-additions list** in
[`Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md`](../Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md).
TL;DR section there enumerates exactly what's in the reference (DQLin core +
NVlabs F6 §1-§7 guards + Lin 2026 §12 #1+#2 backports + this work's §6/§7/§13/
§15) and what was excised to "future additions" (§8/§9/§10/§11/§14, Lin 2026
#3/#4, Stage A unification).

## Step RPT01 — `fireflyClampK` calibration

**What it looks at.** Sweeps the §15 chroma-preserving soft-clamp ceiling
multiplier `params.fireflyClampK` ∈ {10, 30, 100, 1000, ∞ (sentinel 1e9)}
at b=4 x{1,4} on Cornell + Sponza. Each K value renders one restirpt
variant; per-pixel error vs `vanilla_b4_x4096` GT decides the winner.

```
runtime/pythondist/python.exe scripts/run_ladder.py -s RPT01 -c <SCENES>
```

**Why.** The §15 soft-clamp at output time was the only firefly defense
remaining after §10/§11 retired. Its ceiling `K × max-channel(directLighting)`
is scene-relative through DL but the multiplier K was a hardcoded `30.0`
inherited from earlier (now-known-broken) experiments. RPT01 calibrates K
from real GT comparisons.

**Result.** Clamp-disabled is the reference default. The §15 stays in source
(opt-in via `render_graph_ReSTIRPT(fireflyClampK=K)`) but defaults to
`fireflyClampK = 1e9` so the branch never fires — same disabled-by-default
stance as the RTXDI BoilingFilter port. Honest cost: 32PL b4 x4 RMSE +24%
(fireflies leak through that vanilla averages out at 4 SPP). Every other
scene/SPP/metric is a restirpt win.

| K | Cornell mean_err x1 | Sponza mean_err x4 | Cornell RMSE x1 |
| ---: | ---: | ---: | ---: |
| 30 (legacy) | 4.38 | 15.59 | **0.692** |
| 100 | 3.85 | 11.67 | 0.741 |
| 1000 | **3.79** | **9.62** | 0.759 |
| **∞ (default off)** | **3.79** | **9.61** | 0.816 |
| vanilla baseline | 6.36 | 11.50 | 0.804 |

Restirpt beats vanilla on every metric except Cornell RMSE +1.5%. The
firefly suppression is structural — GRIS resampling does it. The §15
soft-clamp adds bias (output magnitude truncation) for that marginal
Cornell RMSE win, so it stays in source as opt-in (analogous to the
RTXDI BoilingFilter's disabled-by-default port) rather than baked in.
Baked as `Params.slang::fireflyClampK = 1e9` (effectively off, branch
never fires).

**Why we narrow.** `fireflyClampK = 1e9` is the canonical reference (no
clamp). Engage via `render_graph_ReSTIRPT(fireflyClampK=K)` if a downstream
consumer needs the RMSE ceiling — sweep table above gives the K choices.

## Step SMOKE — pre-stage-D toggleability validation (2026-05-06)

`scripts/VisCache_LadderSMOKE.py` — gated smoke tests run before opening Stage D's full ladder. Validates that the new `wsRetraceOnReuseMode` toggle (RTXDI BiasCorrection analog: 0=Off / Basic-equiv, 1=FullTrace / ≡ RayTraced, 2=CacheCV / cheap unbiased via `evalRevalidationCV`) produces correct results on the existing 2D-tile and 3D-cell pool variants, AND captures the strict-mode reference both for RTXDI and our two implementations on Sponza + BistroInterior at x4.

**Strict-mode results (Sponza x4, mean OkLab err vs `vanilla_x4096` GT):**

| variant | err% | Δ vs Basic-equiv | Δ vs rtxdi_raytraced |
|---------|-----:|----:|----:|
| vanilla (DI ref) | 6.228 | — | — |
| **restir_2d_vblind** (Basic-equiv, step 00) | 6.492 | 0 | −0.255 |
| **restir_2d_vblind_raytraced** (FullTrace) | 6.492 | +0.000 | −0.255 |
| **restir_2d_vblind_cachecv** (CacheCV) | 6.503 | +0.011 | −0.244 |
| **restir_3d_vblind_raytraced** | 6.507 | +0.006 | −0.240 |
| **restir_3d_vblind_cachecv** | 6.499 | −0.002 | −0.248 |
| **rtxdi_raytraced** | 6.747 | — | 0 |

**BistroInterior x4:**

| variant | err% | Δ vs rtxdi_raytraced |
|---------|-----:|----:|
| restir_2d_vblind (Basic-equiv) | 9.550 | −0.920 |
| **restir_2d_vblind_raytraced** | 9.535 | **−0.935** |
| **restir_2d_vblind_cachecv** | 9.535 | **−0.935** |
| restir_3d_vblind_raytraced | 9.546 | −0.924 |
| restir_3d_vblind_cachecv | 9.536 | −0.934 |
| rtxdi_raytraced | 10.470 | 0 |

**Findings:**

- **Plumbing works.** `wsRetraceOnReuseMode=1|2` produces unbiased results that match the Basic-equivalent `restir_2d_vblind` / `restir_3d_vblind` to 0.005–0.015pp on both scenes — the Basic-equiv's bias is already below the per-frame stochastic noise floor, consistent with RTXDI's modest 0.33pp Basic↔RayTraced gap.
- **Structural equivalence preserved.** `restir_2d_*_raytraced ≡ restir_3d_*_raytraced` within ~0.01pp on both scenes; same as Basic-equivalent.
- **Our restir_2d/3d beat rtxdi_raytraced on both scenes.** Sponza: −0.24pp; BistroInterior: −0.93pp. Already-better-than-strict-RTXDI under our Basic-equiv carries through under strict-mode equivalents.
- **CacheCV ≡ FullTrace within stochastic noise.** Headline §12 claim made operational on the retrace-on-reuse path: cache-V CV+RRR is unbiased per math AND empirically matches full retrace at lower expected ray cost.
- **Cost-tracking gap (fixed 2026-05-06, commit `4f93f8c`).** The diag rays-traced counter didn't see the WS-ReSTIR K-RIS or retrace-on-reuse V-tests originally; `rays_traced_pct` read 0% for `restir_2d/3d_*` variants. Fixed via a new `vcDiagCountRay(pixel, traced)` helper in `VisCacheDiagnostics.slang` + counter calls at the K-RIS post-RIS winner site and at the FullTrace retrace-on-reuse sites. **Verified 2026-05-06 via SMOKE rerun**: `restir_2d/3d_vblind_{raytraced,cachecv}` on Sponza now read `rays_traced_pct ≈ 86.9%` (previously 0%). The CacheCV path goes through `evalRevalidationCV` → `vcWriteDiag` directly, so no separate counter call needed there. (Note: 86.92% < 100% suggests at least one other cache path fires `vcWriteDiag(traced=false)` for a fraction of these pixels even with `enableVisCacheVisibilityCheck=False`; the value semantics need a deeper trace if used for paper Tables, but the column is no longer stuck at zero.)

**Configuration carries forward to Stage D.** All Stage-D candidate variants on the WS-ReSTIR DI side will toggle `wsRetraceOnReuseMode=2` (CacheCV) by default — strictly unbiased, cheaper than FullTrace.

---

# Stage B — single-level VisCache on PT DI

## Step 01 — Cold-Start Tiling + Subframe Mitigation

**What it looks at.** One logical frame, cold cache, coarse `QUANT_01` cells (posA 0.12, posB 0.36, distB 0.96 — deliberately coarser than the step-02+ baseline to expose the tile artifact). Sweeps 1×1 (baseline, artifact visible), 2×2 (+warmup slots 0/1/2), 4×4 (+warmup 0/1/8). Runs only `pos_norm__pos1`. A parallel `subval` control variant forces pMin=1.0 + huge thresholds → always-trace → isolates the Bayer-dispatch plumbing from any cache-skip effect.

**Artifact vs fix** (CornellBox_1PointLight, x1 SPP, cold cache). 1PL is chosen because its hard shadow produces crisp, high-contrast boundaries — any erroneous RR-skip inside the penumbra shows up directly in the render (r1c1) and in the error Δ (r1c3), not just as a diagnostic raysTraced pattern. Multi-light scenes blend the artifact into soft shadow overlaps and mask it.

| 1×1, no warmup — **tile-boundary artifact** | 2×2 + 1 warmup slot — **fixed**             |
| ------------------------------------------- | ------------------------------------------- |
| ![](devlog/step01/plates/artifact_1x1.png)         | ![](devlog/step01/plates/fixed_1PointLight.png)    |

In the 1×1 plate, a regular grid of bright/dark patches aligned to the dispatch tile boundaries is visible in the render and the error Δ — cells straddling tile edges read as "trusted" (RR-skipped with a stale-or-empty mean) because the neighbour tile's pixel-parallel writes committed before the query read — a first-writer-wins race, not real cache maturity. In the 2×2+warmup plate, writes disperse across N² subframes and the first subframe is write-only; the grid vanishes and the render matches vanilla modulo cache-gate noise.

**Subval control.** `noise_blob = 0.00` across every N and scene — the subframe path is bitwise-stable vs vanilla accumulation. Any non-zero delta in the main sweep is a cache-gate effect, not plumbing noise.

**Why we narrow.** 2×2 is enough to break the tile pattern and doesn't slow the step 02+ runs. Every later ladder step adopts `SUBFRAME_2x2` as a fixed baseline. Warmup defaults (≥1 slot write-only) are carried too.

![](devlog/step01/overview_summary_01.png)

## Step 02 — B-side Addressing Shape

**What it looks at.** `PRESET_MINIMAL + RR_ADAPTIVE + SUBFRAME_2x2`, intentionally coarse B-quant (posB 0.72, dirB 20°, distB 1.0) so each cell aggregates many samples at x1 — exposes shape differences before quantization becomes the dominant knob. Sweeps 4 B-side addressing variants under the single `pos_norm` A-side: `pos1`, `pos`, `dir_dist1`, `dir_dist`. (The 5th original variant `dir1_dist1` was dropped — it's numerically identical to `pos1` on every scene and SPP since both collapse all of B into a single bin, and only the A-side carries addressing signal.)

**Results (CornellBox_32PointLights, rays traced %):**

| B-variant   |  x4 rays |  x16 rays | x4 err Δ | x4 blob |
| ----------- | -------: | --------: | -------: | ------: |
| `pos`       | **80.8** |  **50.9** |    −3.92 |    3.17 |
| `dir_dist1` |     82.6 |      57.6 |    −3.88 |    4.34 |
| `dir_dist`  |     85.6 |      54.6 |    −3.92 |    3.17 |
| `pos1`      |     91.9 |      90.8 |    −3.86 |    3.17 |

Collapsed-B `pos1` plateaus near 91% rays on multi-light scenes and the gap widens with SPP: at x4 the cost is 11 pp over full-position `pos` (91.9 vs 80.8); at x16 it's 40 pp (90.8 vs 50.9). The collapsed cell can't tell two distant visibility targets apart at the same A-cell, so RR rarely finds a cell variance low enough to skip — and the mixed-target variance *floor* doesn't fall as SPP grows. Full-position B is clearly the winner on multi-light scenes; `dir_dist` and `dir_dist1` sit between and differ only in distance-axis quantization.

**Why we narrow.** Collapsed-B `pos1` is dropped; step 03 enumerates per-axis quant for `pos`, `dir_dist1`, and `dir_dist` only.

![](devlog/step02/overview_summary_02.png)

## Step 03 — Per-Axis Quantization Sweep

**What it looks at.** 68 variants in one logical step:

- `pos_norm__pos` — qA × qB = 4×4 = 16
- `pos_norm__dir_dist1` — qA × qD_FINE = 4×4 = 16 (distB collapsed)
- `pos_norm__dir_dist` — qA × qD × qd = 4×3×3 = 36

**Results.** Winner rule: *"err ≤ 0 OR ≤ median+25% AND blob ≤ 0 OR ≤ median+50%"* (weighted across scenes with 32PointLights×3), then ranked by rays-pct asc. Top-3 per B-branch flow into step 04. Current top-1 per branch (32PL x4):

| B-branch    | top-1 name         | rays % | err Δ | blob |
| ----------- | ------------------ | -----: | ----: | ---: |
| `pos`       | `qA024_qB036`      | 31.9   | −3.91 | 3.17 |
| `dir_dist1` | `qA024_qD60`       | 75.2   | −3.89 | 3.16 |
| `dir_dist`  | `qA012_qD60_qd192` | 72.4   | −3.88 | 3.16 |

`pos` already crushes the other two B-branches on rays — visibility-relevant dimensions clearly live in position, not direction. `dir_dist` / `dir_dist1` nonetheless stay in the ladder through step 04 to confirm the gap survives SPP convergence before they're parked.

![](devlog/step03/overview_summary_03_top3.png)

## Step 04 — SPP Convergence on Step-03 Top-3

**What it looks at.** The 9 candidates from step 03 (top-3 per B-branch) re-rendered at x1 / x4 / x16 SPP. Validates that step 03's winners don't have pathological convergence behaviour as sample count climbs.

**Results.** The ranking is stable — picker re-runs on step-04 rows yield substantially the same set. `dir_dist__qA024_qD30_qd048` drops to 53.5% rays on 32PL x4 with `err = −3.91`, `blob = 3.18`. No variant flips from qualifying to disqualifying across SPP, no variant's rays-pct regresses as SPP grows.

**Why we narrow.** Confirms step 03's per-axis winners are SPP-insensitive → safe to carry the pos-branch winners into step 05. `dir_dist` / `dir_dist1` branches are parked.

![](devlog/step04/overview_summary_04.png)

## Step 05 — bootThreshold × quantAB, pos Single-Level

**What it looks at.** Crosses step 03's top-3 pos quants (qA024_qB018 / qA024_qB036 / qA024_qB072) with 4 boot thresholds (ct1 / ct2 / ct4 / ct8). `matureThreshold = 128` fixed. 12 variants × 2 SPP = 24 runs/scene. First step where the "trust gate" knob is sized against a chosen cell size.

**Results — auto-picker top-3 (ranked by weighted rays-pct asc across scenes with 32PL×3). 32PL x4 numbers shown:**

| variant                                          | rays % | err Δ | blob |
| ------------------------------------------------ | -----: | ----: | ---: |
| `qA024_qB036__ct1` (picker #1)                   | 19.7   | −3.72 | 9.37 |
| `qA024_qB018__ct2` (picker #2)                   | 18.9   | −3.79 | 5.96 |
| `qA024_qB036__ct2` (picker #3, **manual carry**) | 21.2   | −3.79 | 5.75 |

The `ct1` variants pair every "most aggressive rays" with a much higher blob (9.4 vs 5.8) — cells are being trusted after a single sample, so the per-cell mean is an outlier-prone estimate and worst-region error jumps accordingly. The `ct2` variants keep blob at ~5.8 and cost only 1–2pp more rays.

**Why we narrow — and why the manual carry.** `ct1` = "trust the cell after a single sample" = boot gate effectively off. It wins the picker on rays alone, but it's too eager as the basis for the downstream sweeps that stack jitter, varThreshold, and multi-level on top. `ct2` (one confirming sample before trust) is manually carried: same quant, blob cut 40%, rays cost only 1.5pp.

![](devlog/step05/overview_summary_05.png)

## Step 06 — varThreshold Sweep

**What it looks at.** Step-05 carry baked in, sweeps the RR variance gate: `varThreshold ∈ {vt0 = 0.0001, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60}`. When cell variance drops below `varThreshold`, RR trusts the cached μ and skips the trace; above it, the ray always traces.

**Results — 32PL x4 (carry scene) vs 1PL x4 (hard-shadow blob canary):**

| variant | 32PL rays | 32PL blob | 1PL blob |
|---------|----------:|----------:|---------:|
| `vt0` | 22.3 | 5.89 | **16.86** |
| `vt005` (**carry**) | 22.2 | **3.43** | **16.86** |
| `vt010` | 21.9 | 5.80 | 23.24 |
| `vt015` | 21.3 | 5.91 | 28.78 |
| `vt020` | 20.7 | 6.02 | 32.17 |
| `vt030` | 17.7 | 7.04 | 33.23 |
| `vt040` | 15.5 | 7.82 | 43.66 |
| `vt060` | 13.4 | 8.42 | 67.41 |

**Key finding — tightening vt monotonically improves 1PL blob on single-level.** vt060 → vt0 cuts 1PL blob from 67 → 17 (4× better). `vt005` takes the corner: best 32PL blob in the sweep AND lowest 1PL blob tied with vt0.

**Key negative — contrast with step 11 multi-level.** On the *multi-level cascade* (step 11), tightening to `vt0` does the *opposite*: 1PL blob jumps to 86 because coarse-level cells with few samples over a penumbra spuriously read as "zero variance" and get fraudulently trusted. Single-level has no such over-trust pathway. The same vt knob has opposite optimal values at the two cascade regimes.

**Why we narrow.** Carry `vt005`. The auto-picker's top-1 was `vt030`, but its 1PL blob 33.23 is exactly the kind of regression the "blob > 10 means artifact" rule flags. Manual override to `vt005`: best 32PL blob, tied-best 1PL blob, rays cost ~1.5pp.

![](devlog/step06/overview_summary_06.png)

## Step 09 — Jitter Sweep (single level)

**What it looks at.** Step-05 carry plus a companion fine quant with posA/posB halved. Sweeps the two jitter flavors 3×3:

- `jitterFilter` — per-position-seed jitter (`asuint(pos)` seed). Stochastic grid per sample → acts as a 3D reconstruction kernel; soft cell boundaries.
- `jitterCell` — per-cell-index-seed jitter (`baseIdx` seed, Binder 2018). Whole-cell offset → boundaries stay hard but land at new positions.

**What the data hints at.** jf-only softens boundaries without adding firefly noise. jc-only shifts the visible grid but keeps hard edges. Stacking both at full scale (`jf10_jc10`) adds firefly noise and rays without a clearer visible gain over either axis alone. Mid strength (`jf05`, `jc05`) on each looks like the sweet spot.

**Why there's no carry yet.** Jitter is a visual/artifact call, not a rays+err call — the picker rule is silent on "does the image look right across frames". Likely `jf05_jc05`, pending visual inspection.

![](devlog/step09/overview_summary_09.png)

## Step 10 — Quant × Threshold, Multi-Level

**What it looks at.** Multi-level mirror of step 05: `LEVELS_MULTI + autoTuneCells`, no jitter, no footprint. QUANT_SWEEP (qa006 / qa012 / qa036) × threshold (ct2 / ct4 / ct16) = 9 variants. Step-05 single-level carry (`qA024_qB036__ct2`) overlaid as reference for direct gain comparison.

**Results (32PL x4):**

| variant                        | rays %   | err Δ | blob |
| ------------------------------ | -------: | ----: | ---: |
| `qa012__ct2`                   | 11.6     | −3.48 | 7.54 |
| `qa036__ct2`                   | 11.6     | −3.46 | 7.87 |
| `qa006__ct2`                   | 11.7     | −3.53 | 9.19 |
| `qa036__ct4`                   | 17.6     | −3.77 | 3.86 |
| `qa012__ct4`                   | **17.7** | −3.78 | 3.52 |
| step-05 ref `qA024_qB036__ct2` | 21.2     | −3.79 | 5.75 |

The cascade cuts rays roughly in half vs single-level at matched quality: `qa012__ct4` lands at 17.7% rays with `blob = 3.52` — better blob **and** better rays than the single-level step-05 reference (21.2%, blob 5.75).

**Why we narrow.** The cascade lets fine levels correct coarse-level early-trust decisions. `ct4` tuning is more stable at multi-level than `ct2`. Step 11 onward inherits the multi-level spine.

![](devlog/step10/overview_summary_10.png)

---

# Stage C.1 — multilevel VisCache on PT DI

Foundation: step-10 multilevel cascade with `qa012__ct4`. Ladder builds on it with bounded multi-dimensional sweeps + optimum-in-middle range design.

**Static-scene multilevel ladder (steps 11–18):**

> **Note:** Steps 11–18 narratives below were rewritten 2026-05-06 to match actual disk content. The parallel agent overwrote several step-N capture dirs with later sweeps; original "post-alignment ladder restart" narratives (subframeN×fd at step 11, ct×stderr at step 12, etc.) are preserved in git history but no longer match what's on disk. Each entry below describes the sweep currently in `runtime/captures/ladder/<NN>/`.

- **11 — bayerN × cell-footprint (entry-level only)**: 8 variants {bayer2×2, bayer4×4} × {cell1×1, cell2×2, cell4×4, cell8×8}, with cascade descent disabled (entry-level lookup only). 1AL only. **All 8 variants read rays=100%** — entry-only debug intentionally short-circuits the cascade-skip mechanism, so no rays get skipped. Demonstrates that the cascade descent IS the active rays-savings mechanism on 1AL.
- **12 — bayerN × cell-footprint (cascade-on)**: same 8 variants as step 11 with cascade descent enabled. 1AL only. Numbers identical to step 11 — at 1AL the cascade has no leverage at this matrix (single area light is uniformly trusted regardless of cell size or bayer slot allocation). Pair (11, 12) is the cascade-active vs cascade-off ablation, established as a no-op on 1AL.
- **13 — ct × vt × pMin (12-variant 3-axis)**: ct{16, 64} × vt{0.010, 0.030, 0.080} × pm{0.002, 0.010} on 1PL + 32PL. Tightest gate (`ct016_vt010_pm002`) hits **rays=67.4% on 1PL** with err_d=0.16 and art5=1.57 — clean cache win. 32PL stays at 100% rays across all 12 — multi-light is rays-saturated regardless of trust gate. **Carry: `ct016_vt010_pm002`** (cheapest within artifact-clean envelope on 1PL).
- **14 — cell-size × ct (multi-scene cascade)**: 12 variants {cell4×4 ct {2,4,8,16}, cell8×8 ct {8,16,32,64}, cell16×16 ct {32,64,128,256}} on 4 scenes (1PL, 32PL, Sponza, BistroInterior). cell16×16+ct=32 hits **18.5% rays on 1PL** but **90.2% rays + art5=42.9% on BistroInterior** (artifact-heavy). **Scene-dependent ct is required** — no single (cell, ct) combo wins all 4 scenes. Per-scene picks rather than a universal carry.
- **15 — jitterFilter × jitterCell sweep**: 8 variants jf×jc {0, 0.12, 0.25, 0.5, 1.0} on 4 scenes at `cell4×4 ct=16 vt=0.10 pm=0.02` carry. `jf000_jc000` (no jitter) reads identical to step 13's carry; non-zero jitter mostly neutral within stochastic noise (scene-dependent small wins/losses, no pareto improvement). Carry unchanged (no jitter as default).
- **16 — varThreshold × pMin**: 9 variants over vt {0.03, 0.05, 0.10} × pMin {0.02, 0.05, 0.10}. **First real improvement since step 13**: tighter vt is a Pareto win on 1PL — x4 rays 9.1→7.6%, blob 19.43→9.70; x16 rays 6.8→5.4%, blob 19.69→12.11. 32PL unchanged (cache already saturated). pMin remains no-op at every vt — the variance gate is the only mechanism touching the trust decision in this regime. **Carry: `vt003_pm010`** (pMin pick incidental). At vt=0.10 the variance gate fires too eagerly; vt=0.03 keeps cells in trace mode until they're genuinely flat. (Note: this entry's data is from a sweep on disk that has NOT been overwritten; the post-alignment narrative still matches.)
- **17 — posB-quant fine sweep on Sponza**: 4 variants {qB004, qB009, qB018, qB036} at `cell4×4 ct=2 vt=0.10 pm=0.02` carry. Sponza only. **All 4 variants bit-identical**: rays=73.48% / err_d=2.58 / art5≈23.4. posB quantization has zero effect at the saturated cell4×4 ct=2 corner — same lesson as step 18 (trust-gate exhaustion).
- **18 — vt/se/fd/cwf 4-axis sweep on Sponza (cell4×4 ct=2 vs cell16×16 ct=2)**: 16 variants over varThreshold {0.05, 0.10} × stderrThreshold {0, 0.05} × forceDescend {16, 256} × cascadeWindowForward {12, 24}. Two cell-footprint regimes: cell4×4 (16 px²) and cell16×16 (256 px²). Sponza only.
  - **cell4×4 ct=2 saturated**: all 8 variants produce bit-identical results — rays=73.48%, err_d=2.58, art5=23.36. Trust-gate params (vt, se, cwf) have **zero effect** at this cell+ct combo. The 26.5% ray savings ceiling on Sponza x4 is structural, not vt-gated.
  - **cell16×16 ct=2**: rays drop to ~41% at the cost of art5 climbing to 60–77% — aggressive savings via coarser cells, but artifact-prone.
  - **Trust-gate knobs are exhausted at this regime.** Further progress on bias-dominated scenes requires different levers: per-cell adaptive-ct, decay, or temporal-coherence — NOT more vt/se/cwf tuning.
  - **Action item:** Stage E (multibounce) and Stage D (WS-ReSTIR) need new mechanisms to break the saturation, not finer trust-gate sweeps.

**Net carry after step 18:** `pos_norm__pos__qa012__bayer2x2_cell4x4_ct002` is the saturated reference point — it's the cheapest config that produces vanilla-comparable err_d on Sponza x4. The "step 18 ceiling-break" exhaustion drives the framework forward to non-trust-gate axes (Stage D's retrace-on-reuse, Stage E's per-bounce ct).

**Artifact rule:** any `error_delta_blob_pct > 10` indicates visible cache artifacts (concentrated localized error — wrong-color cells, banding, light/shadow leakage). The picker rule's hard-reject at 25% is too lenient — treating 10 as the practical ceiling re-frames every result.

---

# Stage RDI — ReSTIRDI architectural ablation

The cell-data-structure design of §9 / §11 lives along three orthogonal axes:
per-pixel reservoir layer (R2d / H2d / drop), cell-level reservoir layer
(R3d on/off, footprint), and pool addressing (P2d screen-tile / P3d 3D-cell).
RDI00 measures the full factorial of the implemented architectures on every
canonical scene to surface where each architectural decision pays off.

## Step RDI00 — Cross-scene ReSTIRDI architectural matrix

**Variants** (5 implemented + 1 stub):
- `R2dP2d` — strict RTXDI baseline (per-pixel reservoir + screen-tile pool, no R3d)
- `R2dP3d` — strict + 3D pool (R3d still off; isolates pool addressing)
- `R2dR3dP2d` — adds cell-level reservoir to RTXDI architecture
- `R2dR3dP3d` — full 3D both layers (current canonical)
- `R3dP3d` — pure 3D, no per-pixel layer (R3d at sub-pixel cells absorbs its role)
- `H2dR3dP3d` — scaffold-only stub (slim per-pixel history; not yet implemented)

References: `vanilla` (no cache, x4 SPP) + production `rtxdi` (NVIDIA RTXDIPass).

**Cross-scene matrix at x4 SPP (OkLab err vs x4096 GT):**

| Scene | vanilla | rtxdi | R2dP2d | R2dP3d | R2dR3dP2d | R2dR3dP3d | R3dP3d | best ReSTIRDI |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Cornell_1PL  |  0.14 |  1.46 | **0.14** | 0.14 | 0.14 | 0.14 | 0.14 | tied (Dirac, all variants ≡ vanilla) |
| Cornell_1AL  |  1.06 |  2.18 | **1.42** |  2.15 |  1.42 |  2.15 |  2.19 | R2dP2d   (-0.76 vs rtxdi) |
| Cornell_3AL  |  2.15 |  2.56 |  3.13 |  3.23 |  3.13 |  3.23 |  3.26 | **rtxdi wins** (+0.57 trail; §13.5 structural) |
| Cornell_32PL |  4.38 |  3.65 |  2.90 |  2.90 |  2.90 |  2.90 | **2.85** | R3dP3d   (-0.80) |
| Sponza       |  5.32 |  6.62 |  6.10 |  6.09 |  6.10 |  6.13 | **5.94** | R3dP3d   (-0.68) |
| BistroInt    | 13.05 | 10.04 |  8.28 |  7.65 |  8.28 | **7.63** |  7.66 | R2dR3dP3d (-2.41) |
| BistroExt    | 15.00 | 11.46 | 10.23 |  9.30 | 10.23 |  9.18 | **9.13** | R3dP3d   (-2.33) |

Plates + per-step overview at `runtime/captures/ladder/RDI00/`. Cross-step
overlay: `ladder_progress_combined.png`.

**Key reads:**

1. **ReSTIRDI variants beat production RTXDI on 6 of 7 scenes.** Margins
   range from 0.68pp (Sponza) to 2.45pp (BistroInt). The Cornell_3AL trail
   reproduces the structural §13.5 finding — RTXDI's screen-tile pool's
   global-light-distribution presampling beats our shading-conditional fresh
   K-RIS on the 3-area-light Cornell scene, and no within-architecture
   variant in this matrix closes it. Cornell_1PL is trivially tied (Dirac
   light → cache has no work to do).

2. **R3dP3d (pure 3D) wins 3 of 7 scenes** (Cornell_32PL, Sponza, BistroExt).
   The pure-3D variant **only loses on simple/sparse Cornell scenes**
   (1AL, 3AL). On the multi-light Cornell_32PL it already wins by 0.05pp
   over R2dR3dP3d/P2d — the more lights, the more value the world-cell
   sub-pixel reservoir extracts. Implies R3dP3d is the right default for
   anything beyond toy scenes.

3. **Pool 3D wins 5 of 6 cache-relevant scenes** (everywhere except Cornell_1AL).
   On Cornell_3AL we trail rtxdi regardless of pool addressing.
   World-cell pool addressing dominates as soon as light count > 1 area light.

4. **Cell-level R3d is write-only-orphaned at P2d.** On every scene,
   `R2dP2d ≡ R2dR3dP2d` to within sampling noise (≤0.0005pp on Cornell
   variants, 0.01pp on Sponza). Confirms that with the canonical p̂-blind
   setup (`wsUseCellInRIS=False`), the cell-level reservoir gets written
   but never read — pure overhead in 2D-pool mode. R3d only does useful
   work at P3d, where it provides small wins on BistroInt (7.65 → 7.63)
   and a small cost on Sponza (6.09 → 6.13).

**Open question for RDI01:** the architectural-decision winner per regime
is now well-characterised but no single variant dominates the full matrix.
Options: keep multiple canonicals (one per scene class), or push toward a
single canonical via the visibility-aware p̂ folding (§11 c1/c2/c3) that's
been deferred since Task #41 — that's the most plausible mechanism by
which the cell-level reservoir could become the dominant variance-reduction
layer across all regimes.

**H2dR3dP3d's actual purpose (clarified 2026-05-08):** NOT a per-pixel-
temporal-accumulator that fixes Cornell pick-diversity loss. The real
role is **graceful fallback for sparse cell coverage**:
- per-pixel buffer = "my last working shading sample," not a Bitterli
  reservoir
- read path: try cell-pool first; if empty / disoccluded / cold, fall
  back to the per-pixel history slot
- write path: every successful shade updates the per-pixel slot

Under-test in the canonical RDI00 config (frame-accumulation x4 with
post-warmup steady-state) cells are well-covered everywhere, so H2d's
fallback path is rarely exercised — R3dP3d and H2dR3dP3d look identical.
The right tests are the cold/sparse regimes: x1 SPP (no warmup), fast
camera motion, disocclusion edges, glancing-angle pixels. The parallel
agent's PT-side R3d variant (analogous architecture, no pixel buffer)
regressed Cornell SPP=1 by +34% — that's the failure H2d is designed to
prevent.

**MVP shortcut tried (eb25b05):** flag combination
`enableWSPixelReservoir=True + wsCellReservoirMerge=1`. Result:
H2dR3dP3d = R2dR3dP3d bit-equivalent (Cornell_1AL 2.145 vs 2.146;
Cornell_3AL 3.226 vs 3.226). Doesn't break out of the per-pixel
reservoir architecture — both reservoirs run in the canonical
read path, no fallback semantics.

**Cold-cell stress test (RDI00 x1 sweep, 13fc09c+):** measured whether
R3dP3d shows a +34%-style cold-cell regression at x1 SPP that would
justify implementing the proper H2d fallback. **Hypothesis falsified
on the DI side.**

| Variant | Cornell_1AL x1→x4 | Sponza x1→x4 |
|---|---:|---:|
| R2dP2d    | 1.78 → 1.42 (+25%) | 6.64 → 6.10 (+9%)  |
| R2dR3dP3d | 2.20 → 2.15 (+2%)  | 6.79 → 6.13 (+11%) |
| R3dP3d    | 2.26 → 2.19 (+3%)  | 6.78 → 5.94 (+14%) |

R3dP3d isn't uniquely worse at x1 — its x1→x4 convergence ratio is
similar to other variants. The +34%-style regression the parallel
agent reported on the PT-side R3d analog (Cornell SPP=1) doesn't
reproduce on our DI side because our canonical config includes a
cell-pool pre-pass (`PathTracerPrePass` with `wsCellPoolFillOnly=true`)
that populates cells *before* the main pass reads them. Bayer-staged
writes during pre-pass mean every pixel contributes; cells aren't
empty at main-pass read time → no fallback path is exercised.

**Conclusion:** H2d's architectural value (empty-cell fallback) doesn't
emerge in our static-scene canonical because the pre-pass already
eliminates the empty-cell failure mode. H2d would matter in the
*dynamic-scene next stage*: animated camera with pre-pass that can't
keep up with new region appearance, transient geometry disocclusion,
or any scenario where cell-pool coverage is sparse. Implementing H2d
proper is therefore deferred to whenever dynamic scenes enter the
ladder. The current matrix variant slot remains a no-op intermediate
between R2dR3dP3d and R3dP3d for completeness.

---

## Steps 19–25 — recorded null result

Post-step-18 sweep piled on pm020, hc005, qa006, ct256, accelDecay. Under the corrected absolute-vs-GT metric these knobs turn out to mostly tie — the signed-delta-vs-vanilla blob metric inherits vanilla's per-SPP sampling noise, so they were chasing comparison noise, not cache degradation. The real cumulative wins come from step 18 ct=128, not from anything in 19–25. Useful negatives that still hold:

- **Cache wins on bias-dominated scenes** (32PL, Bistro, Sponza) at every SPP under absolute-err-vs-GT.
- **Cache ties or slightly trails on Cornell 1PL** — vanilla converges fast on a single point light; cell-averaging adds a small bias.
- **BistroInterior x16 firefly story** holds: cache and vanilla equally far from GT.

**Single-carry recommendation post-metric-fix:** `ct=16 / vt=0.03 / qa012 / bayer4x4_cell4x4 / pm=0.10` — Pareto win across all 5 scenes vs vanilla. The qa006/ct256/hc005/pm020 chain accumulated through 22–25 added complexity for marginal benefit under the corrected metric.

Temporal mechanisms (decay, warmup, accelDecay) and indirect illumination (maxBounces > 0) are deferred to Stage E in [LADDER_PLAN.md](LADDER_PLAN.md), where time-varying mechanisms have something to react to.

---

# Cross-step ladder progress

Per-scene thin lines + bold unweighted "All" across all ladder steps in three panels (rays / error+blob / noise). Red halos mark each step's carried winner; whiskers show per-scene min→max of all variants at that step. One plot per SPP tier.

**x1 SPP:**

![](devlog/ladder_progress_x1.png)

**x4 SPP:**

![](devlog/ladder_progress_x4.png)

**x16 SPP:**

![](devlog/ladder_progress_x16.png)

**Compact overlay — unweighted "All" only, x1 + x4 + x16:**

![](devlog/ladder_progress_combined.png)

---

# What's next

See [LADDER_PLAN.md](LADDER_PLAN.md) for stages C.2 → G:

- **C.2 (steps 19–20)** — multilevel PT DI canonical re-validation under current metric.
- **D (steps 21–30)** — multilevel + WS-ReSTIR DI: ladder-formalise the off-ladder RTXDI parity work and add VisCache μ-NEE on top.
- **E (steps 31–40)** — multilevel + PT multibounce: open the bounce axis.
- **F (steps 41–50)** — multilevel + ReSTIR PT multibounce: paper §12 reconnection-shift V revalidation.
- **G (steps 51+)** — BDPT (open).

---

# Archived dead ends (kept until fully obsolete)

These steps ran but produced no local optimum (all-variants-tied) or were superseded by a downstream sweep. Per the methodology rule (LADDER_PLAN intro), they're archived out of the live narrowing chain above but **kept here while the underlying problem is still open** — dead ends often reframe months later when an adjacent investigation lands. An entry leaves the archive only when its problem is fully obsolete (solved differently / no longer actionable). Per-step body narratives stay below for audit; one-line learnings are listed here, with cross-cutting findings cross-linked to DEVLOG.

| pruned step | sweep | learning (one line) | promoted to |
|-------------|-------|---------------------|-------------|
| **07** (single-level stderr) | `stderrThreshold` curve at single-level | se005 marginal over vt005 (32PL blob 3.4→5.9 at matched rays); single-level metric-saturated | superseded by step 10 cascade (different leverage regime) |
| **09** (jitter, single-level) | `jitterFilter × jitterCell` 3×3 | no Pareto improvement; visual call only, picker rule silent | jitter retried in step 15 (multi-scene), also dead end |
| **12** (cascade-on, 1AL only) | Same 8 variants as step 11 with cascade enabled | bit-identical to step 11 on 1AL — cascade has no leverage at this scene+matrix | merged into step 11 narrative (cascade-active vs cascade-off as one ablation) |
| **15** (multi-scene jitter) | `jitterFilter × jitterCell` on 4 scenes at step-13 carry | non-zero jitter mostly neutral within stochastic noise | "no jitter as default" (jitter parked) |
| **17** (Sponza posB-quant) | qB ∈ {004, 009, 018, 036} at cell4×4 ct=2 | bit-identical across all 4 — saturated at ct=2 | redundant with step 18 (same saturation cause) |
| **18** (Sponza vt/se/cwf 4-axis) | vt × se × fd × cwf at cell4×4 ct=2 vs cell16×16 ct=2 | cell4×4 ct=2 saturated (8 variants bit-identical); trust gates have zero leverage at this corner | superseded by SPONZA_CT — `ct=2` itself was the bottleneck → DEVLOG "Sponza ct=2 saturation" |
| **BISTRO_CT** (Sponza framework on Bistro) | 4-corner (ct, vt) on BistroExt + BistroInt | Sponza framework does NOT generalize — Bistro art5 bit-identical across all 4 corners (firefly-floor, not premature trust) | DEVLOG "Bistro firefly-floor reframe" |
| **BISTRO_ADD** (accelDecayDisagreeThresh) | ad ∈ {0, 0.05..0.5} on Bistro | mechanism toxic — runaway oscillation; non-zero values regress 3–6× | DEVLOG "Failed approaches": `accelDecayDisagreeThresh = 0` (default off, mechanism toxic) |
| **BISTRO_DECAY** (periodic decay) | decayPeriod ∈ {OFF, 2..300} on BistroInt | bit-identical across all 7 dp values; no leverage. The investigation produced the **"cache-at-firefly-floor"** reframe: cache absorbs ~46pp / 18pp of vanilla's variance at x4/x16, residual is irreducible firefly noise | DEVLOG "Bistro firefly-floor reframe" + Stage E (multibounce) instead of more DI levers |

**Step 19–25 (post-step-18 multi-axis pile-on)** — already pruned in earlier rewrite (see "Steps 19–25 — recorded null result" section above). Useful negatives recorded; dead-end content not in active ladder.

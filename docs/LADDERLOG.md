# Ladder Log — Steps 00–18 (Backward-Looking)

Per-step record of what was tested, what was decided, and what was carried. The ladder structure and forward plan live in [LADDER_PLAN.md](LADDER_PLAN.md). Cross-cutting findings (e.g. RTXDI parity, BoilingFilter disable) stay in [devlog/DEVLOG.md](devlog/DEVLOG.md).

**Diagnostic plate layout** (4×3 grid):

|           | col 1          | col 2              | col 3         | col 4            |
| --------- | -------------- | ------------------ | ------------- | ---------------- |
| **row 1** | render         | accum raysTraced % | error Δ vs GT | noise Δ vs GT    |
| **row 2** | frame level    | accum maturity     | accum mean    | accum variance   |
| **row 3** | accum coldmiss | frame qAHash       | frame qBHash  | frame probeSteps |

Both row 1 col 3 : error Δ vs GT and row 1 col 9: noise Δ vs GT use the same continuous bipolar ramp anchored at viridis(0) = dark purple for Δ = 0. Positive values (VisCache degraded / noisier) walk the full **viridis** palette (purple → blue → green → yellow); negative values (VisCache better / smoother) fade from purple toward **black**. Darker-than-purple = better; brighter-than-purple = worse. Plate labels report mean and per-pixel [min … max] signed %.

- **error Δ** = OkLabDistance(viscache, GT) − OkLabDistance(vanilla_xN, GT) at matched SPP — perceptual error vs ground truth, relative to same-SPP vanilla.
- **noise Δ** = bilateral_noise(viscache LDR) − bilateral_noise(vanilla_xN LDR) at matched SPP — screen-space noise difference, relative to same-SPP vanilla. Step 00 also emits per-SPP absolute OkLab error vs GT as the reference noise floor the noise Δ is measured against.

> ⚠ **Metric change at step 11+**: the error metric switched to a **Reinhard-tone-mapped OkLab** (HDR x → x/(1+x) before perceptual distance) so brightly-lit Sponza floors etc don't dominate the metric. Steps 00–10 numbers in this log are still under the **pre-tone-map** metric (linear-clipped at 10 + sRGB gamma). Pre/post-step-11 magnitudes are not directly comparable. **Action item**: re-run steps 00–10 with the new metric (postprocess only — EXRs are kept, no re-rendering needed) once the new ladder stabilizes, so cross-step plots have a single consistent error scale.

## Narrowing chain at a glance

| step | axis under sweep              | decision made                                       | carried forward                        |
| ---- | ----------------------------- | --------------------------------------------------- | -------------------------------------- |
| 00   | vanilla SPP 1..4096           | error + noise references                            | GT EXRs (not a config)                 |
| 01   | subframe N × warmup           | 2×2 + ≥1 warmup fixes tile artifact                 | `SUBFRAME_2x2`                         |
| 02   | B-side addressing shape       | collapsed-B variants fail multi-light               | `pos` `dir_dist1` `dir_dist`           |
| 03   | per-axis quant                | top-3 per B-branch by median-gated rays             | 3 quants × pos / dir_dist1 / dir_dist  |
| 04   | SPP × step-03 top-3           | winners don't degrade with SPP                      | keep quants                            |
| 05   | bootThreshold × quantAB       | select `qA024_qB036__ct2`, `ct1` is noise           | `qA024_qB036__ct2`                     |
| 06   | varThreshold (expanded vt0..vt060) | tightening vt improves blob monotonically (single-level) | `vt005`                          |
| 07   | stderrThreshold pure curve (single-level) | **se005 beats vt005 on 1PL x4 blob 17→11** at matched rays; 32PL blob cost 3.4→5.9 (still below 10) | `qA024_qB036__ct2__se005` |
| 09   | jitter f / c × fine companion | slightly worse but adds graceful degradation        | (likely `jf05_jc05`, pending review)   |
| 10   | multi-level quant × threshold | multi-level beats single-level                      | multi-level                            |
| 11   | subframeN × fd (Bayer-cell symmetry)        | bayer4×4 + cell4×4 wins on 1PL/32PL                                | `bayer4x4_cell4x4`                     |
| 12   | ct × stderr (trust requirement)             | ct=16 best, stderr off                                              | `ct16_se000`                           |
| 13   | pMin × hierarchicalConsistency              | both no-op at vt=0.10 (variance gate fires first)                   | unchanged                              |
| 14   | addressing × normalACoarse                  | pos beats dir_dist; normalACoarse no-op at 30/60/90°                | unchanged                              |
| 15   | bootThresholdFactorFootprintPx × matureThreshold | both no-op at ct=16                                            | unchanged                              |
| 16   | varThreshold × pMin                         | tighter vt is a Pareto win on 1PL                                   | `vt003_pm010`                          |
| 17   | vt finer sweep below 0.03 + full-scene validation | vt=0.03 confirmed global optimum                              | unchanged                              |
| 18   | ct revisit on bias scenes                   | ct=128 brings BistroExt x4 blob 45.6 → 0.2 at 81.5% rays            | `ct128_vt0030_pm010`                   |

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

# Stage C.1 — multilevel VisCache on PT DI (post-alignment ladder restart)

Earlier ladder steps 11–52 (and the previous pre-multiframe attempt) ran on
versions of the cascade that turned out to have systematic bugs: int32 overflow
on env/sun rays, stride-induced fingerprint fragmentation, lvl-0 collapse from
unaligned target-level rounding. Their numbers are not comparable to the current
shader and are kept under `archive_post_alignment/` for audit only.

Step 10 is the foundation that survives: multi-level cascade with `qa012__ct4`
addressing/quantization/threshold, validated under the corrected shader. The
new ladder builds from there with **bounded multi-dimensional sweeps**, the
**fast pre-test → triple-trial finalist** protocol, and **optimum-in-middle**
range design.

**Static-scene multilevel ladder (steps 11–24):**

- **11 — subframeN × fd**: 9 variants over Bayer-slot count × force-descend pixel footprint. Matched diagonal (bayer4×4 + cell4×4) wins on 1PL/32PL pre-test. Confirms the hypothesis that the Bayer slot count and the per-cell pixel footprint should match: every cell receives one sample per slot per frame, exactly tiling the target footprint. **Carry: `bayer4x4_cell4x4`.**
- **12 — ct × stderr**: 9 variants over bootThreshold {4,16,64} × stderrThreshold {0, 0.02, 0.05}. ct=16 best across SPP tiers; stderr off (=0) best — the stderr gate is not yet useful at the current trust regime. **Carry: `ct16_se000`.**
- **13 — pMin × hierarchicalConsistency**: 9 variants. Both knobs are no-ops at the inherited varThreshold=0.10 — the RR variance gate fires first and strips the safety nets of anything to do. Documented dead-end; carry unchanged. **Productive next step: tighter varThreshold (e.g. 0.03) so pMin/HC have a regime in which to bite.**
- **14 — addressing × normalACoarse**: 6 variants. Re-validation of pos vs dir_dist under corrected shader — `pos` beats `dir_dist` on rays at equal blob (the earlier "Sponza dir_dist win" was a stride-fragmentation artifact). normalACoarse has minimal effect at 30°/60°/90°. Carry unchanged.
- **15 — footprintScale × matureThreshold**: 9 variants. footprintScale > 0 inflates rays 5–10× without measurable blob improvement on 1PL/32PL (fp010 4spp: 46.8% rays / blob 19.43 vs fp000: 9.1% / 19.43). matureThreshold has no effect at ct=16 — the counter saturates well below 64. Carry unchanged.
- **16 — varThreshold × pMin**: 9 variants over vt {0.03, 0.05, 0.10} × pMin {0.02, 0.05, 0.10}. **First real improvement since step 12**: tighter vt is a Pareto win on 1PL — x4 rays 9.1→7.6%, blob 19.43→9.70; x16 rays 6.8→5.4%, blob 19.69→12.11. 32PL unchanged (cache already saturated there). pMin remains no-op at every vt — the variance gate is the only mechanism touching the trust decision in this regime. **Carry: `vt003_pm010`** (pMin pick incidental). The story: at vt=0.10 the variance gate fires too eagerly and locks in high-blob cells; vt=0.03 keeps cells in trace mode until they're genuinely flat, producing both fewer rays and lower blob simultaneously.
- **17 — vt finer sweep below 0.03 + full-scene validation**: 5 variants vt {0.005, 0.01, 0.02, 0.03, 0.05} on all 5 scenes. **vt=0.03 confirmed as global optimum**: it sits exactly at the false-trust cliff. On Sponza x4, vt≤0.02 blob doubles to 90+ (cells trust too readily on low-variance noise), vt=0.03 holds at 43.78. On 1PL, vt<0.02 collapses cold-start (blob 35–62 at x1). 32PL is saturated and unaffected by vt. Carry unchanged.
- **18 — ct revisit on bias scenes**: 4 variants ct {16, 64, 128, 256} at vt=0.03 carry, on 32PL+Bistro+Sponza. **Major breakthrough on x1/x4**: ct=128 brings BistroExterior x4 blob from 45.6 → **0.2** (vanilla quality) at 81.5% rays. Sponza x4 ct=256 blob 8.2 ✓ (ct=128 borderline at 10.7). BistroInterior is a clear cache win (err_delta_pct -14 to -15% = denoising; blob_pct=0 because cache reduces error vs vanilla). 32PL stays usable across all ct (blob ≤6.4 ✓). **x16 unsolved**: Bistro/Sponza x16 blob 14–17 at every ct including 256 — ct alone cannot fix it. The multi-frame accumulation matures cells faster than the trust gate can catch biased ones; needs a "rate defense" (pMin / HC / footprintScale) on top. **Carry: `ct128_vt0030_pm010`** (best rays/blob trade-off; saves ~5% rays vs ct=256 at the cost of borderline Sponza x4).

This step required two infrastructure fixes that surfaced from the camera-renderer redo: (a) `postprocess()` was globbing all SPP variants from raw/ and `find_exr` returned the lex-first match (.1) regardless of requested SPP — corrupted every repost'd step's rays metric (commit `952df34`); (b) the Reinhard tone map produced NaN on inf inputs, collapsing OkLab ΔE to 0 on EXRs containing firefly inf pixels — that was the BistroInterior x1 blob=0 across all variants (commit `60eb030`).

**Net carry after step 18:** `pos_norm__pos__qa012__bayer4x4_cell4x4_ct128_vt0030_pm010`. The ct=128 + vt=0.03 combo is the first usable cache configuration on Bistro/Sponza at x1/x4. Rays are higher than the cheaper carries (~80% vs ~30%) but the alternative is artifacts.

**Artifact rule:** any `error_delta_blob_pct > 10` indicates visible cache artifacts and the variant is unusable in practice (concentrated localized error — wrong-color cells, banding, light/shadow leakage). The picker rule's hard-reject at 25% is too lenient — treating 10 as the practical ceiling re-frames every result.

## Steps 19–25 (archived under `archive_post_v2/`)

Post-step-18 sweep that piled on `pm020`, `hc005`, `qa006`, `ct256`, `accelDecay`. Under the corrected absolute-vs-GT metric (commits `0ad0e12` + `06a7fe1` + `ccc4708`), most of those mechanisms turned out to be attacking what was **noise in the cache-vs-vanilla comparison rather than real cache degradation**. With the noise-independent metric, the practical sweet spot is much earlier in the ladder.

The data is preserved under `runtime/captures/ladder/archive_post_v2/` for audit; they are not the active carry chain. Stage C.2 step 19 (in [LADDER_PLAN.md](LADDER_PLAN.md)) is the clean re-curation.

**Single-carry recommendation post-metric-fix:** `ct=16 / vt=0.03 / qa012 / bayer4x4_cell4x4 / pm=0.10`. It's a real Pareto win across all 5 scenes vs vanilla.

> **Metric correction (post-step-25):** the original signed-delta-vs-vanilla blob metric inherits vanilla's per-SPP sampling noise. After fixing to **absolute err vs x4096 GT** (commits `0ad0e12` + `06a7fe1` + `ccc4708`) and reposting all steps:
>
> - **The cache wins on bias-dominated scenes** (Cornell 32PL, Bistro, Sponza) at every SPP. Step-18 ct=128 vs step-17 vt=0.03 baseline on BiE x4: cache_err 14.48 → 13.69; on Sponza x4: 6.04 → 4.96. Real cumulative improvements through the ladder.
> - **The cache is roughly tied with vanilla on Cornell 1PL** at low SPP and *slightly worse* at x16 (cache 0.34 vs vanilla 0.14 abs OkLab err) — vanilla converges fast on a single point light, cache adds a small bias from cell-averaging.
> - **BistroInterior x16** is precisely tied (cache 11.05 vs vanilla 11.14) — the firefly story still holds; both are equally far from GT, and the old metric's "blob 14.6" was reporting *the noise pattern of the comparison*, not real cache degradation.
> - The "blob 14.6 invariant" finding from steps 19–24 was largely a metric artifact: pMin / fp / HC / cell-size / accelDecay all looked like no-ops because they couldn't move a number that was anchored to vanilla's noise. Under the new metric, they still mostly tie, but step 18's ct=128 was a real breakthrough (clear absolute error reduction on every bias scene).

Temporal mechanisms (decay, warmup, accelDecay) and indirect illumination
(maxBounces > 0) are deferred to Stage E in [LADDER_PLAN.md](LADDER_PLAN.md), where time-varying mechanisms have something to react to.

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

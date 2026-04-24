# VisCache Dev Log

**Diagnostic plate layout** (4×3 grid):

|           | col 1          | col 2              | col 3         | col 4            |
| --------- | -------------- | ------------------ | ------------- | ---------------- |
| **row 1** | render         | accum raysTraced % | error Δ vs GT | noise Δ vs GT    |
| **row 2** | frame level    | accum maturity     | accum mean    | accum variance   |
| **row 3** | accum coldmiss | frame qAHash       | frame qBHash  | frame probeSteps |

Both row 1 col 3 : error Δ vs GT and row 1 col 9: noise Δ vs GT use the same continuous bipolar ramp anchored at viridis(0) = dark purple for Δ = 0. Positive values (VisCache degraded / noisier) walk the full **viridis** palette (purple → blue → green → yellow); negative values (VisCache better / smoother) fade from purple toward **black**. Darker-than-purple = better; brighter-than-purple = worse. Plate labels report mean and per-pixel [min … max] signed %.

- **error Δ** = OkLabDistance(viscache, GT) − OkLabDistance(vanilla_xN, GT) at matched SPP — perceptual error vs ground truth, relative to same-SPP vanilla.
- **noise Δ** = bilateral_noise(viscache LDR) − bilateral_noise(vanilla_xN LDR) at matched SPP — screen-space noise difference, relative to same-SPP vanilla. Step 00 also emits per-SPP absolute OkLab error vs GT as the reference noise floor the noise Δ is measured against.

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
| 11   | vt × ct × fp (expanded) on step-10 carry | `vt005` beats `vt010` on every blob at matched 32PL rays; fp≥0.2 regresses rays | `qa012__ct4_vt005_fp0`  |
| 12   | ct × warmup × force-descend on step-11 carry (x1/x4/x16) | `ct16` + `w=2` cuts 1PL blob 2.4× (41→17) at 2.3× 32PL rays; x16 stress test shows blob still grows 2–5× with SPP (residual bias), force-descend & fp no-ops | `qa012__ct16_vt005_fp0_fd0` (w=2) |
| 13   | stderr × hierarchical × accel-decay, single-level | **negative**: no variant strictly beats vt005; best-x4 se10+hc cuts 1PL x4 blob 17→10 but regresses x1 13→50 | no carry (keep step-06 vt005) |
| 15   | stderr × hierarchical × accel-decay, multi-level + x16 | **negative** on Cornell; **big-scene supplement (Bistro/Sponza) shows viscache cuts mean GT-err 18–70% on Bistro** — first real-scene data, gate mechanisms near-irrelevant there | no carry (keep step-11 ct4_vt005_fp0) |
| 16   | per-level ct (bootThreshold coarse, bootThresholdFine) | **negative**: asymmetric ct has non-monotonic mid-level regimes — (16,4) regresses 1AL 21→112; fine ct rarely consulted on dense Bistro so doesn't recover rays | no carry |
| 17   | insert-side level-skip (paper win-win idea) | **negative**: fd>0 at insert skips big-cell writes AND disrupts parent-preinit chain → 1AL blob 17→117 at fd=4096; 1PL mixed (46 at fd=4096 vs 56 baseline); ~10% Bistro rays savings at fd=1024 | no carry |

---

## [Step 00 — Vanilla Baselines](step00/STEP00.md)

**What it looks at.** Vanilla PathTracer (no VisCache) at x1 / x2 / x4 / x8 / x16 SPP plus x4096 ground truth per scene. Produces two things every later step measures against:

- `error Δ` reference = OkLab distance from the matched-SPP vanilla
- `noise Δ` reference = bilateral noise from the matched-SPP vanilla
- `vanilla_xN_gterr` floors = absolute OkLab vs the x4096 GT, the noise floor the Δ rides on top of.

**Narrowing.** None — this step is purely reference generation. Every per-scene ladder plot's error/noise panel is a *delta against* this step's EXRs.

| x1 SPP                                           | x16 SPP                                           | x4096 SPP                                           |
| ------------------------------------------------ | ------------------------------------------------- | --------------------------------------------------- |
| ![](step00/renders/CornellBox_1AreaLight_x1.png) | ![](step00/renders/CornellBox_1AreaLight_x16.png) | ![](step00/renders/CornellBox_1AreaLight_x4096.png) |

Full four-scene gallery in [STEP00.md](step00/STEP00.md).

![](step00/overview_summary_00.png)

---

## Step 01 — Cold-Start Tiling + Subframe Mitigation

**What it looks at.** One logical frame, cold cache, coarse `QUANT_01` cells (posA 0.12, posB 0.36, distB 0.96 — deliberately coarser than the step-02+ baseline to expose the tile artifact). Sweeps 1×1 (baseline, artifact visible), 2×2 (+warmup slots 0/1/2), 4×4 (+warmup 0/1/8). Runs only `pos_norm__pos1`. A parallel `subval` control variant forces pMin=1.0 + huge thresholds → always-trace → isolates the Bayer-dispatch plumbing from any cache-skip effect.

**Artifact vs fix** (CornellBox_1PointLight, x1 SPP, cold cache). 1PL is chosen because its hard shadow produces crisp, high-contrast boundaries — any erroneous RR-skip inside the penumbra shows up directly in the render (r1c1) and in the error Δ (r1c3), not just as a diagnostic raysTraced pattern. Multi-light scenes blend the artifact into soft shadow overlaps and mask it.

| 1×1, no warmup — **tile-boundary artifact** | 2×2 + 1 warmup slot — **fixed**             |
| ------------------------------------------- | ------------------------------------------- |
| ![](step01/plates/artifact_1x1.png)         | ![](step01/plates/fixed_1PointLight.png)    |

In the 1×1 plate, a regular grid of bright/dark patches aligned to the dispatch tile boundaries is visible in the render and the error Δ — cells straddling tile edges read as "trusted" (RR-skipped with a stale-or-empty mean) because the neighbour tile's pixel-parallel writes committed before the query read — a first-writer-wins race, not real cache maturity. In the 2×2+warmup plate, writes disperse across N² subframes and the first subframe is write-only; the grid vanishes and the render matches vanilla modulo cache-gate noise.

**Fixed config across scenes — 2×2 + 1 warmup slot (x1 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step01/plates/fixed_1PointLight.png) | ![](step01/plates/fixed_1AreaLight.png) | ![](step01/plates/fixed_3AreaLights.png) | ![](step01/plates/fixed_32PointLights.png) |

**Subval control.** `noise_blob = 0.00` across every N and scene — the subframe path is bitwise-stable vs vanilla accumulation. Any non-zero delta in the main sweep is a cache-gate effect, not plumbing noise.

**Why we narrow.** 2×2 is enough to break the tile pattern and doesn't slow the step 02+ runs. Every later ladder step adopts `SUBFRAME_2x2` as a fixed baseline. Warmup defaults (≥1 slot write-only) are carried too.

![](step01/overview_summary_01.png)

---

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

**Why we narrow.** Collapsed-B `pos1` is dropped; step 03 enumerates per-axis quant for `pos`, `dir_dist1`, and `dir_dist` only. The dense sweep lives on 3 B-branches, not 4.

**Winner `pos_norm__pos` across scenes (x4 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step02/plates/1PointLight.png) | ![](step02/plates/1AreaLight.png) | ![](step02/plates/3AreaLights.png) | ![](step02/plates/32PointLights.png) |

![](step02/overview_summary_02.png)

---

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

**Why we narrow.** Per-axis picker enforces "no variant that degrades err/blob above the cohort median", so aggressive-quant variants only survive if they stay close to the group norm. Gives us 3 quants × 3 B-branches = 9 candidates entering step 04.

**Pos top-1 `qA024_qB036` across scenes (x4 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step03/plates/1PointLight.png) | ![](step03/plates/1AreaLight.png) | ![](step03/plates/3AreaLights.png) | ![](step03/plates/32PointLights.png) |

**Per-B-branch overview split** (variants in the combined overview are too dense for a single plot; each branch gets its own):

- `pos_norm__pos`:
  ![](step03/overview_summary_03_pos.png)
- `pos_norm__dir_dist1`:
  ![](step03/overview_summary_03_dir_dist1.png)
- `pos_norm__dir_dist` (3×2×2 plot subset):
  ![](step03/overview_summary_03_dir_dist.png)

**Top-3 per B-branch — best-of comparison:**

![](step03/overview_summary_03_top3.png)

---

## Step 04 — SPP Convergence on Step-03 Top-3

**What it looks at.** The 9 candidates from step 03 (top-3 per B-branch) re-rendered at x1 / x4 / x16 SPP. Validates that step 03's winners don't have pathological convergence behaviour as sample count climbs.

**Results.** The ranking is stable — picker re-runs on step-04 rows yield substantially the same set. `dir_dist__qA024_qD30_qd048` drops to 53.5% rays on 32PL x4 with `err = −3.91`, `blob = 3.18`. No variant flips from qualifying to disqualifying across SPP, no variant's rays-pct regresses as SPP grows.

**Why we narrow.** Confirms step 03's per-axis winners are SPP-insensitive → safe to carry the pos-branch winners into step 05 (threshold sweep). `dir_dist` / `dir_dist1` branches are parked — the full-position `pos` branch gives the largest consistent rays savings, and step 05+ goes deep on it rather than splitting attention across all three.

**SPP-converged pos winner `qA024_qB036` across scenes (x16 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step04/plates/1PointLight.png) | ![](step04/plates/1AreaLight.png) | ![](step04/plates/3AreaLights.png) | ![](step04/plates/32PointLights.png) |

![](step04/overview_summary_04.png)

---

## Step 05 — bootThreshold × quantAB, pos Single-Level

**What it looks at.** Crosses step 03's top-3 pos quants (qA024_qB018 / qA024_qB036 / qA024_qB072) with 4 boot thresholds (ct1 / ct2 / ct4 / ct8). `matureThreshold = 128` fixed. 12 variants × 2 SPP = 24 runs/scene. First step where the "trust gate" knob is sized against a chosen cell size.

**Results — auto-picker top-3 (ranked by weighted rays-pct asc across scenes with 32PL×3). 32PL x4 numbers shown:**

| variant                                          | rays % | err Δ | blob |
| ------------------------------------------------ | -----: | ----: | ---: |
| `qA024_qB036__ct1` (picker #1)                   | 19.7   | −3.72 | 9.37 |
| `qA024_qB018__ct2` (picker #2)                   | 18.9   | −3.79 | 5.96 |
| `qA024_qB036__ct2` (picker #3, **manual carry**) | 21.2   | −3.79 | 5.75 |

The `ct1` variants pair every "most aggressive rays" with a much higher blob (9.4 vs 5.8) — cells are being trusted after a single sample, so the per-cell mean is an outlier-prone estimate and worst-region error jumps accordingly. The `ct2` variants keep blob at ~5.8 and cost only 1–2pp more rays.

**Why we narrow — and why the manual carry.** `ct1` = "trust the cell after a single sample" = boot gate effectively off. It wins the picker on rays alone (the picker rule lets high-blob variants through if they're inside median+50%, which they are here — the cohort's median is carried upward by the ct1 rows themselves), but it's too eager as the basis for the downstream sweeps that stack jitter, varThreshold, and multi-level on top. `ct2` (one confirming sample before trust) is manually carried: same quant, blob cut 40%, rays cost only 1.5pp.

**Manual carry `qA024_qB036__ct2` across scenes (x4 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step05/plates/1PointLight.png) | ![](step05/plates/1AreaLight.png) | ![](step05/plates/3AreaLights.png) | ![](step05/plates/32PointLights.png) |

![](step05/overview_summary_05.png)

---

## Step 06 — varThreshold Sweep

**What it looks at.** Step-05 carry baked in, sweeps the RR variance gate: `varThreshold ∈ {vt0 = 0.0001, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60}`. When cell variance drops below `varThreshold`, RR trusts the cached μ and skips the trace; above it, the ray always traces. Raising the threshold → more skips in high-variance regions. `vt0` is the extreme "trust only if variance = 0 modulo eps" probe, included to mirror step 11's multi-level run so the two regimes are directly comparable.

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

**Key finding — tightening vt monotonically improves 1PL blob on single-level.** vt060 → vt0 cuts 1PL blob from 67 → 17 (4× better). `vt005` takes the corner: best 32PL blob in the sweep (3.43 vs 5.80 at vt010 and 6.02 at vt020) AND lowest 1PL blob tied with vt0 (16.86), at essentially the same rays as vt010 (22.2 vs 21.9). The cost of tight-vt on 32PL is minimal (~1.5pp extra rays vs vt020) because single-level cells have reliable per-cell variance estimates.

**Key negative — contrast with step 11 multi-level.** On the *multi-level cascade* (step 11), tightening to `vt0` does the *opposite*: 1PL blob jumps to 86 because coarse-level cells with few samples over a penumbra spuriously read as "zero variance" and get fraudulently trusted. Single-level has no such over-trust pathway — all cells at one resolution, and the variance estimate reflects sample stability. The same vt knob has opposite optimal values at the two cascade regimes.

**Why we narrow.** Carry `vt005`. The auto-picker's top-1 was `vt030` (minimises rays at 17.7% and blob qualifies under median+50%), but `vt030`'s 1PL blob (33.23) is exactly the kind of regression the "blob > 10 means artifact" rule flags. Manual override to `vt005`: best 32PL blob, tied-best 1PL blob, rays cost ~1.5pp.

**Carry `…__ct2__vt005` across scenes (x4 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step06/plates/1PointLight.png) | ![](step06/plates/1AreaLight.png) | ![](step06/plates/3AreaLights.png) | ![](step06/plates/32PointLights.png) |

![](step06/overview_summary_06.png)

---

## Step 09 — Jitter Sweep (single level)

**What it looks at.** Step-05 carry plus a companion fine quant with posA/posB halved (step-03 quant grid is power-of-2 spaced, so /2 = "one step finer"). Sweeps the two jitter flavors 3×3:

- `jitterFilter` — per-position-seed jitter (`asuint(pos)` seed). Stochastic grid per sample → acts as a 3D reconstruction kernel; soft cell boundaries.
- `jitterCell` — per-cell-index-seed jitter (`baseIdx` seed, Binder 2018). Whole-cell offset → boundaries stay hard but land at new positions.

2 quants × 3×3 jitter = 18 variants. Scales are in cell units (1.0 = ±0.5 cell).

**What the data hints at.** jf-only softens boundaries without adding firefly noise. jc-only shifts the visible grid but keeps hard edges. Stacking both at full scale (`jf10_jc10`) adds firefly noise and rays without a clearer visible gain over either axis alone. Mid strength (`jf05`, `jc05`) on each looks like the sweet spot.

**Why there's no carry yet.** Jitter is a visual/artifact call, not a rays+err call — the picker rule is silent on "does the image look right across frames". Likely `jf05_jc05`, pending visual inspection. Step 09 only feeds step 14 (combined multi-level sweep), and step 14 currently composes jitter off a fixed guess; carry fixation lands once the plates are reviewed.

**Likely-carry `jf05_jc05` across scenes (x4 SPP, step-05 carry quant):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step09/plates/1PointLight.png) | ![](step09/plates/1AreaLight.png) | ![](step09/plates/3AreaLights.png) | ![](step09/plates/32PointLights.png) |

![](step09/overview_summary_09.png)

---

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

**Why we narrow.** The cascade lets fine levels correct coarse-level early-trust decisions: coarse level fires an RR skip when its variance is low; if it's wrong, the next cascade step down at a finer resolution catches it. `ct4` tuning is more stable at multi-level than `ct2` because the coarser levels have genuinely more samples per cell to back the trust decision — `ct2` at multi-level over-trusts coarse levels and lets blob climb (7.5–9.2) even as it drives rays down. Step 11 onward inherits the multi-level spine.

**Multi-level winner `qa012__ct4` across scenes (x4 SPP):**

| 1PointLight | 1AreaLight | 3AreaLights | 32PointLights |
| --- | --- | --- | --- |
| ![](step10/plates/1PointLight.png) | ![](step10/plates/1AreaLight.png) | ![](step10/plates/3AreaLights.png) | ![](step10/plates/32PointLights.png) |

![](step10/overview_summary_10.png)

---

## Steps 11+ — archived (pre-multi-frame regime)

All x4 and x16 ladder runs up to step 27 used `(frames=1, spp=N)` — a single Mogwai frame with N samples per pixel. This traps every sample at the same Bayer slot (slot rotation is per-frame), so the "cache correlation" effects attributed to the algorithm were substantially a measurement artifact of the harness.

**Switching policy going forward:** viscache runs always use `spp=1`, multi-sample via `frames=N`. Vanilla can use multi-SPP as usual.

**Archive locations:**
- Scripts: `scripts/archive_pre_multiframe/VisCache_Ladder{11..27}.py`
- Captures: `runtime/captures/ladder/archive_pre_multiframe/{11..27}/`
- Per-step plates/plots: `docs/devlog/archive_pre_multiframe/step{11..27}/`

**What we learned that carries forward as design intent:**

1. **Multi-level cascade is the spine.** Single-level was a teaching ladder; multi-level consistently saves rays and improves blob.
2. **pMin is rate-defense, not trust-gate** (step 20). Raising the RR floor from 0.05 to 0.10 broke through 5 consecutive negative gate-tuning results — it ensures corrective tracing at a minimum rate regardless of cache trust. Carried forward.
3. **Variance gate (vt) and pMin decouple** (step 23). Once pm010 is the rate-defense, `vt` purely controls cascade trust tightness, not RR efficiency. Step 23 tightened vt to 0.03 for another big Sponza win — but see §5 below for the multi-frame re-validation caveat.
4. **Scene-regime split is real** (step 21). Variance-dominated scenes (Bistro, dense point lights) want low ct (~4) for rays savings; bias-dominated scenes (Sponza, directional sun + hard shadows) want high ct (~16) to stabilize cell means before trust. `ct` and `vt` are orthogonal bias defenses (step 24) — they combine additively, not substitutively.
5. **Multi-frame re-validation reverses some Cornell pathologies and reveals Sponza bias** (step 27 A/B at step-23 carry):
   - Cornell 1AL x4 blob: 112 → 4.7 (−96%)
   - Cornell 1PL x4 w2 blob: 86 → 41 (−53%)
   - Bistro interior x4 w1 err: −17.7% → −38.6% (quality gain)
   - **Sponza x4 err: +0.2% → +14.8% (regression — single-frame was masking the bias by never warming the cache enough)**
   The previous Sponza "parity" was artifactual. True cache behavior emerges under multi-frame; bias on Sponza is substantial and remains the open problem.
6. **Negative mechanisms that did NOT help** (archived): stderr gate alone or stacked (steps 13, 15, 18), hierarchical-consistency check (13, 15), accel-decay on disagreement (13, 15), per-level bootThresholdFine (16), insert-side level-skip v1/v2 (17), force-descend-footprint × ct16 (19), fine-grained pMin (22). Most of these were fighting correlation artifacts introduced by single-frame testing — under multi-frame they may behave differently, but the case for a new shader mechanism has to be made on top of the multi-frame baseline.
7. **Picker rule updated** (from step 27): per-scene outlier gate replaces weighted-mean aggregate. A variant qualifies only if every scene passes `err ≤ median+25%` and `blob ≤ median+50%`. Ranking by unweighted mean rays. `SCENE_WEIGHTS` emptied.

### Plan for rebuilding the 11+ ladder on multi-frame

- **Phase A** (infrastructure): steps 4, 5, 6, 9, 10 already exist at `x1/x4/x16`; their x4/x16 data is under the old regime. Re-run those steps with multi-frame configs so the single-level / multi-level foundations have accurate data.
- **Phase B** (rebuild): new steps 11+ under multi-frame, applying what we learned:
  - Skip single-level sweeps (multi-level is the spine).
  - Start from step-10 multi-level carry, probe directly at x1/x4/x16 with pm010 + vt tight.
  - Re-validate step-20 pm010 and step-23 vt003 findings against multi-frame.
  - Attack Sponza bias as the primary open problem (not a side-quest).
  - Avoid re-testing the negative shader mechanisms unless there is a reason specific to multi-frame.

## Steps 31–37 — cascade restructuring + HC peek + dir_dist addressing

**Phase A** (step 31): restructured the cascade to allow arbitrarily large `numLevels`.
- `deriveFine` changed from `coarse / 4^sqrt(N-1)` (astronomical at large N) to `coarse / 1024` (constant span).
- `vhfLookup` / `vhfInsert` loops stride by `(N-1)/32` so 32 effective cascade steps run regardless of N. `numLevels` bumped to **32000** — cascade granularity without per-ray cost exploding.
- Analytical entry level: both loops compute `startLvl` from per-pixel footprint (`targetCellSize = depth · pixelSize · √fd`) in a single log-based formula, skipping coarse-level work for near-camera cells.
- Hierarchical-consistency peek now probes one *stride* ahead (= one cell-size doubling) instead of `lvl+1`, which shared quant indices at large N. Disagreement between coarse μ and the finer strided cell flags a penumbra boundary and triggers descent.

**Result (pos addressing, step 31 e_fd0_hcOn):** Sponza x4 blob **184 → 91 (−50%)**, Sponza x1 blob 148 → ~100 (−30%). Cornell scenes unchanged or marginally better. Committed in `251a6c0`.

**Phase B** (steps 32–35): knob sweeps at the step-31 carry.
- Step 32 tolerance sweep: `hierarchicalMuTolerance=0.20` is near-optimal; tightening to 0.05–0.15 doesn't help consistently, 0.30 is too loose.
- Step 33 stderr gate: Sponza x1 blob 160 → 103 with se=0.03 but regressed x4 129 → 193. Mixed, not carried.
- Step 34 accelDecay: Sponza x16 blob 201 → 148 at `accelDecayDisagreeThresh=0.30` (−26%). Run-to-run variance too high on Sponza to separate from noise.
- Step 35 stacking (stderr + accelDecay): no synergy.

**Phase C** (steps 36–37): B-side addressing.
- Step 36 swap pos → dir_dist (view-cone cells indexed by direction × distance instead of endpoint position):
  - Sponza x1 blob **170 → 86 (−49%)**, Sponza x16 blob **193 → 124 (−35%)**.
  - 1PL x4 blob **30 → 18 (−41%)**.
  - Cost: ~50% more rays traced on Sponza (17% → 22%).
  - Trade-offs: 1AL x4 blob 19 → 26 (+35%), Sponza x4 159 → 191 (+20%). dir_dist helps scenes with hard shadows / complex geometry, hurts soft-area-light scenes.
- Step 37 dirB/distB tuning on dir_dist:
  - `distB=0.24` (finer distance cells) at `dirB=15°`: Sponza x4 blob **191 → 110 (−42%)**, 1PL x4 blob 30 → 21 (−30%).
  - Same config regresses Sponza x16 (121 → 213). Finer distance cells fragment the sample pool at high SPP.
- No universal winner — `dir_dist + dirB=15 + distB=0.48` (step 36 default) is the most balanced across Sponza SPPs; `distB=0.24` is strictly better at x4 but worse at x16.

**Sponza reproducibility caveat (step 42 triple-trial):** identical config run 3 times on Sponza yielded blob:
  - x1:  86 / 147 / 111  (range 61)
  - x4:  110 / 109 / 202 (range 93, ~100% spread)
  - x16: 168 / 209 / 121 (range 88, ~72% spread)
The GPU atomic ordering noise floor on Sponza blob is ~90 units. This means many of the −30% to −50% improvements claimed from single-run step-31-41 findings sit near the noise.

**Step 43 ABCD triple-trial — pre-clamp-fix numbers:** ran 4 variants × 3 trials on Sponza:
  | variant | x1 blob μ±σ | x4 blob μ±σ | x16 blob μ±σ |
  |---------|-------------|-------------|--------------|
  | pos addressing, no HC, no decay | 148±22 | 183±23 | 203±6 |
  | pos + HC peek | 130±38 | 171±22 | 192±36 |
  | dir_dist + HC peek | 86±0 | 129±33 | 122±2 |
  | dir_dist + HC + decay dp15 | 91±9 | 121±19 | 172±33 |

Pre-fix, dir_dist looked like the clear winner. **But step 45 then found the cause — an int32 overflow bug in `vhfAddressPosB` for env/sun rays** (Falcor passes tMax=1e30 → `int(round(pos/cellSize))` wraps silently). Fixed by clamping dist to 32× max coarse-cell before the multiply (commit `f9460e3`).

**Step 45 post-fix ABCD triple-trial** (same protocol, with clamp fix applied):
  | variant | x1 blob μ±σ | x4 blob μ±σ | x16 blob μ±σ | rays x1 |
  |---------|-------------|-------------|--------------|---------|
  | pos addressing | **122±7** | 164±20 | 187±43 | 57% |
  | pos + HC peek | 143±26 | 173±36 | 195±36 | 56% |
  | dir_dist | 147±39 | 170±19 | **139±13** | 34% |
  | dir_dist + HC + decay dp15 | 123±32 | **129±21** | 180±44 | 34% |

Reversal: **pos addressing after the clamp fix is now better than dir_dist at x1 and comparable at x4**; dir_dist only wins at x16 (and uses far fewer rays throughout). The pre-fix dir_dist "magic" on Sponza x1 (86 blob) was an artifact of the rest of the pipeline compensating for garbage env cells by always tracing — which is why dir_dist had lower σ (6–38 pos vs 0–2 dir_dist) in the pre-fix data.

Clamp fix is a correctness win regardless; efficiency comparison (blob per ray) still favors dir_dist (34% rays vs 57% rays for comparable blob).

**Open on Sponza x16:** blob plateau at 150–200% across all step-31+ variants. Appears intrinsic to the pos-addressing bias-trap regime. dir_dist addressing cuts it to 124% (step 36); further gains likely need per-scene addressing selection or a new bias-correction mechanism that doesn't drown in high-SPP sample floods.

## Cross-step ladder progress

Per-scene thin lines + bold unweighted "All" across all ladder steps in three panels (rays / error+blob / noise). Red halos mark each step's carried winner; whiskers show per-scene min→max of all variants at that step. One plot per SPP tier.

**x1 SPP:**

![](ladder_progress_x1.png)

**x4 SPP:**

![](ladder_progress_x4.png)

**x16 SPP:**

![](ladder_progress_x16.png)

**Compact overlay — unweighted "All" only, x1 + x4 + x16:**

![](ladder_progress_combined.png)

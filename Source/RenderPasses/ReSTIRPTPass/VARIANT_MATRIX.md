# ReSTIRPT Variant Matrix — at-a-glance overview

One page that pulls together the R-axis × P-axis × H-axis taxonomy and
points at the deeper docs. Mirrors `Source/RenderPasses/VisCache/`'s
DI-side `Rxd/Pyd` matrix.

## R-axis — reservoir storage (`restirptAddrMode`)

| mode | tag | storage | status | doc |
|---:|---|---|---|---|
| 0 | R2d | 2D pixel buffer only (DQLin baseline) | LIVE — bit-identical to frozen `restirpt_ref` | [PORT_NOTES.md](PORT_NOTES.md) |
| 1 | R3d | Pure 3D cell-pool, no pixel buffer | LIVE | same |

**Dropped variants** (2026-05-11): `R2dR3d` (was mode 1, hybrid pixel+cell — no measurable win vs pure R3d; parallel agent's RDI00 validated as no-op +Δ 0.004); `H2dR3d` (was mode 3, per-pixel history fallback — H2dR3dP3d ≡ R3dP3d at static camera per parallel agent's audit; dynamic-camera regime needed to demonstrate value, deferred indefinitely).

## P-axis — NEE light-sample pool (`restirptPoolAddrMode`)

| mode | tag | pool | status | doc |
|---:|---|---|---|---|
| 0 | Pno | none — fresh `emissiveSampler.sampleLight` per NEE | LIVE (= current behavior) | — |
| 1 | P2d | 2D screen-tile pool (RTXDI-tile semantics) | SCAFFOLD ONLY — dispatch wired, real RIS-at-insert TODO | [PORT_NOTES_P_AXIS.md](PORT_NOTES_P_AXIS.md) |
| 2 | P3d | 3D world-cell pool at `restirptPoolFootprintPx` | SCAFFOLD ONLY — same TODO | same |

## Bayer subframe staging (`RESTIRPT_BAYER_N`)

| value | behaviour | status | doc |
|---:|---|---|---|
| 1 | full frame, no Bayer gate (default) | LIVE | — |
| 2+ | Bayer-staged subframes (replaces explicit pre-pass) | DEFERRED — substrate (frame-CAS) now in place; ~1 day port left | [PORT_NOTES_BAYER.md](PORT_NOTES_BAYER.md) |

## Cell-pool write protocol

Single path: three-field slot (`fingerprint` / `frameStamp` / `ready`),
InterlockedMax-elected one-writer-per-(slot, subframe), atomic `ready`
publish. `currentFrame = (frameCount * 256u) + uint(gSppId) + 1u`
per user's "frame_id = frame + subframe" directive. The legacy clearUAV
+ strict-first-writer-wins path was dropped 2026-05-11 (commit pending);
frame-CAS eliminates both the per-frame clear and the 2nd-CAS-overwrite
race that previously TDR'd BistroExt at x12.

Validation (Cornell/Sponza parity at noise floor; BistroInt 45% closer
to vanilla GT than the dropped legacy path; BistroExt R3d x16+x32 TDR-
free): see [PORT_NOTES_FRAMEFP.md](PORT_NOTES_FRAMEFP.md).

## Headline finding (commits `83d3878`, `e158663`)

R3d's cell-pool first-writer-wins atomic-CAS suppresses a DQLin
per-pixel-reservoir firefly pathology on Bistro/Sponza, **and** R3d
runs ~67% faster than R2d everywhere.

### Quality axis (mean_err_pct OkLab vs vanilla GT, SPP=16)

| scene | R2d (DQLin) | R3d | quality speedup |
|---|---:|---:|---:|
| Sponza | 27.76% | 7.18% | **3.9×** |
| BistroInterior | 25.95% | 7.46% | **3.5×** |
| BistroExterior | 16.52% | 8.43% | **2.0×** |

Cumulative R3d-vs-R2d delta across 7 scenes at SPP=16: **−46.08pp WIN**.
Cornell scenes pay a small R3d tax (+0.1pp at SPP=16).

### Cost axis (gpu_total_ms ratio, ladder-relative)

| scene | R2dR3d/R2d | R3d/R2d |
|---|---:|---:|
| BistroExterior | 0.572× | 0.352× |
| BistroInterior | 0.578× | 0.362× |
| Cornell_1AL | 0.542× | 0.306× |
| Cornell_1PL | 0.534× | 0.297× |
| Cornell_32PL | 0.549× | 0.318× |
| Cornell_3AL | 0.538× | 0.307× |
| Sponza | 0.575× | 0.359× |
| **mean** | **0.555×** | **0.329×** |

Remarkable uniformity (R3d/R2d all 0.297-0.362×) → structural speedup
from skipping per-pixel reservoir write + downstream temporal/spatial-
reuse passes that read it. Per-scene independent.

**Combined**: R3d Pareto-dominates R2d on both axes. The Cornell
"+0.1pp quality tax" is offset by a 67% compute drop. Cross-checked
via frozen `restirpt_ref` plugin → R2d's firefly pathology is a DQLin
algorithm property, not a port bug.

### Per CLAUDE.md FULL-METRIC-BATTERY rule (commit pending)

`mean_err_pct` (OkLab) is the headline; secondary metrics show
anti-correlated trade-offs that single-metric reporting would miss:

| Metric | Cum d (R3d-R2d) @ SPP=16 | Story |
|---|---:|---|
| `mean_err_pct` (OkLab) | **−46.08pp** | R3d wins by huge margin |
| `rmse` | **−1092.59** | R3d wins by even larger margin in linear space (Sponza R2d 73 vs R3d 0.19) |
| `psnr_db` (sign-flipped) | **−136.38 dB** | Same direction; R3d's PSNR much higher |
| `artifact_5_pct` | **−36.42pp** | R3d wins cum but Cornell scenes now INCREASE artifact area: 1PL +13.1pp, 1AL +5.1pp |

The artifact_5 anti-correlation: vanilla converges to <5% err on simple
Cornell, so any R3d bias bumps pixels over the threshold even if mean
OkLab is barely affected. On Bistro/Sponza the metric tracks mean
(R3d −10 to −28pp). Headline cum stays in R3d's favour but Cornell-
artifact reporting in the paper needs honesty.

Regenerate any metric: `audit_rpt_zoo_R3d_vs_R2d.py 16 --md --metric=KEY`.

Full per-scene tables in [docs/LADDERLOG.md](../../../docs/LADDERLOG.md)
"Step RPT_ZOO" section. Cost audit:
`scripts/audit_rpt_zoo_cost.py 16`.

## Tooling

- `scripts/audit_rpt_zoo_R3d_vs_R2d.py [spp] [--md] [--all]` — markdown
  table of per-scene + cumulative R-axis deltas, ready for LADDERLOG paste-in.
- `scripts/backfill_step00_vanilla_csv.py` — regenerate missing vanilla
  CSV rows in step 00 from existing EXRs (idempotent).
- `scripts/RestirPT2D_AB.py` — AB harness vs frozen `restirpt_ref`.
  Env vars: `AB_FRAMES`, `AB_BOUNCES`, `AB_POOL_MODE` (0 = Pno default,
  1 = enable P-axis dispatch).

## Composition

P-axis is orthogonal to R-axis (per parallel-agent's DI-side audit
findings). Conjugate: `R{x}d × P{y}d` covers the matrix.

For PT side, the parallel agent's 2026-05-11 audit notes are still WIP:
- P2d_F00P24 BEATS RTXDI at architectural parity by 0.39pp cumulative.
- P3d_F00P24 was 12.99pp WORSE than P2d at the time of audit; root cause
  identified as N=128 slots vs RTXDI 1024 + first-writer-wins discards.
  `wsCellPoolFindSlot` (double-hash probe) just landed to fix the
  collision half; slot-capacity bump + Sponza re-run pending.

H2dR3d (mode 3) is deferred per parallel agent's "fallback layer not
temporal accumulator" finding — H2dR3dP3d ≡ R2dR3dP3d in canonical
regimes; cold-cell stress test (SPP=1, fast camera) is when H2d's
fallback would matter.

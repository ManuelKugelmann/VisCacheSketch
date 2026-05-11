# ReSTIRPT Variant Matrix — at-a-glance overview

One page that pulls together the R-axis × P-axis × H-axis taxonomy and
points at the deeper docs. Mirrors `Source/RenderPasses/VisCache/`'s
DI-side `Rxd/Pyd` matrix.

## R-axis — reservoir storage (`restirptAddrMode`)

| mode | tag | storage | status | doc |
|---:|---|---|---|---|
| 0 | R2d | 2D pixel buffer only (DQLin baseline) | LIVE — bit-identical to frozen `restirpt_ref` | [PORT_NOTES.md](PORT_NOTES.md) |
| 1 | R2dR3d | 2D pixel + 3D cell-pool override (cell-first, pixel-fallback) | LIVE | same |
| 2 | R3d | Pure 3D cell-pool, no pixel buffer | LIVE | same |
| 3 | H2dR3d | Per-pixel "last good shade" fallback for empty cells | DEFERRED — three viable design options enumerated | [PORT_NOTES_H2DR3D.md](PORT_NOTES_H2DR3D.md) |

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
| 2+ | Bayer-staged subframes (replaces explicit pre-pass) | DEFERRED — clearUAV restructure required | [PORT_NOTES_BAYER.md](PORT_NOTES_BAYER.md) |

## Headline finding (commit `83d3878`, 2026-05-09)

R3d's cell-pool first-writer-wins atomic-CAS suppresses a DQLin
per-pixel-reservoir firefly pathology on Bistro/Sponza:

| scene | R2d (DQLin) x16 OkLab | R3d x16 OkLab | speedup |
|---|---:|---:|---:|
| Sponza | 27.76% | 7.18% | **3.9×** |
| BistroInterior | 25.95% | 7.46% | **3.5×** |
| BistroExterior | 16.52% | 8.43% | **2.0×** |

Cumulative R3d-vs-R2d delta across 7 scenes at SPP=16: **−46.08pp WIN**.

Cross-checked via frozen `restirpt_ref` plugin → pathology is a DQLin
algorithm property, not a port bug. Cornell scenes pay a small R3d tax
(+0.1pp at SPP=16) where vanilla converges fast.

Full per-scene table in [docs/LADDERLOG.md](../../../docs/LADDERLOG.md)
"Step RPT_ZOO" section.

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

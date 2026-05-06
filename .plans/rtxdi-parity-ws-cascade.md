# RTXDI Parity via WS-Cascade ReGIR — Design Notes

Source: design discussion 2026-04-30 between user and assistant.
Status: design only; implementation deferred.

## Context

Our WS-ReSTIR DI on `pixel_restir K=8 + no VisCache` is ~2× worse than vanilla
on emissive-heavy scenes (Sponza x1: 18.75% mean err vs vanilla 11.27%, RTXDI
9.20%). RTXDI parity = ~9.2% on Sponza.

Audit of the RTXDI SDK (`Falcor/external/packman/rtxdi/1.3.0-falcor/`) shows
RTXDI's quality lead does NOT come from visibility-aware p̂ (their target pdf
is luminance-only; SDK comment: "would be prohibitively expensive"). It comes
from **structural mechanisms** we lack:

1. Tile pre-sampling (power-weighted candidate POOL per screen tile)
2. Spatial reuse from K=5 neighbour-pixel reservoirs
3. V=0 reservoir invalidation after the winner's shadow trace
4. (Some implementations) ReGIR — world-space variant of tile pre-sample

The cleanest port to our infrastructure is **ReGIR built on top of the
VisCache cascade**, with two of our own enhancements that compose naturally.

## Architecture: WS-Cascade ReGIR

### Core idea

Reuse the VisCache cell-hash + cascade addressing as the **world-space
importance grid**. Each cell of each cascade level stores a small light pool
(N=8 power-weighted lights) shared across pixels in the cell.

### Data structure

New buffer `gWSCellPool[level][slot]` of `WSCellPool`:

```
struct WSCellPool {
    uint fingerprint;                       // 0 = empty sentinel
    uint count;                             // 0..N valid entries
    uint lightTypeIndex[N];                 // (lightType<<24) | lightIdx
    uint payload[N];                        // barys / dirOct / 0
};
static const uint N = 8;                    // 72 B per pool at N=8
```

Pool count budget: ~256K slots per level × ≤4 active levels = 72 MB upper
bound. Could be cut by reusing one buffer across levels with level-tagged
fingerprints.

### Phases

Three orthogonal mechanisms, each independently switchable:

#### (a) Main-pass winner write-back to cell pool

After per-pixel K-RIS picks a winner, write that identity to the home cell's
pool with a random-replace policy (or LRU). Pool fills organically over
frames — frame 1 is empty (= fall back to `generateLightSample`), frame 2+
benefits from accumulated winners.

**~150 lines slang/cpp.** Builds the data structure plumbing.

#### (b) Bayer subframe pre-pass

Run PathTracer twice per frame:

  Pre-pass: subframeN=4, warmupRun=1 (1/16 of pixels active, write-only)
            Pixels do M-from-N RIS, write top-K to cell pool.
  Main pass: subframeN=1 (full coverage, all pixels read pool, K-RIS,
             shade as before).

The pre-pass uses Bayer to get gapless cell coverage at coarse cascade
levels. **No new compute pass needed** — reuses existing PathTracer subframe
infrastructure.

**~50 lines** if subframe gating already supports the write-only flag.

#### (c) Cascade-descend pool inheritance

Pool keyed by `(cell_coords, cascade_level)`. Pre-pass writes to multiple
cascade levels (coarsest reliably populated, finer sparsely). Main-pass
query descends cascade fine→coarse, using whichever level has populated
pool:

```
for lvl in finest..coarsest:
    pool = wsLoadCellPool(posA, lvl)
    if pool.count > 0:
        return draw_K_from_pool(pool)
return generateLightSample (fallback)
```

This makes coverage adaptive: well-sampled regions use fine pools (precise);
sparse regions fall back to coarse pools (less precise but always populated).

**~100 lines** to extend pool buffer + query logic. Architecturally new
relative to standard ReGIR (which uses a single fixed-grid resolution).

#### (d) V-aware re-presample (extension beyond RTXDI)

In the pre-pass, draw M=32 candidates, **trace a shadow ray for each** to
get V (binary or cached μ from VisCache), keep top-N=8 by `p̂ × V`. Cell
pool ends up with VISIBLE-bright lights only. Eliminates the bright-occluded
sample bias entirely.

**Affordable because pre-pass is sparse** (1/16 pixels). At full-screen
density this would be ~8 extra rays/pixel/frame; at 1/16 it's 0.5
rays/pixel/frame amortized.

**~50 lines** — adds a shadow-trace loop in pre-pass.

This is what RTXDI explicitly declined for cost reasons. We can do it because
the pre-pass amortizes the cost. **Should beat RTXDI on Sponza-class scenes
where bright-but-occluded lights dominate.**

## Implementation order

1. **(a) Single-level cell pool** — basic data structure + main-pass
   write-back. Test: should help at multi-frame SPP (x4+); no benefit at x1.
2. **(b) Bayer pre-pass** — run PathTracer in pre-fill mode at subframeN=4
   for 1 frame, then main-pass for 1 frame. Test: x1 SPP should now have
   non-empty pools → quality jump on emissive-heavy scenes.
3. **(c) Cascade pool descend** — extend pool buffer to per-level. Test:
   coverage robustness on Bistro/Sponza geometry-dense regions.
4. **(d) V-aware re-presample** — add shadow trace in pre-pass.

After (a)+(b): expect to close ~50–70% of the gap to RTXDI parity.
After (c): close to RTXDI parity.
After (d): exceed RTXDI on emissive-heavy scenes.

## Comparison table

|                            | Tile pre-sample (RTXDI) | ReGIR (Boksanský '21) | Our WS-cascade ReGIR |
|----------------------------|------------------------|------------------------|----------------------|
| Sharing axis               | Screen tile            | World cell, fixed grid | World cell, cascade  |
| Pool target function       | Power                  | Power × G [× V]        | Power × G × V (opt)  |
| Multi-resolution           | No                     | No                     | **Yes (cascade)**    |
| Motion robust              | Needs MV reprojection  | Free (world-anchored)  | Free                 |
| Pre-pass mechanism         | Dedicated compute      | Dedicated compute      | Bayer subframe       |
| Visibility in pre-sample   | No (declined for cost) | Sometimes              | Yes (sparse → cheap) |

## Reuse of existing infrastructure

What we already have that this design leverages:
- `vhfQuantizePosA`, `wsResolveCell` — cell hash addressing (any cascade level)
- `gSubframeN`, `gWarmupSlotsFirst/Run` — Bayer subframe gate
- `vhfLookup` — visibility cache for the V-aware extension
- Per-pixel reservoir + spatial reuse machinery — orchestration around the new pool

What's new:
- `WSCellPool` struct + buffer (per-level)
- Pool-load / pool-write helpers
- M-then-N re-presample logic in pre-pass
- Cascade-descend query path

## Memory & perf budget

- Pool buffer: 72 B × 256K × 4 levels = 72 MB (upper bound, could share level)
- Pre-pass cost: sparse Bayer = (1/16) × main-pass cost
- Per-pixel K-RIS cost: identical to current (8 candidate evals + RIS)
- V-aware extension: +(M / N²) shadow rays per pixel amortized = ~0.5 rays/pixel
  for M=32, N=4 (subframeN²)

## Open questions

- Random-replace vs LRU vs power-weighted-replace for pool insertion?
- Should pool entries also store `targetPdf` at write time for proper RIS,
  or recompute at read time? (Recompute is correct but more costly.)
- How does the V-aware extension interact with VisCache's μ instead of binary V?
  Cached μ ∈ [0,1] gives a softer weighting; might tune p̂ × max(μ, μ_min).

## ReGIR-paper directives (2026-04-30, user)

The Boksanský 2021 ReGIR chapter contributes four points worth pulling
into our grid-side cascade variant:

1. **Cell-centre proxy bias.** They evaluate p̂ at cell centre, biasing
   against grazing-angle / near-edge shading points. Their fix is jitter
   the cell-centre query or store a small distribution. Maps directly to
   our `wsCellJitter` work and the Sponza ceiling-corner failure mode
   (project memory `project_sponza_ceiling_is_vt`).

2. **Temporal cell-pool blending — M-cap + decay.** Old samples decay,
   new samples replace via the RIS update rule. Our current step (a)
   write-back is one-shot random-replace; the chapter's exponential
   M-cap gives a smoother bias/variance trade. **One-line change in
   `wsCellPoolInsert`**, addresses the saturated-`ct=2` finding from
   step 18 (project memory `project_sponza_trust_gate_saturated`).

3. **Visibility-in-p̂ at fill time (NEE-style).** Paper recommends NEE-
   style visibility-aware fill or post-shade revalidation — both cheaper
   than per-pixel V (which we tried + rejected, project memory
   `project_wsrestir_visibility_blind_bias`). **This is exactly our
   step (d)** with the cost amortized through the Bayer-sparse pre-pass.

4. **Cell selection from grid for shading.** Paper looks up cell at
   the hit point; we have a cascade of cells. The combination
   (chapter's selection rule + our cascade) is the one design call
   the paper does not make for us.

### Adoption priorities (paper directives mapped to our roadmap)

- **P1 — Cite ReGIR as the primary anchor** in WS-ReSTIR / WSCellPool
  paper section. Boissé 2021 = screen-side; ReGIR = grid-side; we are
  grid-side.
- **P2 — Adopt M-cap + decay schedule** in `wsCellPoolInsert` before
  tuning K. One-line change; smoother than random-replace.
- **P3 — Visibility-in-p̂ at fill time** (= step (d) of this plan,
  with the existing Bayer-sparse pre-pass making the cost affordable).
- **P4 — Footprint-derived cell size** (Binder 2018/2019). Replace the
  constant `quantSceneScale` multiplier with a per-hit cell size derived
  from the area pdf at the hit point — gives ≈constant samples-per-cell
  across distance. Our `footprintScale` flag is the same idea in spirit
  but global; per-hit removes the Sponza/Bistro tuning gap.
- **P5 — Two-level promotion/decay policy** (Boissé 2022 GI-1.0).
  Explicit "promote when stable, decay when missing" rule for cell
  entries — more principled than our discrete `numLevels` cascade with
  fixed quant shifts. Plugs into the adaptive-`ct` idea (project memory
  `project_scene_dependent_ct`).

## Status

- Step (a): IMPLEMENTED + verified Cornell32PL (matches vanilla x16 at
  16 samples, unbiased ✓), Sponza single-frame x1 = **3.81% mean err**
  vs RTXDI 9.20% / vanilla 11.27% — **2.4× better than RTXDI**.
- Step (b): IMPLEMENTED — `wsCellPoolFillOnly` PathTracer property +
  separate PathTracerPrePass instance in graph. Single-frame ReGIR
  matches 16-frame ReGIR (3.8108 ≈ 3.8102) — pre-pass UAV barrier works.
- Step (c): TBD — cascade-descend pool inheritance.
- Step (d): TBD — V-aware re-presample in pre-pass (= P3).

## Quick-win cost reductions (RDI ladder)

1. **Bayer-sparse pre-pass** (`RDI_04`): prepass dispatches with only
   1/N² of pixels active per frame. Pool fills across N² subframes;
   prepass cost shrinks to ≈0.03× vanilla.
2. **Reduced `wsCellPoolDrawK`** (`RDI_05`): 8 → 4 candidates per pixel
   in main-pass RIS. Halves main-pass RIS work for marginal quality
   loss (worth measuring).
3. **V-aware re-presample** (`RDI_06`): step (d) above. Trades cheap
   sparse-prepass ray budget for unbiased visibility-aware p̂.

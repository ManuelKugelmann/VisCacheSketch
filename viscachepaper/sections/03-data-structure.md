# 3. Data Structure

## 3.0 Data Structure as a Convergent Design Point

The data structure described in this section is, by 2026, the **convergent design point** for online-learned per-cell statistics in real-time path tracing. The unpublished Diplomarbeit [Kugelmann 2006] already explored a visibility-caching variant of it, whose §3.2.2 lists "the location of the query point" (per-position grouping) and "the occupied grid cell" (per-cell grouping) alongside "the depth value" and "the surface orientation" as criteria for the cell key — the position+normal+grid cell descriptor still used here. The thesis was never properly published and remained invisible to the field; in the intervening twenty years, the cache machinery has been developed independently in radiance-caching, light-reservoir, and path-guiding settings by at least five contemporary teams that arrived at structurally equivalent designs. We pick up that thread in 2026 by GPU-parallelizing the 2006 framework, extending it with a multi-level cascade, and integrating with the modern ReSTIR family.

| Design choice | This work | Independent contemporaries arriving at the same choice |
|---|---|---|
| Flat single-buffer hash table, levels co-mingled | `gTableCapacity`; one buffer for all levels | [Boissé 2021]; [Boksanský et al. 2021] (ReGIR); [Boissé 2022] (GI-1.0); [Benyoub et al. 2024] (SHaRC); [Alber et al. 2025] (MCPG, adaptive + static in one buffer) |
| Position+normal as joint cell key | `qa = jitterQuantize(posA) ⊕ oct-normal`, `VisCache.slang:597–614` | sketched in [Kugelmann 2006 §3.2.2] (unpublished Diplomarbeit, listing the criteria) and independently developed by [Boissé 2021]; [Zhang and Wang 2023]; [Alber et al. 2025] (`hash_grid_normal_level`) |
| Level XOR'd into the hash key (no per-level table) | `pcgHashEndpoint(q, lvl, salt)` per dim | [Gautron 2020]; [Alber et al. 2025] |
| Distance/footprint-driven cell width | `vhfCellPixels(lvl, posA)` + per-level geometric ladder `posACoarse → posAFine` | [Binder et al. 2018] (cell size from ray footprint / area pdf); [Alber et al. 2025] (`2·tan(α/2)·dist(cam, pos)`); [Benyoub et al. 2024] (SHaRC, camera-distance-driven) |
| Analytical entry-level computation (closed-form, O(1) lookup) | `targetLvl = round(N · log(targetCellSize/posACoarse) / log(posAFine/posACoarse))`, `vhfInsert/vhfLookup` ~lines 1412–1430 | [Binder et al. 2018] (LOD selected directly from footprint); [Alber et al. 2025] (`mc_adaptive_target_level_for_pos`, exp/quad inverse). **Not present in [Boissé 2022] (GI-1.0)**, which uses data-driven adaptive promotion / decay heuristics; **not applicable to single-level [Boissé 2021] / [Boksanský et al. 2021] (ReGIR) / [Zhang 2023]**. This is the sub-cluster shared with the path-filtering / path-guiding lineage but not with the radiance-cache lineage. |
| Fingerprint-based collision detection | `pcgHash(..., 0xDEADBEEF)` + double-hash probing | [Binder et al. 2018]; [Gautron 2021]; [Alber et al. 2025] (`MCState.hash` uint16) |
| Jitter-before-quantize on lookup (per-position seed) | `gJitterFilter` mode — `seed = asuint(pos)` | [Binder et al. 2018 §2.1] ("jittering realizes the stochastic evaluation of filter kernels"); [Alber et al. 2025] (`grid_idx_interpolate(pos, w, rand)`) |
| Stochastic LOD selection (probabilistic level draw) | `wsCellLevelJitter` (one-sided exponential, `WSReservoirIO.slang`) | [Alber et al. 2025] (`level = target + uint(-log2(1-u))`) — we adopt their probabilistic form |
| MLE α-floor on per-cell mean (`α = max(1/N, α_min)`) | `mlAlphaFloorN` lowering the in-line decay trigger to N* | [Alber et al. 2025] (`mc_state_add_sample`) |
| Race-tolerant atomic insert | packed `[vis:16\|total:16]` + `InterlockedAdd` + 1/8 inline decay | [Gautron 2021] (atomic hash-map updates) |

Nine structural primitives in common across teams that began from completely different problems — visibility (us), incident radiance (SHaRC, NRC, GI-1.0), per-cell light reservoirs (ReGIR, Boissé 2021), path guiding via vMF mixtures (Alber et al. 2025) — and from completely different update math (atomic running mean + 1/8 decay vs. MCMC accept + MLE blend; CV+RRR vs. continuous MIS; binary V vs. continuous radiance). The convergence is not on the algorithm. **It is on the data structure.** The flat multilevel jittered spatial hash with a position+normal cell key, fingerprint collision check, distance-driven cell sizing, analytical entry-level computation, and α-floor blending is, at this point, the right data structure for online-learned per-cell statistics in real-time path tracing — validated five times over from independent starting points.

The design-convergence picture is not, however, fully uniform. The analytical entry-level row above splits the contemporary teams into two sub-clusters: the **path-filtering / path-guiding lineage** (us, Binder et al., MCPG, SHaRC) computes the entry level closed-form from screen footprint, giving an O(1) cascade lookup independent of data state; the **radiance-cache lineage** (Boissé 2021/2022, ReGIR) is either single-level or uses data-driven promotion / decay heuristics where lookup cost depends on which cells have matured. We belong to the first sub-cluster, and that is the more defensible design-convergence claim: among multi-level world-space caches *that need O(1) lookup*, four independent teams arrived at the same analytic-entry-from-footprint design. The radiance-cache lineage occupies a different design point that solves the same problem (distance-adaptive resolution) without requiring O(1) cascade lookup at query time.

We therefore frame the rest of §3–§7 as **expository of a settled design choice**, noting that [Kugelmann 2006] already explored the cell-keying and CV+RRR machinery and citing contemporary works for parallel evidence. The novel contributions of this paper sit on top of this data structure, not within it: the multi-level cascade with footprint-driven descent (this section, §3.2 below), the variance-gated write depth (§7), the binary-V Bernoulli σ²=μ(1−μ) closed-form RR rate (§8), the ReSTIR-family composition (§9), and the empirical Pareto-domination of the production RTXDI baseline (§13). RTXDI parity at the data-structure level (§13 / Ladder00 `restir_2d` and `restir_3d`) is the **floor** we have to clear; it earns the right to layer the cost and quality contributions on top.

**The world-space cell pool subsumes the 2D variants by construction.** The two ReSTIR DI screen-space data structures — per-pixel reservoir and tile pool, both used by RTXDI — are recovered as specific operating points of the cell-footprint knob (`forceDescendFootprintPx`):

- **Per-pixel reservoir ↔ pixel-footprint cells.** At a target cell footprint of one pixel each shading point maps to a private world cell, structurally equivalent to a per-pixel reservoir.
- **Tile pool ↔ tile-footprint cells.** At a target footprint of $T^2$ pixels (matching the RTXDI tile size) all pixels in the projected tile map to the same world cell, structurally equivalent to a tile pool.

The two Ladder00 variants are configured accordingly: `restir_2d` uses the discrete RTXDI data structure (per-pixel reservoir + tile pool, separate buffers); `restir_3d` uses the world-space cell pool with the single-slot reservoir keyed at pixel-footprint cells and the cell pool keyed at tile-footprint cells. Both should match RTXDI directly. `restir_2d` matches by construction (it *is* RTXDI's data structure); `restir_3d` matches by the equivalence above, modulo addressing/quantization details that the parity step is designed to surface.

Cross-tile sample sharing — pixels at the same world location from different screen positions, depths, or frames — is what occurs strictly beyond the tile-size footprint and is the regime that the 2D variants structurally cannot represent. The Ladder00 parity benchmark therefore tests a structural-equivalence claim that is derivable rather than purely empirical: at footprint=1 the cell pool must collapse to the per-pixel reservoir, and at footprint=$T^2$ it must collapse to the tile pool. Empirical agreement at those operating points is a correctness check on the addressing, not a comparison between architectures. The contribution is the curve *beyond* footprint=$T^2$, where the world-space cell pool persists state across camera motion in ways the 2D variants cannot. Even at the tile-equivalent operating point the world-space cell pool is depth- and motion-invariant; this is not a quality claim under the static-frame parity benchmark, but it is a structural property that becomes load-bearing under camera motion (§13).

---

## 3.1 Entry

Each entry stores a fingerprint for collision detection and a packed uint with two 16-bit counters (visible_count, total_count):

```hlsl
struct Entry {
  uint fingerprint; // collision detect (Sec. 4.4)
  uint packed;     // [vis:16][total:16]
}; // 8 bytes
```

V=1 adds 0x00010001; V=0 adds 0x00000001. Single InterlockedAdd — both counters always in sync, no lock required. Mean = vis/total, variance = mean(1−mean). Weighted insertion optional: quantize weight to 4 bits (1–15), add (w<<16)|w for V=1.

**Overflow and collision handling.** Inline overflow decay prevents counter saturation: when total exceeds a trigger (0xE000), a single InterlockedAdd atomically subtracts 1/8 of both counters, keeping the ratio (and thus the mean) stable within ~0.003% at trigger counts. The fingerprint field detects hash collisions — different keys that map to the same table slot. On collision, the double-hash probe sequence (Sec. 4.4) searches subsequent slots. Pressure-scaled eviction on the insert path self-heals long probe chains: from probe step 2 onward, each step doubles the eviction threshold, preferentially displacing stale or low-sample entries (Sec. 6). The 8-byte entry format enables WaveMatch coalescing (SM 6.5): merging N samples targeting the same cell into a single InterlockedAdd of (vis_count<<16 | total_count), reducing atomic contention ~16× at coarse levels where many pixels share a cell.

## 3.2 LOD Configuration

N levels (default N=3) with LOD index encoded in the hash key (Sec. 4.4). The primary addressing mode (position+normal × direction+distance, Sec. 4.1) has two LOD dimensions: spatial cell size and angular bin size, both following geometric progressions from coarse to fine. Distance bins are not an LOD dimension — they exploit a geometric monotonicity invariant (Sec. 4.1). Cell sizes in world units; no scene bounds needed.

Cell sizes follow a geometric progression from cell_coarse (L0) to cell_fine (L_{N-1}):

```
cell_size(l) = cell_coarse × exp(l/(N-1) × ln(cell_fine / cell_coarse))
```

Three runtime cbuffer parameters control the LOD ramp: N (level count), cell_coarse, and cell_fine. Example configuration for mixed interior/exterior scenes (Bistro, Sponza) at primary viewing distances 2–20 m:

| Level | Cell size | ≈ px @ 5 m |
|---|---|---|
| L0 | 10 m | ~107 |
| L1 | ~1.26 m | ~14 |
| L2 | 16 cm | ~1.7 |

> **Table 1.** Spatial cell sizes (N=3, cell_coarse=10 m, cell_fine=0.16 m). In the primary addressing mode (Sec. 4.1), these control the position quantization of the shading point. In the secondary position × position mode (Sec. 4.6), both endpoints use the same cell size. Pixel column shows projected cell side length at 5 m distance, 90° HFoV, 1080p. L2 is near-pixel at typical viewing distances; it populates only where the variance-gated cascade (Sec. 5) propagates past L1. All parameters are scene-dependent tuning knobs — there are no universal correct values.

| Level | Angular bin | Distance threshold |
|---|---|---|
| L0 | ##° | ∞ (directional only) |
| L1 | ##° | ## m |
| L2 | ##° | ## m |

> **Table 1b.** Angular bin sizes and distance thresholds for the direction+distance dimensions of the primary addressing mode (Sec. 4.1). Angular bins follow a geometric progression from coarse (L0) to fine (L2). Distance thresholds are tied to spatial cell sizes via d_max(l) = cell_size(l) × distance_scale. The coarsest distance bin [0, ∞) collapses to direction-only addressing. All values are scene-dependent tuning knobs — placeholders (##) to be filled with measured defaults.

Scenes at substantially different scales (tabletop close-ups, city-scale flyovers) would benefit from camera-adaptive cell sizing via FoV and circle of confusion — deferred to future work.

**Two addressing modes.** The primary mode — position+normal × direction+distance (Sec. 4.1) — exploits surface normal, angular structure, and distance monotonicity. A secondary position × position mode (Sec. 4.6) is available for GI revalidation where both endpoints are surface points. Both coexist in the same flat table. In the current design, the variance-gated cascade (Sec. 5) determines which levels are written: coarse levels converge first, and propagation stops when variance drops below τ_var. A maturity gate (SE-based) skips entries with enough samples, and decay periodically revalidates.

**Why a flat hash, not a hierarchy.** Prior multilevel approaches — separate tables per level, octree subdivision [Popov et al. 2013], hierarchical cascade grids — add structural complexity: pointer management, multi-table eviction coordination, variable-depth traversal. A single flat table with level-in-key (Sec. 4.3) is simpler, has uniform access cost, and allows entries at all levels to compete for capacity under one eviction policy. This design emerged after experimenting with alternatives; the flat table consistently performed better for our access pattern (many parallel inserts/lookups with variable level mix).

**Explicit vs. neural.** Compared to neural visibility caches [Bokšanský and Meister 2025], the explicit hash table offers inspectable entries (cached μ and sample count are directly readable), zero inference latency (one hash + one memory read vs. MLP evaluation), predictable cold-start behavior (first sample populates an entry immediately), and tunable parameters with clear semantics. The neural approach offers automatic spatial adaptation without explicit LOD configuration and potentially better generalization. Prediction-with-correction (Sec. 8) applies identically to either data structure.

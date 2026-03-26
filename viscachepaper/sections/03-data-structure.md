# 3. Data Structure

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

> **Table 1.** Spatial cell sizes (N=3, cell_coarse=10 m, cell_fine=0.16 m). In the primary addressing mode (Sec. 4.1), these control the position quantization of the shading point. In the secondary position × position mode (Sec. 4.6), both endpoints use the same cell size, enabling canonicalization. Pixel column shows projected cell side length at 5 m distance, 90° HFoV, 1080p. L2 is near-pixel at typical viewing distances; it populates only where the variance-gated cascade (Sec. 5) propagates past L1. All parameters are scene-dependent tuning knobs — there are no universal correct values.

| Level | Angular bin | Distance threshold |
|---|---|---|
| L0 | ##° | ∞ (directional only) |
| L1 | ##° | ## m |
| L2 | ##° | ## m |

> **Table 1b.** Angular bin sizes and distance thresholds for the direction+distance dimensions of the primary addressing mode (Sec. 4.1). Angular bins follow a geometric progression from coarse (L0) to fine (L2). Distance thresholds are tied to spatial cell sizes via d_max(l) = cell_size(l) × distance_scale. The coarsest distance bin [0, ∞) collapses to direction-only addressing. All values are scene-dependent tuning knobs — placeholders (##) to be filled with measured defaults.

Scenes at substantially different scales (tabletop close-ups, city-scale flyovers) would benefit from camera-adaptive cell sizing via FoV and circle of confusion — deferred to future work.

**Two addressing modes.** The primary mode — position+normal × direction+distance (Sec. 4.1) — exploits surface normal, angular structure, and distance monotonicity. A secondary position × position mode with symmetric cell sizes and canonicalization (Sec. 4.6) is available for GI revalidation where both endpoints are surface points. Both coexist in the same flat table. In the current design, the variance-gated cascade (Sec. 5) determines which levels are written: coarse levels converge first, and propagation stops when variance drops below τ_var. A maturity gate (SE-based) skips entries with enough samples, and decay periodically revalidates.

**Why a flat hash, not a hierarchy.** Prior multilevel approaches — separate tables per level, octree subdivision [Popov et al. 2013], hierarchical cascade grids — add structural complexity: pointer management, multi-table eviction coordination, variable-depth traversal. A single flat table with level-in-key (Sec. 4.3) is simpler, has uniform access cost, and allows entries at all levels to compete for capacity under one eviction policy. This design emerged after experimenting with alternatives; the flat table consistently performed better for our access pattern (many parallel inserts/lookups with variable level mix).

**Explicit vs. neural.** Compared to neural visibility caches [Bokšanský and Meister 2025], the explicit hash table offers inspectable entries (cached μ and sample count are directly readable), zero inference latency (one hash + one memory read vs. MLP evaluation), predictable cold-start behavior (first sample populates an entry immediately), and tunable parameters with clear semantics. The neural approach offers automatic spatial adaptation without explicit LOD configuration and potentially better generalization. Prediction-with-correction (Sec. 8) applies identically to either data structure.

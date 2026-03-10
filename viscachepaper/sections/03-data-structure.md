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

**Overflow and collision handling.** Inline overflow decay prevents counter saturation: when total exceeds a trigger, a CAS loop atomically subtracts 1/8 of both counters, keeping the ratio (and thus the mean) stable within ~0.003% at trigger counts. The fingerprint field detects hash collisions — different keys that map to the same table slot. On collision, the double-hash probe sequence (Sec. 4.4) searches subsequent slots. Pressure-scaled eviction on the insert path self-heals long probe chains: from probe step 2 onward, each step doubles the eviction threshold, preferentially displacing stale or low-sample entries (Sec. 6). The 8-byte entry format enables WaveMatch coalescing (SM 6.5): merging N samples targeting the same cell into a single InterlockedAdd of (vis_count<<16 | total_count), reducing atomic contention ~16× at coarse levels where many pixels share a cell.

## 3.2 LOD Configuration

Three levels with LOD index encoded in the hash key (Sec. 4.3). Default: asymmetric — endpoint A (shading point) refines faster than B (light/secondary hit), matching the common unidirectional PT case where roles are known. Cell sizes in world units; no scene bounds needed. Optional: symmetric cell sizes for bidirectional use cases or when canonicalization (Sec. 4.5) is enabled.

| Level | Cell A | Cell B | ≈ px @ 5 m |
|---|---|---|---|
| L0 | 10 m | 10 m | ~107 |
| L1 | 1.25 m | 2.5 m | ~13 / ~27 |
| L2 | 8 cm | 62 cm | ~0.9 / ~6.7 |

> **Table 1.** Asymmetric cell sizes (default). Symmetric variant uses Cell A for both endpoints. Pixel column shows projected Cell A / Cell B side length at 5 m distance, 90° HFoV, 1080p. L2 Cell A is subpixel at 5 m because L2 is only active at close range (distance-gated, Sec. 5).

Cell sizes are calibrated for primary viewing distances of 2–20 m in mixed exterior/interior scenes (Bistro, Sponza). Scenes at substantially different scales (tabletop close-ups, city-scale flyovers) would benefit from camera-adaptive cell sizing via FoV and circle of confusion — deferred to future work.

**LOD asymmetry.** Cell sizes are asymmetric: endpoint A (shading point) is quantized more finely than endpoint B (light source or secondary hit). This is justified for direct illumination where the shading point exhibits more spatial variation (view-dependent BRDF, geometric normal) than the light source (spatially coherent emission). For GI revalidation (Sec. 9), where B is also a surface point, symmetric cells may be more appropriate — we defer this investigation, noting that at L2 both endpoints are typically close spatially, limiting the impact.

**Why a flat hash, not a hierarchy.** Prior multilevel approaches — separate tables per level, octree subdivision [Popov et al. 2013], hierarchical cascade grids — add structural complexity: pointer management, multi-table eviction coordination, variable-depth traversal. A single flat table with level-in-key (Sec. 4.3) is simpler, has uniform access cost, and allows entries at all levels to compete for capacity under one eviction policy. This design emerged after experimenting with alternatives; the flat table consistently performed better for our access pattern (many parallel inserts/lookups with variable level mix).

**Explicit vs. neural.** Compared to neural visibility caches [Bokšanský and Meister 2025], the explicit hash table offers inspectable entries (cached μ and sample count are directly readable), zero inference latency (one hash + one memory read vs. MLP evaluation), predictable cold-start behavior (first sample populates an entry immediately), and tunable parameters with clear semantics. The neural approach offers automatic spatial adaptation without explicit LOD configuration and potentially better generalization. CV+RRR (Sec. 8) applies identically to either data structure.

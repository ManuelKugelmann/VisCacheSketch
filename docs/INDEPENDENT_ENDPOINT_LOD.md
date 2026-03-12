# Independent Per-Endpoint LOD with 2D Variance Cascade

_Design document — future work for VisCache_

---

## Motivation

The current VisCache uses a single LOD level `lvl` in the hash key `(qa, qb, lvl)`, with both endpoints quantized at the same cell size per level. This forces both endpoints to refine in lockstep — wasteful when only one endpoint needs finer resolution.

**Example:** A sharp shadow boundary (endpoint A, the shading point, needs L2 precision) cast by a large area light (endpoint B, spatially coherent emission, only needs L0). The current system must store this at `(2, 2)`, wasting fine resolution on B. With independent endpoint LOD, the entry lives at `(lvlA=2, lvlB=0)` — correct resolution for each endpoint.

## Design

### Hash key: `(qa, qb, lvlA, lvlB)`

Each endpoint gets its own LOD level in the hash key:

- `qa = jitterQuantize(posA, kCell[lvlA], ...)` — A quantized at A's level
- `qb = jitterQuantize(posB, kCell[lvlB], ...)` — B quantized at B's level
- **Single cell size array** `kCell[N]` (geometric progression, same as existing `vhfCellSize()`). The asymmetry comes from endpoints being at *different* levels, not different cell size tables.
- Combined level index for hash: `lvlA * kNumLevels + lvlB`
- With N=3: up to 9 possible `(lvlA, lvlB)` pairs per spatial region

This generalizes the current scheme: the existing 1D cascade `lvl ∈ {0,1,2}` is the diagonal `{(0,0), (1,1), (2,2)}` of the 2D LOD grid.

### 2D Insert Cascade (BFS, 3-way split)

When an entry at `(lvlA, lvlB)` has high variance, it spawns three children — refine A only, refine B only, or refine both:

```
vhfInsert2D(posA, posB, V):
    visited = 0                          // N*N bitmask (9 bits for N=3)
    queue[N*N]; front=0; back=0
    enqueue(0, 0)

    while front < back:
        (a, b) = dequeue()
        idx = a * N + b
        if visited & (1 << idx): continue
        visited |= (1 << idx)

        // Peek existing state (read packed, no atomic)
        existing = vhfPeekAt(posA, posB, a, b)

        if existing.total >= bootThreshold AND existing.var > varThreshold:
            // Known mixed — skip insert, just cascade. Decay revalidates.
            if a+1 < N: enqueue(a+1, b)
            if b+1 < N: enqueue(a, b+1)
            if a+1 < N AND b+1 < N: enqueue(a+1, b+1)
            continue

        // Insert sample and read post-insert variance
        postVar = vhfInsertAt(posA, posB, V, a, b)

        if postVar <= varThreshold: continue   // converged — prune branch

        // High variance — 3-way split
        if a+1 < N: enqueue(a+1, b)
        if b+1 < N: enqueue(a, b+1)
        if a+1 < N AND b+1 < N: enqueue(a+1, b+1)
```

**Skip-known-mixed optimization:** If a coarse entry already has sufficient samples and high variance, it is an established boundary region. Inserting one more sample won't meaningfully change the variance. Skip the insert (save one atomic), cascade directly to children. Decay sweeps revalidate these entries over time.

### 2D Lookup (BFS, coarse-to-fine)

Same BFS structure, read-only. Returns finest converged entry:

```
vhfLookup2D(posA, posB):
    best = MISS
    visited = 0; queue = [(0, 0)]

    while queue not empty:
        (a, b) = dequeue()
        if visited: continue; mark visited

        entry = vhfLookupAt(posA, posB, a, b)
        if not found or too few samples: continue

        best = entry          // BFS is coarse-to-fine, so last valid = finest

        if entry.var <= varThreshold: continue   // converged — don't go finer

        // Expand children
        if a+1 < N: enqueue(a+1, b)
        if b+1 < N: enqueue(a, b+1)
        if a+1 < N AND b+1 < N: enqueue(a+1, b+1)

    return best
```

### LOD range gating

Both endpoints always cascade from L0. No per-endpoint distance-gated range selection — the variance gate itself provides spatial adaptivity. The existing `enableVisCacheDistanceLOD` ablation flag can optionally clamp the start level per endpoint.

## Key Properties

- **N-agnostic:** `kNumLevels` is a compile-time constant; all BFS bounds derived from it. The design works for any N without structural changes.
- **Backward compatible:** The current 1D cascade is the diagonal `lvlA == lvlB` of the 2D grid. Old functions can wrap diagonal-only 2D calls during transition.
- **Self-regulating:** No per-endpoint LOD selection heuristic needed. The variance gate automatically finds the right `(lvlA, lvlB)` pair — if only A needs refinement, the cascade prunes the B dimension early.
- **Skip-known-mixed:** Avoids wasting atomics on established boundary entries at coarse levels. Decay handles revalidation.
- **Max overhead:** N² hash probes per insert/lookup (9 for N=3, vs. 3 for current 1D). In practice, variance gate prunes most branches — uniform visibility regions stop at `(0,0)`.

## Implementation Sketch

### Address and fingerprint

Replace single `uint lvl` with combined level:

```hlsl
uint vhfCombinedLevel(uint lvlA, uint lvlB) { return lvlA * kNumLevels + lvlB; }

uint vhfAddr(int3 qa, int3 qb, uint lvlA, uint lvlB) {
    uint cl = vhfCombinedLevel(lvlA, lvlB);
    uint3 h = pcg3d(uint3(
        uint(qa.x) ^ uint(qb.x),
        uint(qa.y) ^ uint(qb.y),
        (uint(qa.z) ^ uint(qb.z)) + cl * 0x9e3779b9u));
    return (h.x ^ h.y ^ h.z) & (gTableCapacity - 1u);
}
```

### Per-endpoint quantization

Each endpoint uses its own level's cell size:

```hlsl
float csA = vhfCellSize(lvlA);
float csB = vhfCellSize(lvlB);
int3 qa = jitterQuantize(posA, csA, 0xAAu ^ lvlA);
int3 qb = jitterQuantize(posB, csB, 0xBBu ^ lvlB);
```

### Updated result type

```hlsl
struct VHFResult {
    float mu;
    float var;
    int   levelA;   // was: level
    int   levelB;   // new
    bool  valid;
};
```

## Expected Behavior by Scenario

| Scenario | Expected populated entries |
|---|---|
| Uniform visibility | Only `(0,0)` — variance gate stops immediately |
| Shadow boundary, large area light | `(2,0)` or `(2,1)` — A refined, B coarse |
| Fine point light shadow | `(2,2)` — both endpoints need refinement |
| GI bounce (surface-to-surface) | `(1,1)` or `(2,2)` — symmetric refinement |
| Known-mixed coarse | `(0,0)` skipped on insert, children populated |

## Open Questions

1. **BFS ordering for lookup:** When multiple converged entries exist at different `(lvlA, lvlB)` pairs (e.g., `(2,0)` and `(0,2)` are both converged), which is "best"? Currently the BFS returns the last visited valid entry. A better heuristic might prefer entries with higher `max(lvlA, lvlB)` or `lvlA + lvlB`.

2. **WaveMatch interaction:** Coalescing groups lanes by `addr`. With 2D LOD, `addr` depends on `(lvlA, lvlB)`, so threads targeting the same spatial region but different LOD pairs will not coalesce. The coarsest pair `(0,0)` still benefits most from coalescing, which is where contention is highest.

3. **Table pressure:** With up to N² entries per region (vs. N), the effective table occupancy increases. The flat table handles this naturally via pressure-scaled eviction, but the table capacity may need to increase. Alternatively, the variance gate's pruning keeps actual occupancy close to the 1D case for most regions.

4. **Coupled variance adaptation:** The current coupling (same variance signal drives RR probability AND write-depth gate) extends to 2D: the variance at each `(lvlA, lvlB)` entry gates its own subtree. High-variance entries cascade to children; low-variance entries are leaves.

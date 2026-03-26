# 4. Addressing

## 4.1 Key Structure: Position+Normal × Direction+Distance

The hash key encodes the shading point and the query direction
as two independent groups:

- **Endpoint A (shading point):** position + surface normal.
- **Endpoint B (query):** direction from A to target + distance to target.

This decomposition exploits free geometric information
that a symmetric position × position key cannot:

1. **Normal disambiguates local geometry.**
   Two nearby points on opposite sides of a thin wall,
   or on adjacent faces of a corner,
   share the same position cell but have different normals.
   Without the normal, they would alias into one entry,
   averaging contradictory visibility.
   The surface normal is available at no cost
   (already computed for shading)
   and separates entries that position alone conflates.

2. **Direction enables angular LOD.**
   The angular bin size is a variance-gatable refinement axis,
   analogous to spatial LOD:
   coarse bins (large solid angle) suffice in open regions;
   fine bins are needed only where visibility varies with direction
   (e.g. looking past a pillar edge).
   A symmetric position × position key has no natural angular LOD structure.

3. **Distance enables free monotonicity propagation.**
   Visibility along a ray is monotone in distance:
   if an occluder exists at d, everything farther is also blocked.
   This is a geometric invariant, not an adaptive choice.
   When a trace returns V=0,
   the occluder distance d\_hit (available from any-hit via `CommittedRayT()` at zero cost)
   allows writing V=0 to all distance bins with d\_max ≥ d\_hit.
   When V=1, write V=1 to all bins with d\_max ≤ d\_query.
   One shadow ray populates an entire column of distance bins for free.
   A position × position key cannot exploit this —
   the second endpoint is a position with no distance decomposition.

The alternative position × position addressing
(both endpoints quantized as positions)
remains available for symmetric queries (GI revalidation,
where both endpoints are surface points and
canonicalization V(A,B) = V(B,A) halves table pressure).
But for the general case — direct lighting, IBL, area lights —
position+normal × direction+distance is the primary mode
because it exploits geometric information that is already available for free.

## 4.2 Quantization

Position quantization uses absolute cell-size division:
int3(floor(pos / cell_size)).
No scene bounds needed — works for any position in infinite space
[Teschner et al. 2003].
Normal quantization uses octahedral mapping
(same encoding as for infinite endpoints)
at a configurable angular cell size.
Direction quantization uses the same octahedral mapping
at its own angular cell size (the angular LOD parameter).
Distance bins are nested intervals [0, d\_max(l)]
with geometric (log) spacing;
the coarsest bin [0, ∞) collapses to direction-only
(no distance discrimination),
while finer bins add distance resolution where visibility varies with range.
A natural parameterization ties distance thresholds
to the spatial cell sizes:
d\_max(l) = cell\_size(l) × distance\_scale (one additional scalar parameter).
The LOD level index is concatenated into the hash key [Gautron 2020],
so entries at different resolutions coexist in one flat table.

## 4.3 Position-Seeded Jitter as Box Filter

Jitter uses pcg3d [Jarzynski & Olano, 2020], seeded from the unquantized position bits asuint(pos). Each surface point gets deterministic but spatially decorrelated jitter — a fixed world-space point always maps to the same cell, but nearby points near a cell boundary may map to different cells.

This is the key departure from Binder et al. [2018], whose jitter is shared within a cell (ensuring all positions in one cell receive the same displacement). This maximizes samples per cell but creates sharp step functions at (irregularly placed) cell boundaries — a systematic, persistent bias that does not diminish with accumulation.

**The jitter *is* the filter.** Position-seeded jitter gives probabilistic cell membership near boundaries: a surface point at distance d from a cell edge has probability d/cell_size of mapping to the adjacent cell. Across many samples, this produces an intrinsic box filter of width cell_size centered on the boundary. The filter requires no explicit smoothing pass, no bilateral weights, no neighbor polling — it emerges directly from the addressing scheme. The marginal variance increase from boundary dilution is noise that reduces with sample count, while Binder's boundary steps are irreducible bias. Eliminating bias at the cost of slightly more reducible variance is the standard Monte Carlo trade-off — the same principle that makes stochastic sampling preferable to regular grids.

## 4.4 LOD in the Hash Key

The LOD level index is part of the hash input [Gautron 2020, 2021]. This is simpler and more effective than alternatives we considered:

- **Separate tables per level:** Wastes memory when levels have different occupancy. Requires managing multiple table sizes, eviction policies, and decay rates independently.
- **Hierarchical indirection:** Tree-like structures (octrees, cascaded grids) add pointer-chasing latency and complicate lock-free GPU updates.
- **Shared table without level in key:** Entries at different resolutions collide, corrupting both.

With level-in-key, a coarse L0 entry and a fine L2 entry for the same spatial region are simply different keys in the same flat table. They are inserted, evicted, and decayed independently. The variance-gated cascade (Sec. 5) controls which levels are populated: coarse levels converge first; finer levels fill only where variance remains high. No distance heuristic is needed — the cascade is self-regulating. The flat-table design also means LOD level naturally participates in load balancing — underused levels take less table space, freeing capacity for levels under pressure.

Spatial cell size is one LOD dimension; angular bin size is another.
Both follow geometric progressions from coarse to fine
and are variance-gated independently.
Distance is not an LOD dimension —
distance propagation exploits a geometric invariant (Sec. 4.1),
not an adaptive refinement choice.

## 4.5 Collision Detection

Fingerprint uses the same jittered+quantized coordinates as the address but a different hash function [Binder et al., 2018]. Binder et al. use linear probing; we use standard double hashing [Knuth 1973] with the fingerprint as h2, which distributes probe chains more uniformly under high load. The fingerprint detects collisions at lookup time: if the stored fingerprint does not match, the entry belongs to a different key. False positives (two different keys producing identical fingerprint and table slot) are possible but rare — at 32-bit fingerprint, the probability is ~2⁻³² per probe step.

## 4.6 Infinite Endpoints and Position × Position Mode

IBL samples and directional lights have no finite position;
the direction+distance encoding handles them naturally
(direction is finite, distance = ∞, mapping to the coarsest distance bin [0, ∞)).

For symmetric queries where both endpoints are surface points —
primarily GI revalidation (Sec. 9.3) —
position × position addressing with bidirectional canonicalization
(lexicographic swap merging V(P,Q) and V(Q,P))
doubles effective cache utilization.
This requires symmetric cell sizes
and sacrifices the normal, angular, and distance dimensions.
The two modes coexist in the same hash table via the level-in-key design;
entries from different addressing modes use different key encodings
and do not collide.

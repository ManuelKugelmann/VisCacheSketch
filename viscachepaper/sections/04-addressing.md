# 4. Addressing

## 4.1 Quantization

Quantization uses absolute cell-size division: int3(floor(pos / cell_size)). No scene bounds needed — works for any position in infinite space [Teschner et al. 2003]. Both endpoints are jittered independently before quantization, with magnitude = cell_size. The LOD level index is concatenated into the hash key [Gautron 2020], so entries at different resolutions coexist in one flat table with no indirection.

## 4.2 Position-Seeded Jitter as Box Filter

Jitter uses pcg3d [Jarzynski & Olano, 2020], seeded from the unquantized position bits asuint(pos). Each surface point gets deterministic but spatially decorrelated jitter — a fixed world-space point always maps to the same cell, but nearby points near a cell boundary may map to different cells.

This is the key departure from Binder et al. [2018], whose jitter is shared within a cell (ensuring all positions in one cell receive the same displacement). This maximizes samples per cell but creates sharp step functions at (irregularly placed) cell boundaries — a systematic, persistent bias that does not diminish with accumulation.

**The jitter *is* the filter.** Position-seeded jitter gives probabilistic cell membership near boundaries: a surface point at distance d from a cell edge has probability d/cell_size of mapping to the adjacent cell. Across many samples, this produces an intrinsic box filter of width cell_size centered on the boundary. The filter requires no explicit smoothing pass, no bilateral weights, no neighbor polling — it emerges directly from the addressing scheme. The marginal variance increase from boundary dilution is noise that reduces with sample count, while Binder's boundary steps are irreducible bias. Eliminating bias at the cost of slightly more reducible variance is the standard Monte Carlo trade-off — the same principle that makes stochastic sampling preferable to regular grids.

## 4.3 LOD in the Hash Key

The LOD level index is part of the hash input [Gautron 2020, 2021]. This is simpler and more effective than alternatives we considered:

- **Separate tables per level:** Wastes memory when levels have different occupancy. Requires managing multiple table sizes, eviction policies, and decay rates independently.
- **Hierarchical indirection:** Tree-like structures (octrees, cascaded grids) add pointer-chasing latency and complicate lock-free GPU updates.
- **Shared table without level in key:** Entries at different resolutions collide, corrupting both.

With level-in-key, a coarse L0 entry and a fine L2 entry for the same spatial region are simply different keys in the same flat table. They are inserted, evicted, and decayed independently. The distance-gated level selection (Sec. 5) acts as a clipmap: L0 for far field, L2 for near field, L1 as bridge. The flat-table design also means LOD level naturally participates in load balancing — underused levels take less table space, freeing capacity for levels under pressure.

## 4.4 Collision Detection

Fingerprint uses the same jittered+quantized coordinates as the address but a different hash function [Binder et al., 2018]. Binder et al. use linear probing; we use standard double hashing [Knuth 1973] with the fingerprint as h2, which distributes probe chains more uniformly under high load. The fingerprint detects collisions at lookup time: if the stored fingerprint does not match, the entry belongs to a different key. False positives (two different keys producing identical fingerprint and table slot) are possible but rare — at 32-bit fingerprint, the probability is ~2⁻³² per probe step.

## 4.5 Infinite Endpoints

IBL samples use a virtual far endpoint; a 1-bit is_inf flag selects angular quantization (octahedral mapping) for infinite endpoints (IBL, directional lights) vs positional quantization for finite surfaces, preventing collisions between the two address spaces. Optional bidirectional canonicalization (lexicographic swap) merges V(P,Q) and V(Q,P) into one entry; requires symmetric cell sizes and applies only to finite×finite pairs.

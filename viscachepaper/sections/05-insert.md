# 5. Insert

Each level's variance gates writes to the next finer level. The coarsest level is always written; after each write, the level's post-increment variance is checked — if it falls below τ, propagation stops and no finer levels are written. During bootstrap (insufficient samples), variance is above τ by construction, so all levels fill unconditionally. This is the same variance signal that drives adaptive sampling in Sec. 8 (see coupled variance adaptation). A distance interval gates the LOD range by target square pixel footprint: skip levels where the cell is below 4×4 pixels or above 64×64 pixels. Clipmap-like: L0 far field, L2 near field, L1 bridges. Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync; the post-increment value is used directly for the variance check, avoiding a separate lookup.

**Algorithm 1: Distance + Variance-Gated Insert**
```
Input: pos_a, pos_b, visibility V, camera_pos
di <- distance_lod_interval(pos_a, camera_pos)
for l <- di.min_level to di.max_level do
  jitter pos_a by cell_size(l)
  cur <- try_insert(hash(pos_a,pos_b,l), fp(pos_a,pos_b,l), V)
  if cur.total >= w_bootstrap and variance(cur) <= tau then
    break                                // this level is smooth — stop
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

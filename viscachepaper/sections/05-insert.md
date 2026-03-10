# 5. Insert

L0 is read to decide write depth. During bootstrap, all levels are written. Once L0 matures, fine levels are written only where L0 variance exceeds a threshold — the same variance signal that drives adaptive sampling in Sec. 8 (see coupled variance adaptation). A distance interval gates the LOD range by target square pixel footprint: skip levels where the cell is below 4×4 pixels or above 64×64 pixels. Clipmap-like: L0 far field, L2 near field, L1 bridges. Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync.

**Algorithm 1: Distance + Variance-Gated Insert**
```
Input: pos_a, pos_b, visibility V, camera_pos
di <- distance_lod_interval(pos_a, camera_pos)
r0 <- lookup_single(pos_a, pos_b, di.min_level)
if r0 = MISS or r0.weight < w_bootstrap then
  var_max <- N_LEVELS - 1               // bootstrap
else if r0.variance > tau then
  var_max <- N_LEVELS - 1               // boundary
else
  var_max <- di.min_level               // smooth
max_level <- min(di.max_level, var_max)
for l <- di.min_level to max_level do
  jitter pos_a by cell_size(l)
  try_insert(hash(pos_a,pos_b,l), fp(pos_a,pos_b,l), V)
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

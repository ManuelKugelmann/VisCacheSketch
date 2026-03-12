# 5. Insert

Two gates control the coarse-to-fine cascade L0..N-1:

1. **Maturity gate** (before write): skip entries where the standard error is already small enough. Required samples scale with variance: `n_required = μ(1−μ) · boot / τ`, where boot (= gBootThreshold, default 32) is the minimum sample count for a fully uncertain entry (μ=0.5) and τ (= gVarThreshold) is the variance gate. Unanimous cells (μ≈0 or μ≈1) mature in few samples; shadow boundaries (μ≈0.5) need more. Decay periodically subtracts 1/8 of both counters (factor 0.875 per pass), temporarily un-maturing entries for revalidation — no coin flip needed.

2. **Cascaded variance gate** (after write): if this level's post-increment variance falls below τ, stop — finer levels would agree. During bootstrap (insufficient samples), variance is above τ by construction, so all levels fill unconditionally.

Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync; the post-increment value is used directly for the variance check, avoiding a separate lookup.

**Algorithm 1: Maturity + Variance-Gated Insert**
```
Input: pos_a, pos_b, visibility V
for l <- 0 to N-1 do
  (qa, qb) <- quantize_pair(pos_a, pos_b, cell_size(l), l)
  addr <- hash(qa, qb, l); fp <- fingerprint(qa, qb, l)
  if is_mature(addr, fp) then continue   // enough samples at this level
  cur <- try_insert(addr, fp, V)
  if cur.total >= boot and variance(cur) <= tau then
    break                                // this level is smooth — stop
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

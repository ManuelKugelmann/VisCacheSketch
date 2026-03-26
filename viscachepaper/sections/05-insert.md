# 5. Insert

Three gates control the coarse-to-fine cascade L0..N-1.
Each entry transitions through three states:

- **Bootstrap** (total < n_useable): receiving writes, but too few samples to guide children. The cascade does not propagate past this level.
- **Useable** (total ≥ n_useable, variance > τ): receiving writes AND cascading to children. The entry's μ is rough but sufficient as a parent control variate for finer levels.
- **Mature** (SE below threshold): no longer receiving writes — further samples are wasted. The cascade still propagates to children, since finer levels may need refinement even when the parent is converged.

The three gates:

1. **Maturity gate** (before write): skip entries where the standard error is already small enough. Required samples scale with variance: `n_required = μ(1−μ) · boot / τ`, where boot (= gBootThreshold, default 32) is the minimum sample count for a fully uncertain entry (μ=0.5) and τ (= gVarThreshold) is the variance gate. Unanimous cells (μ≈0 or μ≈1) mature in few samples; shadow boundaries (μ≈0.5) need more. Decay periodically subtracts 1/8 of both counters (factor 0.875 per pass), temporarily un-maturing entries for revalidation — no coin flip needed.

2. **Useable gate** (after write): if this level has too few samples (total < n_useable, default ~8), stop — the entry's μ is not yet reliable enough to bootstrap children. This separates the question "can this entry guide its children?" (low threshold) from "has this entry converged?" (high threshold). At L0, where thousands of pixels share a cell, useable is reached within the first frame; children start accumulating immediately rather than waiting for full convergence. When a child entry is first created, it inherits the parent's μ as initial data at reduced weight — equivalent to a few decay steps (e.g., parent counts right-shifted by 3, giving 1/8 of the parent's sample count). This seeds the child with a reasonable control variate from the first trace rather than bootstrapping from zero. The reduced weight ensures the parent's coarser-resolution estimate is quickly overridden by the child's own observations at finer resolution.

3. **Cascaded variance gate** (after write): if this level's post-increment variance falls below τ, stop — finer levels would agree.

The variance-gated cascade implicitly discovers the local *visibility correlation length* — the spatial scale below which visibility is effectively constant. A level converges when its cell size is at or below this scale; the cascade stops because finer levels would see the same value. No explicit correlation estimation is needed; the Bernoulli variance signal is a sufficient proxy, and the system adapts automatically to the actual visibility field rather than to a model of it.

Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync; the post-increment value is used directly for the variance check, avoiding a separate lookup.

**Algorithm 1: Maturity + Useable + Variance-Gated Insert**
```
Input: pos_a, pos_b, visibility V
for l <- 0 to N-1 do
  (qa, qb) <- quantize_pair(pos_a, pos_b, cell_size(l), l)
  addr <- hash(qa, qb, l); fp <- fingerprint(qa, qb, l)
  if is_mature(addr, fp) then continue   // stop writing, but cascade continues
  cur <- try_insert(addr, fp, V)
  if cur.total < n_useable then
    break                                // not enough data to guide children
  if variance(cur) <= tau then
    break                                // this level is smooth — stop
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

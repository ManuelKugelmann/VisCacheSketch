# 5. Insert

Three gates control the coarse-to-fine cascade L0..N-1.
Each entry transitions through three states:

- **Bootstrap** (total < τ_useable): receiving writes, but too few samples to guide children. The cascade does not propagate past this level.
- **Useable** (total ≥ τ_useable, variance > τ_var): receiving writes AND cascading to children. The entry's μ is rough but sufficient as a parent control variate for finer levels.
- **Mature** (SE below τ_mature): no longer receiving writes — further samples are wasted. The cascade still propagates to children, since finer levels may need refinement even when the parent is converged.

Two thresholds and one variance gate control the transitions:

- **τ_useable** (= gUseableThreshold, default 8): minimum sample count before children may be written. Low by design — a rough μ from ~8 samples is sufficient as a parent control variate. At L0, where thousands of pixels share a cell, τ_useable is reached within the first frame; children start accumulating immediately rather than waiting for full convergence. When a child entry is first created, it inherits the parent's μ as initial data at reduced weight — equivalent to a few decay steps (e.g., parent counts right-shifted by 3, giving 1/8 of the parent's sample count). This seeds the child with a reasonable control variate from the first trace rather than bootstrapping from zero. The reduced weight ensures the parent's coarser-resolution estimate is quickly overridden by the child's own observations at finer resolution.

- **τ_mature** (= gMatureThreshold, default 32 at μ=0.5): sample count at which an entry stops accepting writes. Scales with variance: `n_mature = μ(1−μ) · τ_mature / τ_var`. Unanimous cells (μ≈0 or μ≈1) mature in few samples; shadow boundaries (μ≈0.5) need the full τ_mature. Decay periodically subtracts 1/8 of both counters (factor 0.875 per pass), temporarily un-maturing entries for revalidation — no coin flip needed.

- **τ_var** (= gVarThreshold): the variance gate. After writing, if this level's post-increment variance falls below τ_var, stop — finer levels would agree.

The variance-gated cascade implicitly discovers the local *visibility correlation length* — the spatial scale below which visibility is effectively constant. A level converges when its cell size is at or below this scale; the cascade stops because finer levels would see the same value. No explicit correlation estimation is needed; the Bernoulli variance signal is a sufficient proxy, and the system adapts automatically to the actual visibility field rather than to a model of it.

Both-endpoint jitter is in the addressing step (Sec. 4). Single InterlockedAdd on packed uint ensures counters stay in sync; the post-increment value is used directly for the variance check, avoiding a separate lookup.

**Algorithm 1: Insert with τ_mature, τ_useable, and τ_var**
```
Input: pos_a, pos_b, visibility V
for l <- 0 to N-1 do
  (qa, qb) <- quantize_pair(pos_a, pos_b, cell_size(l), l)
  addr <- hash(qa, qb, l); fp <- fingerprint(qa, qb, l)
  if total(addr) >= tau_mature then continue   // mature — skip write, cascade continues
  cur <- try_insert(addr, fp, V)
  if cur.total < tau_useable then
    break                                      // bootstrap — not enough to guide children
  if variance(cur) <= tau_var then
    break                                      // smooth — finer levels would agree
```

The cache is live during the frame (not double-buffered). At L0 (43), each cell spans thousands of pixels. After ~1K shadow rays, L0 is substantially populated. An ABA race exists when two threads simultaneously find an empty slot (fp=0) and both claim it via CompareExchange — the second overwrites the first, wasting one traced sample. At L0 with warp reduction (~16 atomics/cell/frame), the collision rate is negligible. At L2 without warp reduction, the rate is approximately 1/waveSize ≈ 3% of inserts per contested cell. The wasted sample does not affect the surviving entry's mean. A 64-bit CAS on a combined {fingerprint, packed} entry would eliminate the race at the cost of doubling entry size. On SM6.5+, warp-level reduction via WaveMatch coalesces threads targeting the same cell into a single atomic (~16× reduction at L0). The packed format enables this directly — merging N samples is one InterlockedAdd of (vis_count&lt;&lt;16 | total_count).

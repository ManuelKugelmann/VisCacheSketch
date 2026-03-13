# Ablation Matrix
_Paper §15 — all configurations and metric targets_

---

## Toggle reference

| Toggle | Parameter | Off behaviour | Ablation label |
|--------|-----------|--------------|---------------|
| B | `enableVisCacheVarianceGate` | Write fine levels in all regions | −B |
| C | `enableVisCacheWarpReduction` | Per-lane atomics at L0 | −C |
| D | `enableVisCacheDecay` | No counter decay | −D |
| E | `enableVisCachePressureEvict` | Evict from step 0 | −E |
| — | `numLevels=1` | Single level only | Single-level |
| — | VisCache disabled entirely | Full retrace baseline | No-cache |

---

## Configuration matrix

| Config | B | C | D | E | Primary claim tested |
|--------|---|---|---|---|---------------------|
| Full | ✅ | ✅ | ✅ | ✅ | Baseline |
| −B | ❌ | ✅ | ✅ | ✅ | Variance gate prevents wasteful fine writes |
| −C | ✅ | ❌ | ✅ | ✅ | WaveMatch reduces L0 contention ~16× |
| −D | ✅ | ✅ | ❌ | ✅ | Decay prevents mean drift |
| −E | ✅ | ✅ | ✅ | ❌ | Pressure eviction controls probe chains |
| Single-level | ✅ | ✅ | ✅ | ✅ | Multilevel necessary for GI amortization |
| No-cache | — | — | — | — | Full-retrace ground truth |

---

## Per-config expected results

**−B (no variance gate) — most important ablation:**
- Fine level writes increase in smooth (low-variance) regions
- Expected: negligible MSE gain, measurable insert cost increase
- If MSE improves significantly → VAR_THR is too low, raise it before submission
- If insert cost doesn't increase → gate is never triggering, investigate

**−C (no WaveMatch):**
- L0 atomic contention increases ~16×
- GPU timestamp for insert pass increases
- No effect on output quality
- Requires SM 6.5 comparison — run on RTX 3090 / 4090 only

**−D (no decay):**
- Mean drift visible after ~1000 frames with moving lights
- Static scenes: no measurable effect
- Animated scenes: bias accumulates, hit rate stays high but µ is stale
- Run disocclusion stress test to show drift

**−E (no pressure eviction):**
- Probe chain length increases under load
- Miss rate increases in dense scenes
- Insert cost increases (longer probes)

**Single-level (numLevels=1):**
- Cold start brutal: many shadow rays per cell before VAR_THR reached
- GI path-sharing amortization breaks
- Camera motion: fine cells go cold immediately, p=1 for many frames
- Warm-up curve shape: frames to 80% hit rate should be dramatically worse
- This is the key architectural validation test

---

## Contention management

LOD contention is handled dynamically — no static threshold or distance heuristic:

1. **Maturity gate** (before write): if total >= bootThreshold, skip the
   atomic. The entry has enough samples — whether low-var (smooth) or
   high-var (shadow boundary), additional writes have diminishing returns.
   Background decay periodically halves counts, temporarily un-maturing
   entries for fresh sampling (revalidation). No coin flip needed.

2. **Cascaded variance gate** (after write): if var <= varThreshold, stop
   descending to finer levels — this region is smooth, finer detail is
   wasteful. Only applies to cold entries being populated.

3. **WaveMatch coalescing** (SM 6.5): in the batched insert pass,
   WaveMatch coalesces threads targeting the same cell into a single atomic.

---

## Metrics per config (Bistro + Sponza)

### Primary
- Shadow ray reduction ratio (vs. no-cache baseline)
- Per-pixel MSE vs. 1024 spp reference
- GPU timestamp breakdown: insert / lookup / decay ms

### Secondary
- Cache hit rate (trusted entries / total queries)
- Average probe depth (stats buffer)
- Cache miss rate (cold queries / total)

### Convergence (animated / flythrough)
- Frames to 80% hit rate from cold start
- Variance spike duration after disocclusion
- Peak shadow ray ratio during cold-start

---

## Capture settings

- Warm-up: 200 frames (cache reaches steady state)
- Capture: 16 frames per config
- Format: EXR (linear HDR)
- Reference: 1024 spp path tracer, same scene, same camera
- Scenes: BistroInterior.pyscene, Sponza.pyscene

See `scripts/VisCache_Ablation.py` for automated capture.

---

## Disocclusion stress test

Fast camera flythrough — one full room traversal in 60 frames.

Metrics:
- Frames to 80% hit rate post-disocclusion event
- Variance spike duration (frames with MSE > 2× steady-state)
- Peak shadow ray ratio during cold-start

Expected: graceful degradation. At disocclusion: p rises to 1 in uncovered region, traces at full rate, warms up within 32–64 frames (bootThreshold). Full-retrace cost during cold-start period, then savings resume.

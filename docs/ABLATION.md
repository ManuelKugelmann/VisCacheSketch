# Ablation Matrix
_Paper §15 — all configurations and metric targets_

---

## Toggle reference

| Toggle | Parameter | Off behaviour | Ablation label |
|--------|-----------|--------------|---------------|
| A | `enableDistanceLOD` | Write all levels always | −A |
| B | `enableVarianceGate` | Write fine levels in all regions | −B |
| C | `enableWarpReduction` | Per-lane atomics at L0 | −C |
| D | `enableDecay` | No counter decay | −D |
| E | `enablePressureEvict` | Evict from step 0 | −E |
| — | `minLevel=maxLevel=2` | Finest level only | Finest-only |
| — | `minLevel=maxLevel=0` | Coarsest level only | Coarsest-only |
| — | VHF disabled entirely | Full retrace baseline | No-cache |

---

## Configuration matrix

| Config | A | B | C | D | E | Primary claim tested |
|--------|---|---|---|---|---|---------------------|
| Full | ✅ | ✅ | ✅ | ✅ | ✅ | Baseline |
| −A | ❌ | ✅ | ✅ | ✅ | ✅ | LOD gate reduces insert cost |
| −B | ✅ | ❌ | ✅ | ✅ | ✅ | Variance gate prevents wasteful fine writes |
| −C | ✅ | ✅ | ❌ | ✅ | ✅ | WaveMatch reduces L0 contention ~16× |
| −D | ✅ | ✅ | ✅ | ❌ | ✅ | Decay prevents mean drift |
| −E | ✅ | ✅ | ✅ | ✅ | ❌ | Pressure eviction controls probe chains |
| −AB | ❌ | ❌ | ✅ | ✅ | ✅ | Combined pressure stress |
| Finest-only | ✅ | ✅ | ✅ | ✅ | ✅ | Multilevel necessary for GI amortization |
| Coarsest-only | ✅ | ✅ | ✅ | ✅ | ✅ | Coarse level insufficient for shadow boundaries |
| No-cache | — | — | — | — | — | Full-retrace ground truth |

---

## Per-config expected results

**−A (no distance LOD):**
- Insert cost increases (all levels written everywhere)
- Load factor increases, eviction rate rises
- MSE: negligible change (same mean estimate)
- Claim: LOD gate earns its keep on performance, not quality

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

**Finest-only (minLevel=maxLevel=2):**
- Cold start brutal: 50–100 shadow rays per L2 cell before VAR_THR reached
- GI path-sharing amortization breaks: 50–100 pixels → 50–100 distinct L2 cells (not 3–5 L0 cells)
- Camera motion: L2 goes cold immediately (8cm cells), p=1 for many frames
- Warm-up curve shape: number of frames to reach 80% hit rate should be dramatically worse
- This is the key architectural validation test

**Coarsest-only (minLevel=maxLevel=0):**
- Shadow boundaries cannot be resolved at 10m cells
- High variance never decreases → p stays near 1 → few savings
- GI revalidation: coarse V estimate, high residuals in ReSTIR merge

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
- Scenes: Bistro_Interior.pyscene, Sponza.pyscene

See `scripts/MLVHF_Ablation.py` for automated capture.

---

## Disocclusion stress test

Fast camera flythrough — one full room traversal in 60 frames.

Metrics:
- Frames to 80% hit rate post-disocclusion event
- Variance spike duration (frames with MSE > 2× steady-state)
- Peak shadow ray ratio during cold-start

Expected: graceful degradation. At disocclusion: p rises to 1 in uncovered region, traces at full rate, warms up within 32–64 frames (bootThreshold). Full-retrace cost during cold-start period, then savings resume.

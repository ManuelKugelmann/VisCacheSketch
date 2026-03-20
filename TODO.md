# TODO — Global Task Tracker

**Project:** Unbiased World-Space Visibility Caching for Real-Time ReSTIR Path Tracing

---

## Legend

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — done

Priority tags: **CRITICAL** (blocks submission), **HIGH** (significant gap), normal (polish).

---

## 1. Implementation

### 1.1 ReSTIR GI Integration
- [ ] **CRITICAL** Port DQLin/ReSTIR_PT into Falcor fork (`Falcor`)
  - Fork NVIDIAGameWorks/Falcor → ManuelKugelmann/Falcor
  - Apply API migration (see `docs/PORTING.md`)
  - Merge full DQLin reservoir logic into sketch files
- [ ] Verify ported pass matches DQLin reference images on Bistro (FLIP < 0.01)
- [ ] Verify k=5.0 traces/pixel with VisCache disabled
- [ ] Enable VisCache, verify traces/pixel drops to ~0.5–1.0 at steady state

### 1.2 Open Implementation Questions
- [ ] **HIGH** ABA race in inline decay: quantify error rate empirically or replace with 64-bit CAS
- [ ] Cell sizes at non-standard scene scales (0.5m close-up, 100m city flyover)
- [ ] Symmetric cells for GI revalidation — measure error before changing constants
- [ ] Camera-adaptive cell sizing (FoV + CoC) — future work, document only
- [ ] Coarse-to-fine blending: gate descent on coarse usability, blend coarse data into new fine entries.
  Inspired by SHaRC's `SHARC_BLEND_ADJACENT_LEVELS` (blends data between adjacent levels on
  camera move), adapted for VisCache's fixed LOD (not camera-distance-based).
  Design (two rules in `vhfInsert`'s existing coarse→fine loop):
  1. **Don't descend** to level N+1 while level N is below `bootThreshold`. Coarse must
     have enough samples to provide a usable direction before fine levels exist at all —
     saves table capacity and atomics.
  2. **Blend on creation**: when descending past a usable coarse level and claiming a new
     fine-level slot (`origFp == 0`), blend a small amount of coarse-level data into the
     new entry's initial counts. Blend count should be low — coarse mu can be substantially
     wrong for a specific fine cell (e.g., coarse mu=0.8 but fine cell is deep shadow
     mu=0.0). The fine level still needs significant real samples to refine past the
     blended prior and become trustworthy.
  Implementation: carry `prevMu`/`prevTotal` through loop (already in registers from
  the coarse level's `InterlockedAdd` return). Zero extra lookups, zero extra atomics —
  just a wider initial `delta` and an early `break` when coarse is immature.
  Tuning: blend count and the gap to `bootThreshold` need empirical tuning — too high
  locks in wrong coarse mu, too low provides no benefit over cold start.
- [ ] Jittered multi-sample read: blend on read by sampling multiple neighboring cells.
  Instead of blending coarse→fine at write time, blend at lookup time by jittering the
  query position and reading multiple nearby cells within the same level. Averages out
  cell-boundary artifacts and effectively interpolates mu across neighbors. Trades extra
  lookups per query for smoother estimates without polluting write statistics.
  Ablation question: jitter-on-write (current ablation F) vs jitter-on-read vs both.
  Current jitter-before-quantize randomizes cell assignment at write time. Jittered
  multi-sample read randomizes at lookup time instead (or additionally). Need A/B/AB
  ablation to determine which provides more benefit — they address different artifacts
  (write jitter: cell-boundary banding; read jitter: cell-boundary discontinuities in mu).
- [ ] WaveMatch coalesced reads: wave-level grouping already merges N writes to same cell
  into 1 atomic (SM 6.5). Same grouping could coalesce reads — multiple pixels in a wave
  querying the same coarse cell get a single lookup + broadcast. Free bandwidth savings at
  coarse LODs where many pixels map to one cell. Evaluate: measure read divergence at L0
  to see if coalescing provides meaningful savings.
- [ ] Maturity gate / boot threshold unification: write-side maturity gate (stop accumulating
  when SE is low) and read-side boot threshold (don't trust until N samples) are related but
  NOT duals — read threshold should be lower than write threshold since we want to use cells
  earlier than we stop writing to them. Explore: single adaptive threshold framework with
  separate read/write offsets derived from the same variance signal, reducing from two
  independent tuning knobs to one base + two offsets.
- [ ] CV+RRR beyond visibility: the prediction-with-correction estimator E[μ + (V−μ)/p]
  works for any cached mean, not just binary visibility. Applicable to cached irradiance
  (radiance cache + correction rays), cached BRDF importance, cached path throughput for
  ReSTIR resampling weights. The Bernoulli variance-for-free trick is visibility-specific,
  but the CV structure transfers anywhere there's a stale mean estimate. Note: this
  generalization was already explored in [Kugelmann 2006] experiment (2) for irradiance.
- [ ] Symmetric canonicalization beyond visibility: V(A,B)=V(B,A) trick halves table pressure.
  Same idea applies to any symmetric pairwise cache: mutual visibility between light clusters,
  bidirectional form factors, reciprocal BSDF lobes.
- [ ] Pressure-scaled eviction → ReSTIR reservoir management: graduated-threshold eviction
  (deeper probe = easier to evict) could transfer to screen-space reservoir caches. Reservoirs
  that took more probes to place could be marked lower-priority for resampling, naturally
  prioritizing well-placed reservoirs.

  Note on lazy decay on read (rejected): removing the background management pass and decaying
  only on read would leave un-queried stale entries undecayed indefinitely — they never get
  read or written, so they never decay, bloating the table with dead entries that block
  eviction. The management pass is uniform over the table and very fast (simple stride over
  flat array), so the savings from lazy decay don't justify the stale-entry problem.

  Note on probe-depth as read-side confidence signal (rejected): probe depth in a double-hash
  table is determined by collision patterns, not entry quality. High probe depth means the
  slot was found after several collisions — this is random, not a meaningful quality signal.
  Unlike eviction (where depth correlates with table pressure), weighting read results by
  depth would add noise without useful information.

---

## 2. Experiments & Ablation

### 2.0 Setup
- [x] Ablation capture script (`scripts/VisCache_Ablation.py` — 10 configs)
- [x] Baseline capture script (`scripts/VisCache_Baselines.py` — 14 DI/GI/PT configs)
- [x] Reference capture script (`scripts/VisCache_Reference.py` — 1024 spp)
- [x] Stress test script (`scripts/VisCache_Stress.py` — flythrough)
- [x] Scene download script (`scripts/download_scenes.sh` — Bistro, Sponza)
- [x] Full paper runner (`scripts/run_paper_experiments.sh` — runs all of the above)
- [x] Manual release workflow (`.github/workflows/release.yml` — timestamp+SHA versioning)
- [ ] Download test scenes: `./scripts/download_scenes.sh`

### 2.1 Ablation Sweep (see `docs/ABLATION.md` for full matrix)
Run: `./scripts/run_paper_experiments.sh` (or individual scripts below)
- [ ] **CRITICAL** Run at least one informal Bistro profiling data point (blocks §15)
- [ ] Full config baseline capture (Bistro + Sponza) — `scripts/VisCache_Baselines.py`
- [ ] -A: distance-gated LOD off
- [ ] -B: variance gate off (most important ablation)
- [ ] -C: WaveMatch off (SM 6.5 comparison, RTX 3090/4090)
- [ ] -D: decay off (animated scene, show drift after ~1000 frames)
- [ ] -E: pressure eviction off
- [ ] -AB: combined pressure stress
- [ ] Finest-only (minLevel=maxLevel=2) — key architectural validation
- [ ] Coarsest-only (minLevel=maxLevel=0)
- [ ] No-cache full-retrace baseline
- [ ] **HIGH** Add multilevel vs. finest-level-only ablation row to paper table

### 2.2 Stress Tests
Run: `scripts/VisCache_Stress.py`
- [ ] Disocclusion: fast camera flythrough, measure frames to 80% hit rate
- [ ] Variance spike duration after disocclusion
- [ ] Peak shadow ray ratio during cold-start

### 2.3 Metrics & References
Run: `scripts/VisCache_Reference.py`
- [ ] Capture 1024 spp path tracer reference (Bistro, Sponza)
- [ ] Per-pixel MSE vs. reference for each config
- [ ] GPU timestamp breakdown: insert / lookup / decay ms
- [ ] Cache hit rate, average probe depth, miss rate stats

---

## 3. Paper Revision (detail in `paper/TODO.md`)

### 3.1 CRITICAL — Blocks Submission
- [ ] **CRITICAL** Remove "TODO: experimental validation" from abstract
- [ ] **CRITICAL** §13 Table 4: "~60% benefit at ~5% cost" — add supporting data or mark as projected
- [ ] **CRITICAL** §15 Results is entirely TODO — add at minimum one profiling data point

### 3.2 HIGH — Significant Gaps
- [ ] **HIGH** Add Bokšanský & Meister 2025 (JCGT) citation — concurrent neural visibility cache
- [ ] **HIGH** §10.1: Clarify firefly_budget units
- [ ] **HIGH** §11.1: Define M in "1/M of budget"
- [ ] **HIGH** §4: Frame as continuation of [Kugelmann 2006] experiment (2)
- [ ] **HIGH** §4: State three motivations for binary over free-path distance

### 3.3 Title & Abstract
- [ ] Add CV+RRR framing sentence to abstract
- [ ] Add "revisit" framing to abstract
- [ ] Consider alternative title: "Revisiting Visibility Prediction-with-Correction..."

### 3.4 Introduction (§1)
- [ ] Reframe contribution list — CV+RRR not claimed as new
- [ ] Remove "path sharing aligns with ReSTIR" as architectural insight
- [ ] Add "narrowing and deepening" framing
- [ ] State three actual contributions explicitly

### 3.5 Related Work (§2)
- [ ] Add [Kugelmann 2006] lineage paragraph (three experiments)
- [ ] Note hardware/framework gap between 2006 and 2026
- [ ] Add Bokšanský & Meister 2025 paragraph
- [ ] Add Liu et al. 2025 (Reservoir Splatting) — one sentence, orthogonal
- [ ] Add Zhang et al. 2024 (Area ReSTIR) — CV+RRR integrates without modification
- [ ] Verify pcg3d citation covers PCG3D specifically

### 3.6 CV+RRR Estimator (§4)
- [ ] Full unbiasedness derivation
- [ ] Generality statement (applies to any cache with mean estimate µ)
- [ ] Drop independent development claim → explicit 2006 lineage
- [ ] Make coupled variance adaptation explicit
- [ ] Cross-reference §4 coupling from §7 write-depth gate

### 3.7 Hash Structure & Addressing (§5–§8)
- [ ] Add calibration note after Table 1 (scene scale, viewing distance)
- [ ] Consider pixel-count reframing of cell sizes
- [ ] Add explicit vs. neural tradeoff paragraph
- [ ] Explain LOD asymmetry (A finer than B)
- [ ] Quantify ABA race error rate or fix with CAS
- [ ] Add DECAY_PERIOD half-life math
- [ ] Camera-adaptive cell sizing as future work (one sentence)

### 3.8 Citations (see `paper/CITATIONS.md`)
- [ ] Bokšanský & Meister 2025 — §2, §4, §11.1
- [ ] Liu et al. 2025 — §2
- [ ] Zhang et al. 2024 — §2
- [ ] Confirm Bokšanský & Meister debiasing option status

---

## 4. Running All Paper Experiments

```bash
# 1. Build Falcor with VisCache plugins
./setup-build-system.sh          # Linux
# .\setup-build-system.bat       # Windows

# 2. Download test scenes (Bistro ~3.2 GB, Sponza ~70 MB)
./scripts/download_scenes.sh

# 3. Run all experiments (smoke test → reference → baselines → ablation → stress)
./scripts/run_paper_experiments.sh

# Or run individual steps:
./scripts/run_paper_experiments.sh --skip-stress --skip-reference   # baselines + ablation only
./scripts/run_paper_experiments.sh --dry-run                       # preview commands

# 4. Trigger a release build from any commit
# GitHub → Actions → Release → Run workflow
# Version: dev-YYYYMMDD-HHMMSS-<sha8>
```

Output structure:
```
captures/
  reference/       1024 spp ground truth EXRs
  baselines/       DI/GI/PT × vanilla/local/reval/lightsel/full
  ablation/        A–E toggles, finest/coarsest-only, no-cache
  stress/          Disocclusion flythrough (full_viscache + no_cache)
  logs/            Per-experiment stdout/stderr logs
```

---

## 5. Dependencies & Blockers

**Critical path:** Port DQLin → run baseline → capture one Bistro profile → write §15.

---

## 6. SHaRC (Spatial Hash Radiance Cache) — Falcor Integration Plan

**Goal:** Add SHaRC as an optional upstream render pass (like VisCache), enabling early path
termination via cached radiance. SHaRC and VisCache are complementary — SHaRC reduces bounce
depth, VisCache reduces shadow rays per bounce. Both active simultaneously = compounded savings.

**Reference:** `refs/NVIDIA-RTX_SHARC/` (v1.6.5, NVIDIA license)

### 6.0 Architecture Comparison

| Aspect | SHaRC | VisCache |
|--------|-------|----------|
| Caches | Radiance (float3) | Binary visibility |
| Saves | Bounce depth (early path termination) | Shadow rays (RR skip) |
| Hook point | After bounce N, before next bounce | Before shadow ray dispatch |
| LOD | Camera-distance (log grid) | Variance-gated (fixed multilevel) |
| Eviction | Stale-frame count (resolve pass) | Pressure-scaled + inline decay |
| Passes | 3 separate (Update → Resolve → Query) | 2-phase inline (Gate → Commit) |
| Entry size | 40 bytes (8 hash + 16 accum + 16 resolved) | 8 bytes |
| Table default | 2^22 entries (~160 MiB) | 2^22 entries (~32 MiB) |
| Hash function | Jenkins32, linear probe bucket-16 | PCG3D, double-hash with fingerprint |
| Normal handling | 3-bit octant in hash key | None (endpoint-pair) |
| LOD selection | Camera distance → log level | Variance gate → cascade depth |
| Temporal | Stale frame counter + accumulation window | Inline overflow decay + background sweep |
| Anti-firefly | Luminance-ratio clamping on write | Contribution-weighted pMin floor |

### 6.1 Falcor Render Pass Design

Create `Source/RenderPasses/SHaRC/` as an external plugin (same pattern as VisCache):

```
Source/RenderPasses/SHaRC/
  SHaRC.cpp / .h          — RenderPass host: buffer creation, 3-pass dispatch, dict export
  SHaRC.slang             — Slang port of SharcCommon.h + HashGridCommon.h
  SHaRCTypes.slang        — Slang port of SharcTypes.h
  CMakeLists.txt          — plugin build (target_copy_shaders)
```

**Three sub-passes** within one RenderPass::execute():
1. **SHaRC Update** (RT dispatch, ~4% of pixels): sparse path trace, each hit calls
   SharcUpdateHit → accumulates radiance into accumulation buffer via InterlockedAdd
2. **SHaRC Resolve** (compute dispatch, 1 thread per entry): blends accumulation into
   resolved buffer, handles stale eviction, adjacent-level blending
3. **SHaRC Query** is NOT a separate pass — integrated into downstream renderer shaders
   (same pattern as VisCache's vhfGate/vhfCommit)

**Dict exports** (same pattern as VisCache):
```
dict["sharcHashEntries"]       RWStructuredBuffer<uint64_t>
dict["sharcAccumulation"]      RWStructuredBuffer<SharcAccumulationData>
dict["sharcResolved"]          RWStructuredBuffer<SharcPackedData>
dict["sharcParamsCB"]          cbuffer SharcGridParams
dict["sharcEnabled"]           bool
```

### 6.2 Slang Port of SHaRC Headers

SHaRC headers are HLSL. Key porting tasks:
- [ ] Port `HashGridCommon.h` → `SHaRCHashGrid.slang`
  - `uint64_t` → Slang `uint64_t` (native support)
  - `InterlockedCompareExchange` on uint64 → Slang interlocked ops (SM 6.6)
  - `RWStructuredBuffer` macros → direct Slang buffer declarations
  - Jenkins32 hash, log-grid level computation, spatial hash key encoding
- [ ] Port `SharcCommon.h` → `SHaRC.slang`
  - SharcUpdateHit/Miss, SharcGetCachedRadiance, SharcResolveEntry
  - Anti-firefly filter, BLEND_ADJACENT_LEVELS, fade acceleration
  - PROPAGATION_DEPTH backpropagation state
- [ ] Port `SharcTypes.h` → `SHaRCTypes.slang`
  - SharcAccumulationData, SharcPackedData (fp16x4 + uint packing)

Alternative: `__target_intrinsic` shim to include HLSL directly — fragile, prefer clean port.

### 6.3 Downstream Renderer Integration

Same pattern as VisCache — dict read, defines, binding:

**Compile-time defines:**
| Define | Purpose |
|--------|---------|
| `USE_SHARC` | Hash table + resolved buffer available |
| `USE_SHARC_QUERY` | Early path termination on bounce N≥2 |

**Shader integration point** (in path tracer bounce loop):
```slang
import RenderPasses.SHaRC.SHaRC;

// After bounce N (N >= 1, never primary hit):
#if USE_SHARC_QUERY
    float3 cachedRadiance;
    if (SharcGetCachedRadiance(sharcParams, hitData, cachedRadiance, false))
    {
        // Early terminate: use cached radiance instead of continuing path
        Lo += throughput * cachedRadiance;
        break;
    }
#endif
```

**Per-renderer scope:**
| Renderer | SHaRC integration point | Notes |
|----------|------------------------|-------|
| MinimalPathTracer | After first bounce | Simple loop, easy hook |
| PathTracer | Inside multi-bounce loop | Standard integration |
| ReSTIR PT | After reconnection vertex | Must not cache at reconnection point itself |
| RTXDI | Not applicable | Single-bounce DI, no path to terminate |

### 6.4 SHaRC Update Pass — Sparse Tracing

The Update pass needs its own RT dispatch (separate from main render):
- Select ~4% of pixels (random 1-in-25 per 5×5 block, different each frame)
- Run full path tracer with SHaRC instrumentation:
  - Reset throughput to 1.0 at each bounce (independent segments)
  - Call SharcInit at path start
  - Call SharcUpdateHit at each hit (returns false → terminate early via resampling)
  - Call SharcSetThroughput after BSDF sampling
  - Call SharcUpdateMiss on miss (env map)

**Options for Update pass implementation:**
1. **Dedicated RT shader** — cleanest, duplicates some path tracing logic
2. **Reuse existing path tracer with SHARC_UPDATE define** — less duplication, more coupling
3. **Compute shader with inline ray tracing** — avoids RT pipeline overhead for sparse work

Option 1 is recommended for initial implementation. Can share BSDF/material evaluation
modules with existing path tracers.

### 6.5 SHaRC + VisCache Coexistence

**Graph topology** (both active):
```
VisCache pass → SHaRC pass → Renderer pass
     |              |              |
     |              |              +-- reads VisCache dict (shadow rays)
     |              |              +-- reads SHaRC dict (early termination)
     |              |
     |              +-- SHaRC Update sub-pass may also use VisCache
     |                  for shadow rays during sparse tracing (optional,
     |                  reduces Update cost too)
     |
     +-- independent, no dependency on SHaRC
```

**Key interaction:** SHaRC's Update pass traces shadow rays → can use VisCache to accelerate
those too. This means the SHaRC Update shader should also import VisCache modules and bind
VisCache resources. Compounded savings: fewer shadow rays in the Update pass AND fewer
bounces in the main render.

### 6.6 Tuning & Scene-Specific Parameters

SHaRC parameters that need scene-scale calibration:
| Parameter | SHaRC default | Notes |
|-----------|--------------|-------|
| `sceneScale` | scene-dependent | Controls voxel size; analogous to VisCache cellSize |
| `logarithmBase` | 2.0 | LOD ratio between levels |
| `levelBias` | 0 | Clamp finest level near camera |
| `accumulationFrameNum` | 1–1024 | Temporal window; higher = better quality, slower response |
| `staleFrameNumMax` | 8–1024 | Eviction aggressiveness |
| `radianceScale` | 1e3 | Quantization for u32 atomic accumulation; scene-dependent |

### 6.7 Ablation Matrix (SHaRC-specific)

| Config | Description |
|--------|-------------|
| SHaRC only | Early termination, no VisCache |
| VisCache only | Shadow ray skip, no SHaRC |
| SHaRC + VisCache | Both active (compounded) |
| SHaRC − adjacent blend | Disable BLEND_ADJACENT_LEVELS |
| SHaRC − resampling | Disable cache resampling during Update |
| SHaRC − anti-firefly | Disable luminance-ratio clamping |
| SHaRC sparse rate | Vary 1%, 4%, 10% update pixel fraction |

### 6.8 Implementation Order

- [ ] Phase 1: Slang port of SHaRC headers (pure shader, no host code)
  - Port HashGridCommon.h, SharcCommon.h, SharcTypes.h to Slang
  - Unit test: compile-only validation
- [ ] Phase 2: SHaRC RenderPass host (buffer creation, Resolve compute dispatch)
  - Create SHaRC.cpp/h following VisCache pattern
  - Implement Resolve pass (compute shader, easiest sub-pass)
  - Dict export of buffers
- [ ] Phase 3: SHaRC Update pass (sparse RT dispatch)
  - Implement sparse pixel selection
  - RT shader with SharcInit/UpdateHit/UpdateMiss/SetThroughput
  - Use MinimalPathTracer as template (simplest bounce loop)
- [ ] Phase 4: Query integration into MinimalPathTracer
  - Add SharcGetCachedRadiance call after first bounce
  - Verify early termination reduces average bounce depth
  - Compare image quality vs reference
- [ ] Phase 5: Query integration into PathTracer + ReSTIR PT
  - PathTracer: standard multi-bounce hook
  - ReSTIR PT: careful placement (not at reconnection vertex)
- [ ] Phase 6: SHaRC + VisCache coexistence
  - SHaRC Update pass reads VisCache dict for shadow rays
  - Graph scripts with both passes
  - Compounded savings measurement
- [ ] Phase 7: Ablation captures
  - SHaRC-only vs VisCache-only vs both
  - Parameter sensitivity (sparse rate, stale frames, scene scale)

### 6.9 Open Questions

- [ ] SHaRC's camera-distance LOD vs VisCache's variance-gated LOD — could SHaRC benefit
  from variance gating too? (radiance variance is not free like Bernoulli variance, would
  need explicit variance tracking or proxy)
- [ ] SHaRC uses separate accumulation + resolved buffers (40B/entry). Could a single-buffer
  design work (like VisCache's 8B entries) using inline resolve? Radiance needs more bits
  than binary visibility, so probably not without precision loss.
- [ ] SHaRC's PROPAGATION_DEPTH backpropagation stores up to 4 vertices — register pressure
  concern on some architectures. Profile on RTX 3090 vs 4090.
- [ ] License: SHaRC is NVIDIA proprietary license. Clean Slang reimplementation from
  published algorithm description (GDC 2024 talk + integration guide) preferred over
  line-by-line port of copyrighted headers. Reference code is for understanding, not copying.

# SUPERSEDED — historical context only

This plan is **outdated and rejected**. The "copy DQLin shaders verbatim into `Falcor/.../PathTracer/restirpt/` and add §9.3 cache-gated revalidation" approach it locks in is not what we're building. The 2026-05-04 staged byte-copy at `Falcor/Source/RenderPasses/PathTracer/restirpt/` (referenced by Decisions #5 and #6 below) has been deleted.

**Replacement:** `~/.claude/plans/plan-a-restirpt-2d-synchronous-horizon.md` — clean port of `Source/RenderPasses/ReSTIRPTPass/` (DQLin reference) into `Falcor/Source/RenderPasses/PathTracer/`, parity-only, no experimental algorithmic content. v1 ships `restirpt_2d` (per-pixel addressing equivalent to current ReSTIRPTPass); `restirpt_3d` (world-cell addressing) is a vNext additive change behind a mode flag.

The Risk #1–#8 mitigations and Ladder19 validation skeleton below remain useful as a checklist of failure modes to watch for in the new port; do not execute the file as-is.

---

# Plan: ReSTIR PT integration into PathTracer (WS-PT v1)

## Context

**What:** Add path-space reservoir reuse to Falcor's `PathTracer` pass, riding the same VisCache posA cascade addressing already used by WS-ReSTIR DI. Reservoirs are **cell-keyed** (world-space hash), not pixel-keyed.

**Why:** Paper §9.3 frames this as the cache's highest-value application — unbiased revalidation of V(P, Q) for spatial-reuse reconnection vertices Q drops shadow rays from ~5/pixel to ~0.7/pixel via prediction-with-correction. *No screen-space alternative exists for arbitrary reconnection vertices* — temporal reprojection and neighbour polling cannot help when Q is a world-space point unrelated to the current pixel's view (§9.3).

**Reference (read-only):** `Source/RenderPasses/ReSTIRPTPass/` (DQLin port to Falcor 8) and `Falcor/Source/RenderPasses/RTXDIPass/` are **fully separate, byte-untouched** reference implementations. **WS-PT does NOT import from them, does NOT add fields to their cbuffers, does NOT share shader files with them.** Algorithmic logic (struct layouts, GRIS math, shift kernels) is **copied** into PathTracer/, not imported.

**Already shipped foundation (commits `0846663..f2993a0`):** WS-ReSTIR DI in `PathTracer.slang:1188-1310` — per-cell light reservoir buffer (`mpVHFWSReservoirs`, ~32B/slot, single slot, fingerprint-tagged, last-writer-wins) keyed by `wsResolveCell(posW, faceN)` at `wsLevelOffset` coarser than visibility. WS-PT mirrors this pattern for full path reservoirs.

## Locked decisions

1. **Cell-keyed, single-slot, fingerprint-tagged, last-writer-wins** — same pattern as WS-DI. PathReservoir is heavier (~96B vs 32B) so default `pwsLevelOffset = wsLevelOffset + 1` (one cascade coarser than DI) to reduce contention ~8×.
2. **Cache-gated revalidation in MVP** (paper §9.3) — unbiased correction at the donor reconnection vertex. The whole reason WS-PT differs from a pixel-keyed port.
3. **Spatial-only in v1** — no temporal ping-pong buffer. The cell IS the temporal smoothing structure once we read+merge+write each frame with M-cap. Re-evaluate after metrics.
4. **Both shift modes via runtime cbuffer flag** (`pwsShiftMode`: 0=Reconnection, 1=Hybrid). Reconnection-only is the v1 default and validation focus; hybrid is in the code path for free since shift logic is copied wholesale.
5. **Shift kernel: copy ReSTIRPTPass/Shift.slang into PathTracer/PathShift.slang and adapt.** Replaces per-pixel lookups (`params.getReservoirOffset(dstPixel)`, `prevVBuffer[dstPixel]`) with explicit `ReconnectionData` arguments built on-stack at gather time. **No `import` of the original** — the file becomes pristine PathTracer property.
6. **PathReservoir struct: copy + adapt, do not import.** New `Falcor/Source/RenderPasses/PathTracer/PathReservoir.slang` defines its own `PathReservoir` and `WSPathReservoir { uint fingerprint; PathReservoir r; }`. GRIS merge math (`mergeWithResamplingMIS`, `finalizeGRIS`) copied from ReSTIRPTPass reference, then owned outright.
7. **Separate cbuffer: `WSPathReservoirParams`.** Bound ONLY by PathTracer.cpp. Do NOT add fields to `VisCacheParams` — that cbuffer is also consumed by ReSTIRPTPass and RTXDI, and CLAUDE.md mandates per-field enumeration at every binding site, which would force edits to those passes. A separate cbuffer keeps them byte-untouched.
8. **Static scenes only for v1** — same lightIndex / instanceID stability assumption as WS-DI. Hard-rejected at host-side gate (see Risk mitigations below).
9. **Slang permutation budget**: single new compile-time define `USE_PWS_RESERVOIRS` gating buffer declarations + read/write blocks. All other knobs (shift mode, neighbour count, RR target) are runtime cbuffer fields. Net new permutations: ×2.
10. **ReSTIRPTPass + RTXDIPass stay byte-identical.** No edits to their .cpp, .h, or .slang files for any reason. They're reference baselines for A/B comparisons in the validation matrix only.

## Files added

| Path | Purpose | Approx LoC |
|---|---|---|
| `Falcor/Source/RenderPasses/PathTracer/PathReservoir.slang` | Self-contained: defines `PathReservoir` (88B), `WSPathReservoir { uint fingerprint; PathReservoir r; }`, `pwsResolveCell` (delegates to existing `wsResolveCell` with `pwsLevelOffset`), `init`, `isEmpty`, `mergeWithResamplingMIS`, `finalizeGRIS`. Logic copied from `Source/RenderPasses/ReSTIRPTPass/PathReservoir.slang:224-452` reference, then owned outright (no import). | ~450 |
| `Falcor/Source/RenderPasses/PathTracer/PathReservoirIO.slang` | `wsLoadPathCell`, `wsStorePathCellCAS`, `wsMergePathIntoCell`, `wsResolveJitteredCellPT`. Mirrors pattern from existing `WSReservoirIO.slang:184-205, 288-307`. Bound buffer: `gWSPathReservoirs`. Includes per-cell collision counter (atomic uint, see Risk #3). | ~180 |
| `Falcor/Source/RenderPasses/PathTracer/PathShift.slang` | **Copy** of `Source/RenderPasses/ReSTIRPTPass/Shift.slang` (~600 LoC) with adaptations: (a) per-pixel buffer accesses (`params.getReservoirOffset(dstPixel)`, `prevVBuffer[dstPixel]`) replaced by `ReconnectionData` argument passed by value; (b) `prevSd` reconstructed from `donor.r.rcPrevHit` via `LoadShadingData` rather than from prev V-buffer; (c) `acceptUpper`/`acceptLower` lobe gating mirrored from `PathTracer.slang:1262-1267` at every shift entry (Risk #6). Both `shiftPathReconnection` and `shiftPathHybrid` exposed via thin wrapper `wsShiftToHere(donor, sd, shiftMode, out J, out shiftedF)`. | ~650 |
| `Falcor/Source/RenderPasses/PathTracer/PathTracerParams.slang` (extension) or new `WSPathReservoirParams.slang` | Defines `cbuffer WSPathReservoirParams` separate from `VisCacheParams`. Holds the 8 `gPWS*` fields. | ~30 |

## Files modified

### `Falcor/Source/RenderPasses/PathTracer/PathTracer.slang`

- **Line ~58** (after VisCache imports): `import PathReservoir; import PathReservoirIO; import PathShift;` gated by `#if USE_PWS_RESERVOIRS`.
- **Read+merge+revalidate site at vertex 1** (~line 1310, immediately after the existing WS-DI block). New ~180 LoC. Pseudocode:
  ```
  if (USE_PWS_RESERVOIRS && path.getVertexIndex() == 1 && gPWSEnable) {
      WSPathReservoir local; local.r.init();

      // Gather home + N neighbours
      WSCellAddr home = pwsResolveCell(sd.posW, sd.faceN);
      for (uint i = 0; i <= gPWSSpatialNeighbours; ++i) {
          WSCellAddr addr = (i == 0) ? home
              : wsResolveJitteredCellPT(sd.posW, sd.faceN, i-1, sampleNext2D(sg));
          if (i > 0 && addr.fingerprint == home.fingerprint) continue;

          WSPathReservoir donor;
          if (!wsLoadPathCell(addr, donor) || donor.r.M <= 0.f) continue;

          // Hemisphere lobe gate (Risk #6) — mirror DI's acceptUpper/acceptLower
          if (!pwsAcceptDonorHemisphere(donor.r.rcVertexHit, sd)) continue;

          // Shift donor → P
          float J; float3 shiftedF;
          if (!wsShiftToHere(donor, sd, gPWSShiftMode, J, shiftedF)) continue;

          // §9.3 cache-gated unbiased revalidation
          float predictedV = pwsCachedVisibility(sd.posW, donor.r.rcVertexHit);  // vhfLookup
          float mass = luminance(shiftedF) * predictedV;
          float keepProb = saturate(mass / gPWSRRTargetMass);
          float V_correction = 0.f;
          if (sampleNext1D(sg) < keepProb) {
              float V = traceVisibility(sd.posW, donor.r.rcVertexHit) ? 1.f : 0.f;
              V_correction = (V - predictedV) / keepProb;        // unbiased term
          }
          // CRITICAL: this is the unbiased estimator (Risk #5)
          float3 contribution = (predictedV + V_correction) * shiftedF;

          // GRIS merge with pairwise MIS
          local.r.mergeWithResamplingMIS(contribution, J, donor.r, sg, pairwiseMIS(...));
      }

      // Write back fresh sample → home
      local.r.M = min(local.r.M + 1.f, gPWSMCap);
      wsStorePathCellCAS(home, local);  // increments gPWSCollisionCounter on fingerprint mismatch

      local.r.finalizeGRIS();
      addToPathContribution(path, local.r.weight * local.r.F);
  }
  ```
  The unbiased estimator is `predictedV·shifted + 1[RR fires]·((V − predictedV)/keepProb)·shifted` — the cache-only term is the prediction; the RR-gated term is the correction. Naive `keepProb`-as-importance is biased.
- **Write site** at path completion (after `addToPathContribution` for the BSDF-sampled scatter contribution, ~line 1366 region): construct fresh `PathReservoir` from path's reconnection vertex (v2), CAS-store to home cell. ~30 LoC.

### `Falcor/Source/RenderPasses/PathTracer/PathTracer.cpp`

**New cbuffer `WSPathReservoirParams` (separate from VisCacheParams)** — 8 fields:
```cpp
struct WSPathReservoirParams {
    uint32_t pwsEnable;            // 0/1
    uint32_t pwsLevelOffset;       // default = wsLevelOffset + 1
    uint32_t pwsCapacity;          // # cells (= wsCapacity is fine)
    uint32_t pwsSpatialNeighbours; // 0..4, default 4
    uint32_t pwsShiftMode;         // 0=Reconnection, 1=Hybrid
    float    pwsMCap;              // M-cap; default 30
    float    pwsRRTargetMass;      // RR fire threshold; default 0.01
    float    pwsLightSoftness;     // cache-trust [0..1]
};
```

**Per CLAUDE.md, every field must be enumerated at every binding site** — but **only inside PathTracer**. The 4 PathTracer-internal sites:
1. `PathTracer.cpp:1268-1289` — read from `InternalDictionary` (parallel block to WS-DI fields at 1281-1289).
2. `PathTracer.cpp:1503-1556` — bind to `var["WSPathReservoirParams"]["gPWS*"]` at TracePass binding (parallel block to WS-DI bind at 1543-1550).
3. `PathTracer.cpp` `getDefines()` (~line 1677, next to `USE_WS_RESERVOIRS`): add `USE_PWS_RESERVOIRS`.
4. `Falcor/Source/RenderPasses/PathTracer/ReflectTypes.cs.slang` — declare `WSPathReservoir` for layout reflection.

**ReSTIRPTPass.cpp and RTXDIPass.cpp are NOT touched** (Decision #10). They consume `VisCacheParams`, not `WSPathReservoirParams`, so the new fields are invisible to them.

**New buffer + members in `PathTracer.h`** (after `mpVHFWSReservoirs`, ~line 249):
```cpp
ref<Buffer> mpVHFPWSReservoirs;            // per-cell PathReservoir
ref<Buffer> mpVHFPWSCollisionCounter;      // per-cell atomic uint, Risk #3
WSPathReservoirParams mPWSParams;          // host-side cbuffer mirror
bool mVisCacheWSPathReservoirs = false;    // gate from InternalDictionary
bool mWSPathDynamicSceneDetected = false;  // Risk #4: lightIndex stability
```

**Allocation in `prepareResources()`** near line 1292: if `pwsCapacity > 0`, create `StructuredBuffer<WSPathReservoir>` of size `pwsCapacity`, stride from reflected type. Mirror DI's pattern.

**Dynamic-scene detection guard (Risk #4)**: in `setScene()`, after scene bind, set `mWSPathDynamicSceneDetected = scene->hasAnimation() || scene->hasSkinnedMeshes()`. In `execute()`, if `gPWSEnable && mWSPathDynamicSceneDetected`, log a hard error to Mogwai console and force-clear `mPWSParams.pwsEnable = 0` for the frame. v1 explicitly refuses to run on dynamic content.

**setShaderData patch** at TracePass binding (PathTracer.cpp:1553, immediately under `var["gWSReservoirs"] = mpVHFWSReservoirs`):
```cpp
if (mVisCacheWSPathReservoirs) {
    var["gWSPathReservoirs"] = mpVHFPWSReservoirs;
    var["gPWSCollisionCounter"] = mpVHFPWSCollisionCounter;
}
```

### `Falcor/Source/RenderPasses/PathTracer/StaticParams.slang`
Add single define: `USE_PWS_RESERVOIRS` (0/1). Everything else runtime.

## Critical files

- `C:\Projects\VisCacheSketch\Falcor\Source\RenderPasses\PathTracer\PathTracer.slang` — WS-PT block lands at ~line 1310 immediately after WS-DI block (1188-1310)
- `C:\Projects\VisCacheSketch\Falcor\Source\RenderPasses\PathTracer\PathTracer.cpp` — cbuffer field plumbing at 1268-1289 / 1503-1556 / getDefines ~1677
- `C:\Projects\VisCacheSketch\Falcor\Source\RenderPasses\PathTracer\PathTracer.h` — new buffer member + dict-gate flag + dynamic-scene flag
- `C:\Projects\VisCacheSketch\Source\RenderPasses\VisCache\WSReservoirIO.slang` — template for PathReservoirIO.slang (CAS at lines 184-205, jittered cell at 288-307); read-only template, copy patterns into the new PathTracer-side file

**Read-only references (DO NOT EDIT):**
- `C:\Projects\VisCacheSketch\Source\RenderPasses\ReSTIRPTPass\Shift.slang` — algorithmic source for copy → `PathShift.slang`
- `C:\Projects\VisCacheSketch\Source\RenderPasses\ReSTIRPTPass\PathReservoir.slang` — algorithmic source for copy → `PathTracer/PathReservoir.slang`
- `C:\Projects\VisCacheSketch\Source\RenderPasses\ReSTIRPTPass\ReSTIRPTPass.cpp` — read for reference only
- `C:\Projects\VisCacheSketch\Falcor\Source\RenderPasses\RTXDIPass\*` — read for reference only

## Reused infrastructure (already in repo, just call from PathTracer.slang)

- `wsResolveCell(posW, faceN)` and `wsResolveJitteredCell` — already in `WSReservoirIO.slang`. PathReservoir variant just passes `pwsLevelOffset` instead of `wsLevelOffset`.
- `vhfLookup(P, Q)` — VisCache visibility lookup; the §9.3 prediction.
- DI's contribution-weighted RR mechanism (paper §10) — same pattern at the revalidation site, no shared code needed.

## Risk mitigations folded into v1 plan

Each risk below has a **concrete v1 deliverable** that resolves or bounds it. Nothing is left as advisory.

### Risk #1: Cbuffer per-field enumeration burden (CLAUDE.md rule)
**Mitigation:** Separate cbuffer `WSPathReservoirParams` bound only by PathTracer (Decision #7). ReSTIRPTPass and RTXDI never see the new fields, so per-field enumeration is contained to 4 PathTracer-internal sites. No cross-pass mirroring needed.
**Deliverable:** `WSPathReservoirParams.slang` declared in PathTracer/, bound at exactly 1 site (TracePass binding). Comment block at the binding site labelled "WS-PT fields — keep aligned with WSPathReservoirParams.slang struct order".

### Risk #2: Slang permutation budget (~60/process)
**Mitigation:** Only `USE_PWS_RESERVOIRS` is compile-time. Shift mode (`pwsShiftMode`), neighbour count (`pwsSpatialNeighbours`), RR target (`pwsRRTargetMass`) are runtime cbuffer fields with branchy execution.
**Deliverable:** Permutation count audit at end of build: log `slang.compile.permutations` count to `runtime/Mogwai.exe.*.log`. Target: net new permutations ≤ 2× the WS-DI delta (i.e., ≤ 2 new permutations).

### Risk #3: Single-slot contention on 96B reservoirs
**Mitigation:** Default `pwsLevelOffset = wsLevelOffset + 1` reduces contention ~8×. **Cell-collision counter** is part of v1 (not deferred): atomic uint per-cell incremented on fingerprint mismatch in `wsStorePathCellCAS`. Reported in PixelStats overlay.
**Deliverable:** `mpVHFPWSCollisionCounter` buffer, bound as `gPWSCollisionCounter`, incremented in `PathReservoirIO.slang:wsStorePathCellCAS`. Ladder validation includes a `pwsCollisionRate` column in CSV. **Acceptance gate:** collision rate <10% on Bistro at 16 spp; if higher, fall back to atomic-min on donor pHat luminance before swap (still in v1).

### Risk #4: lightIndex / instanceID stability — static scenes only
**Mitigation:** Host-side hard reject. `setScene()` sets `mWSPathDynamicSceneDetected = scene->hasAnimation() || scene->hasSkinnedMeshes()`. `execute()` force-clears `pwsEnable = 0` for the frame and logs a Mogwai error if dynamic detected.
**Deliverable:** Code path in `PathTracer.cpp::setScene()` and `execute()`. Unit-equivalent check: smoke-test against `VeachAjar` (static, expect WS-PT enabled) and an animated test scene (expect WS-PT force-disabled with log line).

### Risk #5: Unbiased revalidation math footgun
**Mitigation:** The form is `predictedV·shifted + 1[RR fires]·((V − predictedV)/keepProb)·shifted` — NOT `1[RR fires]·(V/keepProb)·shifted + (1−1[RR fires])·predictedV·shifted`. The first is unbiased; the second is biased.
**Deliverable:** **Bias check is a v1 acceptance gate, not a stretch goal.** At 256 spp `recon-N4` on `BistroInterior` and `Sponza`, relative bias vs offline reference (4096-spp vanilla PathTracer) must be ≤1%. If >1%, the unbiased correction is mis-coded — fix before any other validation.

### Risk #6: Reconnection vertex hemisphere check
**Mitigation:** Mirror DI's `acceptUpper`/`acceptLower` lobe gating at every shift entry. Implement as `pwsAcceptDonorHemisphere(donor.r.rcVertexHit, sd)` helper called BEFORE `wsShiftToHere`.
**Deliverable:** Helper in `PathReservoir.slang`; call site in `PathTracer.slang` shown in pseudocode above. Verified by inspection of plate output on grazing-angle pixels (Sponza floor near walls): no fireflies attributable to wrong-hemisphere donors.

### Risk #7: `pwsLevelOffset` × `wsLevelOffset` interaction
**Mitigation:** Joint sweep folded into v1 validation matrix, not deferred. Best variant of `(pwsLevelOffset, wsLevelOffset) ∈ {(W, W), (W+1, W), (W+1, W+1)}` reported alongside the recon-N4 winner.
**Deliverable:** Extra rows in `VisCache_Ladder19.py` matrix (see Validation below).

### Risk #8: ReSTIRPTPass + RTXDIPass kept byte-untouched
**Mitigation:** Decision #10 + separate cbuffer (Decision #7) + no shader imports (Decisions #5, #6). Algorithmic logic copied, not imported.
**Deliverable:** Pre-PR audit step: `git diff --stat HEAD origin/main -- 'Source/RenderPasses/ReSTIRPTPass/**' 'Falcor/Source/RenderPasses/RTXDIPass/**'` must report **0 files changed**. CI gate (optional) can enforce this.

## Verification

### Build & smoke
```
build.bat --skip-setup
.scripts/smoke.sh                            # 1 frame VeachAjar
```

### Per-scene headless check
```
.scripts/mogwai-headless.sh '*PathTracer_Graph.py' BistroInterior 32
```
Expected: clean exit, no shader recompile loop, WS-PT block executes when `pwsEnable=1` set in graph script.

### Pre-flight: Risk #8 audit
```
git diff --stat HEAD origin/main -- 'Source/RenderPasses/ReSTIRPTPass/**' 'Falcor/Source/RenderPasses/RTXDIPass/**'
# expected: empty output (0 files changed)
```

### Ladder validation — new step `VisCache_Ladder19.py`

Variants (8 cells × MULTI_LEVEL_SCENES from `VisCache_LadderCommon.py`):

| Variant | pwsEnable | pwsShiftMode | pwsSpatialNeighbours | Reval | pwsLevelOffset |
|---|---|---|---|---|---|
| `off` (control = WS-DI alone) | 0 | — | 0 | — | — |
| `recon-N0` (cell-only) | 1 | 0 | 0 | on | wsLO+1 |
| `recon-N4` | 1 | 0 | 4 | on | wsLO+1 |
| `recon-N4-noreval` (Risk #2 ablation) | 1 | 0 | 4 | off | wsLO+1 |
| `recon-N4-LO=W` (Risk #7 sweep) | 1 | 0 | 4 | on | wsLO |
| `recon-N4-LO=W+1` (= `recon-N4`) | already covered | | | | |
| `hybrid-N4` | 1 | 1 | 4 | on | wsLO+1 |
| `recon-N4-bias-check` | 1 | 0 | 4 | on | wsLO+1 (256 spp, Risk #5) |

Scenes: `BistroInterior`, `BistroExterior`, `Sponza`, `32PointLights`. SPP: 4, 16 (and 256 for the bias-check row only). Reference: vanilla PathTracer at 4096 spp + cross-compare against ReSTIRPTPass at matched SPP (read-only baseline).

Run:
```
runtime/pythondist/python.exe scripts/run_ladder.py -s 19
```

### Acceptance gates (must all pass before merging)

1. **Risk #8 audit:** 0 files changed in ReSTIRPTPass + RTXDIPass.
2. **Risk #5 bias check:** `recon-N4-bias-check` relative bias ≤ 1% vs 4096-spp reference on Bistro and Sponza.
3. **Risk #3 collision rate:** ≤ 10% on Bistro at 16 spp `recon-N4`.
4. **Risk #2 permutation count:** ≤ 2 new shader permutations vs pre-WS-PT baseline.
5. **Quality:** `recon-N4` indirect-only relMSE drops ≥ 30% vs `off` on Bistro at 16 spp.
6. **§9.3 win:** `recon-N4` shadow-ray count drops ≥ 4× vs `recon-N4-noreval` (target: 5→0.7), relMSE within 2% of unrevalidated.

If any gate fails, stop and address before continuing the validation matrix.

## Out-of-scope for v1 (deferred)

- Temporal ping-pong reservoir buffer (revisit if static-camera convergence still slow after spatial alone).
- Pairwise vs Talbot MIS comparison.
- BPR (`PathSamplingMode::PathReuse`).
- Multi-slot per cell (k=2..4 with hash chaining) — only triggered if Risk #3 acceptance gate fails.
- Dynamic-scene support (motion-compensated cell fingerprints, prev-frame TLAS).
- ReSTIRPTPass *itself* gaining cache-gated revalidation (separate effort once WS-PT validates the §9.3 trick; ReSTIRPTPass remains untouched in this plan).

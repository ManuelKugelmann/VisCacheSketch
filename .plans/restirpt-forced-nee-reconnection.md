# Phase 1 — Forced NEE Light Reconnection (Lin 2026 §6.2.3)

## What this wins

**Structural unblock for Phase 3 (Stage A unification).** The Stage A probe (2026-05-06, `restirpt_unified_b{N}` variant) regressed Cornell mean_err to 20.4% vs canonical 3.87% (5× worse) across all bounce counts. Diagnosis: d=2 NEE-terminating paths have `rcVertexLength = kMaximumPathLength` (no rcVertex marked) → shift falls through with invalid `rcVertexHit` → returns 0 → integrand collapse → resampler bias. §6.2.3 forces the NEE light vertex itself to be the rcVertex when no earlier rcVertex was selected, giving the shift a valid reconnection target with stored light identity.

Paper framing: §6.2.3 is described as a *performance* optimization with "any potential variance increase mitigated by path MIS weights." For us it's promoted to a *correctness prerequisite* for Stage A — without it, Phase 3 cannot reach reasonable metrics.

## Math

NEE-terminating path: `x̄ = [x_0, x_1, ..., x_{k-1}, x_k_light]` where `x_k_light` is the sampled light vertex. For d=2: `pathLength = 1`, `x̄ = [x_0_camera, x_1_primary, x_2_light]`.

**Current (broken at d=2):**
- `rcVertexLength = kMaximumPathLength` (sentinel: no rcVertex)
- Shift code at `Shift.slang:419` reads `rcVertexLength = 15` → no valid reconnection target
- `Shift.slang:432-461` only handles EnvMap fallback; Emissive/Analytic d=2 NEE return 0
- Random replay then re-samples light independently at destination pixel; different light → integrand mismatch → bias

**Fix (§6.2.3):**
- When `addNeeVertex` is called and `rcVertexLength == kMaximumPathLength`, force-mark the NEE light vertex as rcVertex: set `rcVertexLength = pathLength` (= 1 for d=2)
- Populate `rcVertexHit` (Emissive triangle hit), `rcVertexWi[0]` (direction from x_{k-1} to light), `lightPdf`, `lightType`, and (new) `rcLightIndex` for Analytic lights
- During shift: reconnection from y_{k-1} (destination's last bounce vertex) to x_k_light succeeds using stored light identity → same light evaluated at destination → integrand matches source's PDF accounting

The stored direction `rcVertexWi[0]` is the direction from `x_{k-1}` to the light (not a frame on the light surface) — already DQLin's convention per `PathBuilder.slang:171`.

## Reference impl status

**Neither DQLin nor NVlabs implements §6.2.3.** Audit (Explore agent, 2026-05-06):
- `refs/DQLin_ReSTIR_PT/Source/RenderPasses/ReSTIRPTPass/PathBuilder.slang` — addNeeVertex marks rcVertex only when `is_rcVertex` (= `pathLength == rcVertexLength`); never force-marks
- `refs/NVlabs_conditional_ReSTIR/.../PathTracer.slang` — same pattern; no forced-NEE logic

This port would be the first to implement Lin 2026 §6.2.3. Math derived from paper text + DQLin reservoir storage conventions.

## Critical files

| File | Change |
|---|---|
| `Source/RenderPasses/ReSTIRPTPass/PathBuilder.slang::addNeeVertex` (line ~118) | New branch: when `pathReservoir.pathFlags.rcVertexLength() == kMaximumPathLength` AND `pathLength >= 1`, force-mark NEE light as rcVertex. Populate `pathFlags.insertRcVertexLength(pathLength)`, `rcVertexHit`, `rcVertexWi[0]`, `lightPdf`, `lightType`, `rcLightIndex` (new field). |
| `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang::nextVertex` (line ~1383) | Pass `ls.hit` (NEE light surface hit) into `addNeeVertex` — current signature drops it. Plumb the hit info through `LightSample` if not already there. |
| `Source/RenderPasses/ReSTIRPTPass/PathReservoir.slang` (line ~228) | Add `uint rcLightIndex` field for Analytic light identity (8B for alignment, struct grows 100B → 108/112B in non-BPR). Or pack into available `pathFlags` bits (8-15 unused per audit). |
| `Source/RenderPasses/ReSTIRPTPass/Shift.slang::computeShiftedIntegrandReconnection` (line ~432-461) | Extend non-rcVertexHit fallback to handle "lastVertexNEE && lightType == Analytic" case (look up by rcLightIndex, evaluate analytic light pdf at destination). EnvMap case already partially handled at line 437; verify it covers the d=2 NEE EnvMap path. |
| `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp` (line ~1175) | Bump `baseReservoirSize` if struct grows (depends on whether rcLightIndex packs into pathFlags or gets a new field). |

## Sub-phased rollout

**1.A — Audit + math (no code).** Confirm Explore agent's findings against actual code. Specifically: (a) what does `LightSample` currently carry — is `ls.hit` populated for emissive triangles? (b) does `Shift.slang::computeShiftedIntegrandReconnection` already handle the Emissive case correctly when given a valid `rcVertexHit` for an NEE light? (c) does `pathFlags` have 8+ bits free for `rcLightIndex` or do we need a new struct field?

**1.B.1 — Emissive-only forced NEE.** Smallest viable change. Plumb `ls.hit` into `addNeeVertex`. Force-mark Emissive NEE-light as rcVertex when no prior rcVertex. Skip EnvMap + Analytic (they fall through to existing behavior — the latter regressing). Run Cornell + Sponza step 00 to verify Emissive d=2 fix lands. Cornell single area light + Sponza emissive panels are pure-emissive scenes, so this should cover the bulk of the d=2 problem on our test set.

**1.B.2 — EnvMap forced NEE.** Verify existing `Shift.slang:437` EnvMap escape path handles d=2 NEE correctly (audit suggests it might not — `lastVertexNEE() == true` blocks the existing branch). If not, add direction-based reconnection using `rcVertexWi[0]`. Test on a scene with env map (Bistro has, Cornell does not).

**1.B.3 — Analytic forced NEE.** Requires `rcLightIndex` field (struct or pathFlags). Defer until Cornell_3PL or similar analytic-light scene shows regression in 1.B.1/1.B.2.

**1.C — Stage A retest.** Re-run `restirpt_unified_b{N}` variant on Cornell + Sponza. Expected: Cornell mean_err drops from 20.4% → close to canonical 3.87%; Sponza similarly recovers.

## Verification

In execution order, cheapest catch first:

1. **Smoke test** after each sub-phase — 0 Inf, 0 NaN, no crashes.
2. **Bit-identical canonical**: `restirpt_b{N}` (RTXDI feed mode, Phase 1 changes shouldn't affect it since rcVertex selection happens before NEE in the canonical config) must remain bit-exact to pre-Phase-1 baseline. If it changes, the gate is too aggressive.
3. **Step 00 Cornell + Sponza ladder**: full metric battery. Pass criteria:
   - `restirpt_b{N}` (canonical, RTXDI feed): unchanged (preserves §6.3 win, no regression)
   - `restirpt_unified_b{N}` (Stage A, the unblock target): mean_err within 5% of canonical, art5 within 10%, RMSE/PSNR comparable
   - `restirpt_bpr_b{N}`: unchanged (BPR has its own rcVertex selection logic)
4. **Multi-light scene check**: Cornell_32PL or Cornell_3AreaLights to stress the analytic path (1.B.3) once implemented.
5. **Variance overshoot check**: per the paper, MIS weights mitigate variance increase but don't eliminate it. If chroma_var or per-channel variance regresses materially, investigate.

## Risks

- **`addNeeVertex` signature change**: adding `HitInfo` parameter touches every caller. Three sites in `PathTracer.slang` (lines 1381, 1385, 1419). Mechanical change, low risk.
- **`LightSample` hit plumbing**: if `ls.hit` isn't currently populated in `generateLightSample`, we need to populate it. Requires reading `getEmissiveSampler().sampleLight()` to find what's available. Possible refactor blocker.
- **Analytic-light index gap**: PORT_NOTES says no current storage. Either pack into pathFlags (8 bits = 256-light cap, sufficient for our scenes; risk of collision with other flag bits) or add a struct field (ABI bump, more complete). Defer to 1.B.3.
- **Variance overshoot on glossy surfaces**: paper acknowledges. May reveal as art5 regression on Sponza or Bistro. Mitigation: §15 firefly clamp can be re-engaged from K=∞ → K=1000 if needed.
- **Shift code branches for `rcVertexHit invalid + lastVertexNEE`**: audit suggests current EnvMap branch at line 437 doesn't handle d=2 NEE because of the `!lastVertexNEE()` condition. Need to extend without breaking the existing escape-path flow.

## Stop conditions

- If 1.B.1 (Emissive only) regresses canonical `restirpt_b{N}` metrics → too-broad gate; revert and re-derive condition.
- If 1.C Stage A retest doesn't recover Cornell to ~5% range → Phase 1 alone is insufficient; investigate residual issues (e.g. Lin 2026 supplemental §5 multi-sample MIS may also be needed at d=2 boundary).
- If any sub-phase produces Inf pixels → halt and diagnose. Current §1 isIntegrandInvalid + §13 writeback safety net should catch them, but a forced-rcVertex path with mismatched fields could escape the existing guards.

## Out of scope

- Phase 3 Stage A unification implementation — this plan is a prerequisite; Stage A retest is verification only (1.C).
- Lin 2026 supplemental §5 multi-sample MIS at d=2 (`m_1 = M·p_1/(M·p_1+p_2)`) — only relevant if RIS-at-NEE is enabled (M_RIS > 1). Our current code uses M_RIS = 1 → standard single-sample MIS already correct.
- Volumetric NEE — paper doesn't address; codebase doesn't support volumetric.
- Multi-light RIS at x_1 (Lin 2026 §6.1's "optional RIS for many-light scenes") — orthogonal optimization; would require Phase 1 done first anyway.

## 2026-05-06 attempt status — DISABLED

Three structurally correct fixes attempted on Cornell_1AL Stage A test variant
(`restirpt_unified_b{N}`, kDisableDirectIllumination=False / useRTXDIDirect=False
/ useDirectLighting=False). Plateaued at ~4× canonical regression:

| stage | b1 mean_err | b4 | b8 |
|---|---|---|---|
| Bare config flip (no fix) | 20.43% | 16.58% | 16.43% |
| + dstF2=1 for isRcVertexNEE | 16.85% | 14.28% | 14.17% |
| + lightLeOnly override (rcVertexIrradiance encoding) | 16.78% | 14.23% | 14.12% |
| + cachedJacobian populated (scatterPdf, G_src) | **16.78%** (no Δ) | **14.23%** | **14.12%** |
| canonical (RTXDI feed reference) | 3.87% | 3.73% | 3.73% |
| **gap** | **4.3×** | **3.8×** | **3.8×** |

Plumbing landed (kept as scaffolding behind `force_nee_as_rcVertex = false`
gate in PathBuilder.slang):
- `LightSample.packedHit` (Triangle HitInfo for Emissive lights)
- `LightSample.lightNormalW` (for G_src computation)
- `pathFlags.isForcedNEE` flag (bit 17) + `insertIsForcedNEE`/`isForcedNEE` accessors
- `addNeeVertex` extra params: `neeLightHit`, `lightLeOnlyContribution`, `cachedJacobianForceNEE`
- PathTracer.slang caller computes Le×thp + scatterPdf + G_src and passes them
- Shift.slang `dstF2=1` gated on `srcReservoir.pathFlags.isForcedNEE()` (only fires when re-enabled)

`restirpt_unified` variant in `VisCache_Ladder00.py` and `ReSTIRPT_StageA_Test.py`
left in place (commented out in step 00) for re-engagement.

## Why incremental fixes failed — root cause hypothesis

Shift.slang line ~569 MIS weight:
```glsl
float misWeight = PathTracer::evalMIS(1, isRcVertexNEE ? lightPdf : dstRcVertexScatterPdfAll, 1, isRcVertexNEE ? dstRcVertexScatterPdfAll : lightPdf);
```

For force-NEE: `dstRcVertexScatterPdfAll = evalPdfBSDF(rcVertexSd, ...)` evaluated
at the LIGHT SURFACE returns 0 (emissive material has no scatter). MIS weight
degenerates to `lightPdf / (lightPdf + 0) = 1.0`. The BSDF-sampling alternative
strategy that ALSO fires at d=2 in Stage A config (BSDF scatter from x_1 hits
the light triangle directly, line 1094 of PathTracer.slang) is then **not
properly weighted against** — both NEE-from-x_1 and BSDF-hit-x_2 paths flow into
the resampler with effectively unit MIS weight, producing double-counting on
their joint contribution.

The correct MIS form for Stage A's force-NEE-as-light topology should evaluate
the BSDF-sampling alternative pdf at PRIMARY (`dstPDF1All` from earlier in the
shift), not at the LIGHT SURFACE. But this rewires multiple Shift.slang code
paths — the existing `dstRcVertexScatterPdfAll` is shared with BPR's
NEE-at-scatter-rcVertex case where evaluating at rcVertexSd IS correct.

Fixing this cleanly requires Lin 2026 supplemental §5 re-read for the proper
MIS formulation under Stage A's unified DI+GI integrand-sharing path tree.

## Paper re-read priorities for next attempt

When resuming Phase 1 / unblocking Phase 3, read in this order:

1. **Lin 2026 supplemental §5** — RIS-based NEE in primary sample space.
   Specifically: how does §5 derive the multi-sample MIS weight `m_1 = M·p_1/(M·p_1 + p_2)`
   for the d=2 boundary? What are `p_1` and `p_2` evaluated at — primary or rcVertex?
   How does it interact with the path-tree shift Jacobian when the rcVertex IS the light
   (vs BPR's rcVertex-as-scatter)?

2. **Lin 2022 supplemental** — original GRIS resampling-MIS derivation and how it
   handles "NEE-terminated paths" in the path-tree estimator. What does the supplemental
   say about the BSDF-sampling-alternative pdf for these paths?

3. **DQLin's BPR derivation** (paper + supplemental of the original ReSTIR PT) — how
   does DQLin's BPR actually treat NEE-at-rcVertex vs NEE-at-light? Our shift code's
   `isRcVertexNEE` branch handles the former; the topology distinction we hit is
   whether the LIGHT itself is the rcVertex.

4. **Veach 1997** thesis chapter on bidirectional path connections — for ground-truth
   reference on path-tree MIS weights at boundary cases (d=2 NEE, escape-vertex hit-light).
   Sanity-checks Lin's formulations.

5. **Hedstrom 2025 ReSTIR BDPT** (already in `docs/references/`) — closest published
   work on "NEE light is part of GRIS reservoir" topology. May have explicit shift
   formulations for our case.

## Re-enable checklist (for next session)

1. Read paper sources above.
2. Derive correct MIS form for Stage A force-NEE topology (BSDF-sampling-alt evaluated at primary).
3. Modify Shift.slang's MIS computation (line ~569) — likely a separate code branch gated on `isForcedNEE`, since BPR's case still needs current behavior.
4. Flip `force_nee_as_rcVertex = false` → `(rcVertexLength == kMaximumPathLength) && useHybridShift && neeLightHit.isValid()`.
5. Uncomment `restirpt_unified` variant in `VisCache_Ladder00.py`.
6. Run Stage A test on Cornell — expect mean_err to drop from 16.78% to within 1-2× of canonical (3.87%).
7. If still off, audit visibility-test rejection rate (`evalSegmentVisibility` at line ~588) — destination pixels' shadow rays may differ from source pixels'; high rejection rate adds bias even with correct MIS.
8. Multi-scene check on Sponza (DirectionalLight + EnvMap + emissive → tests 1.B.2/1.B.3 prerequisites).

## Cross-references

- Stage A probe results (the empirical motivation): `runtime/captures/ladder/00/CornellBox_1AreaLight/stats.csv`, variants `restirpt_unified_b{1,4,8}`.
- Phase 3 plan: `.plans/restirpt-stage-a-unification.md`.
- Phase 0 research notes: `.plans/restirpt-gris-finish.notes.md`.
- Parent plan (now stale on Phase 1 framing): `.plans/restirpt-gris-finish.md`.
- Paper text: `docs/references/Lin2026_ReSTIR_PT_Enhanced.pdf` §6.2.3, supplemental §5.
- Reference impls (neither implements §6.2.3): `refs/DQLin_ReSTIR_PT/`, `refs/NVlabs_conditional_ReSTIR/`.

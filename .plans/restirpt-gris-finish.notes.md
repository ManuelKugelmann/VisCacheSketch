# GRIS finish — research notes (Phase 0 deliverable)

Working notes for `.plans/restirpt-gris-finish.md`. Updated as later phases refine understanding.

Sources read (paper text extracted via `pdftotext` to `/tmp/lin2026_main.txt` and `/tmp/lin2026_supp.txt`):
- Lin 2026 main §6.1, §6.2.3, §6.3 (key prose extracted below)
- Lin 2026 supplemental §1 (PSS Jacobian), §5 (RIS-based NEE), §6 (RR PSS)
- Audited refs: `refs/DQLin_ReSTIR_PT/`, `refs/NVlabs_conditional_ReSTIR/`

---

## Phase 1 — Forced NEE Light Reconnection (Lin 2026 §6.2.3)

### What §6.2.3 actually says

> During random replay, paths ending at NEE-sampled light vertices incur expensive light sampling that other path types avoid. Since replayed random numbers usually select the same light (e.g., with power-based sampling), **we force reconnection to such vertices if no earlier reconnection is found**. This removes light sampling from random replay, improving performance. Any potential variance increase is mitigated by path MIS weights, which already downweight these cases (as such surfaces are typically glossy).

### Re-interpretation vs PORT_NOTES.md

PORT_NOTES.md framed this as "hydrate `LightSample` from stored fields at the replay-NEE call site." The paper says something **stricter and structurally different**: classify the NEE light vertex AS the reconnection vertex (rcVertex) at initial sample time, when no earlier rcVertex was selected. The replay branch then doesn't sample the light at all — the reconnection shift handles the NEE→light edge directly.

This is **not a `Shift.slang` edit** — it's a **path classification edit in `PathBuilder.slang::addNeeVertex` and `PathTracer.slang::nextVertex`**.

### The right design

Reservoir storage already has the slots for "NEE-at-rcVertex" — see `PathReservoir.slang` lines 234–239:
- `rcVertexHit` — `TriMeshHitInfo` of the reconnection vertex (covers emissive triangles)
- `rcVertexWi[kRcAttrCount]` — incident direction at rcVertex
- `rcLightPdf` — light pdf
- `pathFlags` carries `rcLightType` via `insertRcLightType` (lines 248–251)

`addNeeVertex` already uses these slots when `is_rcVertex=true` (lines 133–135 of PathBuilder.slang). The current path-classification logic decides rcVertex by roughness/footprint criteria — and **does not currently force NEE termination to be rcVertex when no earlier rcVertex was chosen**. That's the missing piece.

### Concrete touchpoints

| File | Function | Change |
|---|---|---|
| `PathBuilder.slang` | `addNeeVertex` (line 118) | When `pathReservoir.pathFlags.rcVertexLength()` is unset (== `kMaximumPathLength`) and the path is about to terminate at NEE → force `is_rcVertex=true` for this NEE vertex; populate `rcVertexHit + rcVertexWi[1] + rcLightPdf + rcLightType`. Currently, `is_rcVertex` is determined upstream by the rough-vertex selector — extend that selector or add a fallback at `addNeeVertex` entry. |
| `PathTracer.slang::nextVertex` | line 1308 NEE branch | After classification: if the NEE was forced-rcVertex, the **replay branch** at line 1396 (where `path.enableRandomReplay && sampleLights` currently `skipLightSampleRandomNumbers`) becomes a no-op — but **also**, the `terminateRandomReplayForNEE` branch at line 1308 should NOT call `generateLightSample`. Instead the replay terminates the path; `Shift.slang::computeShiftedIntegrandHybrid` already does the reconnection at rcVertex. |
| `Shift.slang::computeShiftedIntegrandHybrid` | NEE rcVertex case | Verify it handles `rcLightType + rcLightPdf + rcVertexHit + rcVertexWi[1]` fully — emissive (TriMesh hit), analytic (point/area light index → need to encode in `pathFlags` since `rcVertexHit` is `TriMeshHitInfo`), env (direction). |
| `PathReservoir.slang` | possibly | If analytic/env light identity needs more bits than `pathFlags.rcLightType` carries (only 2 bits for type), consider adding a `rcLightIndex` field. **Audit before coding** — `rcVertexHit` may already encode triangle identity for emissive, and analytic/env may not need an index because `gScene.getLight(idx)` is replayed deterministically by SG — **wait, that's exactly the bug**, the SG draw differs per pixel. So analytic light index DOES need explicit storage. |

### Open question (must resolve before Phase 1.B coding)

For analytic / env lights — does `rcVertexHit` carry enough info to identify the source light, or does the reservoir need a new `rcLightIndex` field? Triangle index is in `TriMeshHitInfo`. For analytic lights, current code at line 1361–1364 patches `ls.pdf` to `getAnalyicSelectionProbability()` — implying the analytic light's identity is currently NOT stored on the reservoir. **This is the storage gap**.

Resolution path:
1. Read `addNeeVertex` for the analytic-light branch and confirm what's stored.
2. If light index is missing, add a `uint rcLightIndex` to `PathReservoir`. Struct-size bump → cbuffer ABI change → ReSTIRPTPass.cpp resize.
3. For env: direction is stored in `rcVertexWi[1]`; pdf via env importance map evaluation at that direction is deterministic per pixel, so no extra storage needed.

### Verification expected impact (Lin 2026 Table 5 / supplemental Table)

From the supplemental ablation table I extracted (line 613 of `/tmp/lin2026_supp.txt`):
- Veach Ajar baseline: 21.99 ms / FLIP 3.57
- +Forced NEE reconnect: **15.75 ms / FLIP 3.98** — **28% time saving**, marginal FLIP cost (matches paper claim "potential variance increase mitigated by path MIS weights")

So the win is **performance**, with neutral-to-slight quality cost. PORT_NOTES.md's "expected to materially improve hybrid-shift acceptance rate on multi-light scenes" was extrapolation; the paper's actual claim is performance.

### Updated Phase 1 exit criteria

- All scenes finite (0 Inf, 0 NaN).
- Frame time ↓ on at least one multi-light scene at b=4 x1 (the paper's claim).
- mean_err neutral-to-slight regression acceptable (paper acknowledges this).
- PORT_NOTES.md §12 #3 status updated; the "expected impact" section there should be edited to say **performance, not quality**.

---

## Phase 2 — Vector-Valued Resampling Weights (Lin 2026 §6.3)

### What §6.3 says

> ReSTIR inherently suffers from color noise because resampling operates on a scalar target function p̂, while the integrand F() is RGB-valued. GRIS therefore samples primarily according to luminance, leaving chroma poorly importance-sampled.
>
> Prior work [Kettunen et al. 2023; Lin et al. 2022] noted that the estimate F() can be improved by marginalizing over the random index choice. In ReSTIR PT, this improvement comes at almost no extra cost: since p̂ = |F|, F() is already evaluated during spatial reuse. **We accumulate vector-valued resampling weights w_i = m_i(...) F(X_i) |J_i| and use Σw_i for shading.** As spatial neighbors typically contain uncorrelated chroma noise, spatial reuse naturally averages it out. This decouples resampling and shading: scalar weights drive future resampling, while vector weights are used for shading.

### Why the first attempt failed (PORT_NOTES.md §12 #4 retro)

PORT_NOTES.md says the prior attempt accumulated `Σ in_F × J × W × misWeight` and finalized as `weightVec /= p_hat × M`. Result: Cornell +20%, Sponza +1920%.

The paper says `w_i = m_i F(X_i) |J_i|`. Comparing:
- `m_i` = MIS weight (matches "misWeight" in attempt)
- `F(X_i)` = vector integrand at sample X_i (matches "in_F")
- `|J_i|` = Jacobian of shift (matches "J")

The attempt also multiplied by `W` (UCW). **The paper does NOT include UCW in the vector weight.** That's the bug. The UCW already factors in via `m_i` for resampling MIS — including it again in the vector accumulator double-counts.

### Final shading formula

> use Σw_i for shading

So: shading color = `Σ_i w_i / something`. The "something" is **not specified explicitly in §6.3** but is constrained by:
- Scalar form has shading `F_chosen × W_chosen` where `W_chosen = (Σ scalar_w_i) / (p̂_chosen × M)`
- Vector form replaces `F_chosen × scalar_W` with `Σ vector_w_i / (p̂_chosen × M)`

So **final shading: `Σ_i w_i / (p̂_chosen × M)`** where `w_i = m_i F(X_i) |J_i|`.

This is a less aggressive accumulator than the prior attempt — no UCW factor.

### Phase 2.A re-derivation

Before coding, write out:
1. **Scalar w_i** as DQLin currently codes it (audit `PathReservoir::add` and `merge`).
2. **Paper vector w_i = m_i F(X_i) |J_i|** with each term sourced from the reservoir code.
3. **Final shading** `Σw_i / (p̂_chosen × M)`.
4. **Diff** between attempt and paper — confirm the UCW double-count hypothesis.

### Phase 2.B implementation

| File | Change |
|---|---|
| `PathReservoir.slang` | Re-enable `float3 weightVec` accumulator. **Drop the UCW (`W`) factor** from the previous attempt's accumulation — only `m_i × F_i × J_i`. |
| `PathReservoir.slang::finalizeRIS/finalizeGRIS` | New `finalizeVecRIS/Vec`: `weightVec /= (p_hat × M)` — same denominator, just vector. |
| Output stage | `outputColor = weightVec` (replaces `F_chosen × scalar_W`). |
| `Shift.slang` | every site that contributed to scalar weight contributes vector counterpart with the corrected formula. |

### Verification

- **Pre-test invariant:** `weightVec.luminance() ≈ scalar_weight` to within FP noise at insertion (modulo `m_i`'s scalar/vector coupling). Add a debug assert: if violated → math is still wrong.
- **Per-channel variance comparison:** the win is chroma noise, not mean error. Compare R/G/B variance separately at fixed SPP.

### Note: §6.3 vs Stage A interaction

§6.3 vector weights are independent of Stage A (§6.1). Either can ship without the other. **Phase 3 does not strictly require Phase 2** — the plan ordering is for math-machinery sharing, but it's not a hard dependency. If Phase 2 turns out painful, Phase 3 can proceed independently.

---

## Phase 3 — Stage A Unification (Lin 2026 §6.1 + Supplemental §5)

### What §6.1 says

> Lin et al. [2022] start by initially sampling a path tree by emanating NEE rays from BSDF-sampled vertices [x_2, ..., x_k]. Initial resampling selects and stores a single path in the reservoir, i.e. x̄ = [x_0, x_1, x_2, ..., x_k] with a single NEE/BSDF ray connecting to a light at x_k with k ≥ 3 originally.
>
> **Direct light can be handled by simply tracing another NEE ray from x_1 when generating the path tree, and giving the (unified) initial resampling a chance to select a shorter direct lighting path (k = 2) from the tree.** The selected path is thus sampled from the full path space.

### Supplemental §5: the multi-sample MIS weight

> With M > 1 (M being the candidate count) RIS for NEE, we replace the original single-sample MIS weight in the integrand to multi-sample MIS weight, i.e. for an NEE path x̄, m_1(x̄) = p_1(x̄)/(p_1(x̄) + p_2(x̄)) where p_1 and p_2 represents NEE and BSDF light sampling strategy, respectively.

So:
- `p_1` = NEE light sampling pdf at the terminal vertex
- `p_2` = BSDF light sampling pdf (the "you happened to hit a light by sampling BSDF" path)
- `m_1 = p_1 / (p_1 + p_2)` (single-sample form). Multi-sample form (M > 1 RIS): `m_1 = M·p_1 / (M·p_1 + p_2)`.

This `m_1` factor enters the path's contribution via `F(x̄) × m_1` for NEE-terminated paths.

### Why the first attempt failed (PORT_NOTES.md retro)

> d=2 paths whose rcVertex is at x_1 fail the GRIS shift, producing ~200k Inf pixels per scene. The full multi-sample MIS weight ω_1 = M·p_1 / (M·p_1 + p_2) is needed for d=2 + d≥3 to share the path tree correctly.

The minimal Stage A attempt enabled internal NEE at x_1 (creating d=2 paths) but **didn't add the m_1 MIS weight** to those paths. Without m_1, they shared the path-tree estimator with d≥3 paths under double-counting (or under-counting), which destabilized the GRIS shift's Jacobian.

### Concrete touchpoints

| File | Function | Change |
|---|---|---|
| `PathTracer.slang::nextVertex` | primary-hit (`isPrimaryHit`) NEE branch | Currently gated by `!(kDisableDirectIllumination && isPrimaryHit)`. To enable Stage A: drop the `kDisableDirectIllumination` gate at primary, but apply `m_1 = p_1 / (p_1 + p_2)` factor to `Lr` for the d=2 path. |
| `PathTracer.slang::handleHit` | BSDF-hit-light branch (escape vertex) | Already computes `lightPdf` for MIS at line 1107–1117 (for emissive) and 1574–1586 (for envmap). The `evalMIS(1, ls.pdf, 1, scatterPdf)` call at line 1344 already implements the single-sample form. For multi-sample (M>1 RIS) extend to `M·p_1 / (M·p_1 + p_2)`. |
| `Params.slang` / `StaticParams.slang` | static-param flag | Add `kEnableUnifiedDIGI` (bool) so Stage A can be opt-in for ablation. Initial default: `false` (preserves DQLin canonical until Phase 3 is verified). |
| `scripts/ReSTIRPT_Graph.py` | variant kwarg | New `restirpt_unified` variant: `kwargs={'disableDirectIllumination': False, 'useRTXDIDirect': False, 'useDirectLighting': False, 'enableUnifiedDIGI': True}`. |
| `ReSTIRPTPass.cpp::setScene` | `rejectShiftBasedOnJacobian` | Per PORT_NOTES, forcing it on broke the DI=on branch. Stage A means DI=on, so this needs careful re-evaluation. Likely keep at DQLin's default (animated-only) and verify Stage A doesn't trip on it. |

### Phase 3 sub-phases

1. **3.B.1 — m_1 weight added at primary-hit NEE, but `kDisableDirectIllumination=true` still in canonical config.** No-op shader change (the branch is gated off). Verify behavior unchanged.
2. **3.B.2 — Flip `kEnableUnifiedDIGI=true` in opt-in variant.** Run on Cornell first. Check 0 Inf at d=2 boundary.
3. **3.B.3 — Scale to Sponza, Bistro.** If clean, promote to canonical.

### Stop conditions

- If any sub-phase produces Infs → halt, do not paper over with clamps. Diagnose the m_1 factor first (PORT_NOTES retro hypothesis).
- If 3.B.2 produces Infs but the cause is NOT m_1 → there's a missing ingredient beyond the supplemental §5 prose. Document, escalate.

---

## Cross-cutting findings

### NVlabs conditional-restir-prototype audit

`refs/NVlabs_conditional_ReSTIR/Source/Falcor/Rendering/ConditionalReSTIR/` does NOT implement Lin 2026 forced NEE reconnection (predates the 2026 paper). It also does not have a vector-valued weight accumulator. So **Phases 1, 2, 3 have no public reference implementation**; we derive from paper text.

### Reservoir struct ABI

Phase 1 may need a new field (`rcLightIndex` for analytic lights). Phase 2 needs to re-activate `weightVec` (already in struct, dormant). Phase 3 needs a static-param flag (`kEnableUnifiedDIGI`).

If both Phase 1 + Phase 2 grow the struct, batch the cbuffer ABI bump in one commit to minimize re-resize churn.

### Test harness

`scripts/VisCache_LadderRPT00.py` covers b ∈ {1, 4, 8} × {Cornell_1AL, Cornell_32PL, Sponza, BistroInterior} and matches PORT_NOTES tables. Re-use as-is for all three phases.

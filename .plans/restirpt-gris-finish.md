# ReSTIRPTPass — finish the GRIS port

Three remaining algorithmic items from Lin 2022 GRIS / Lin 2026 Enhanced.
Listed in execution order, ranked by EV-per-risk.

| Phase | Item | Dependency | Expected impact | Risk |
|---|---|---|---|---|
| 1 | §6.2.3 Forced NEE reconnection | none | **performance** (~28% time savings per Lin 2026 supp); FLIP roughly flat | medium — path classification edit + reservoir ABI bump for `rcLightIndex` |
| 2 | §6.3 Vector-valued resampling weights | independent of Phase 3 | chroma noise ↓ during spatial reuse | medium — math re-derive (UCW double-count was the prior bug) |
| 3 | §6.1 Stage A unification (drop RTXDI feed) | needs `m_1 = p_1/(p_1+p_2)` MIS weight at d=2 boundary | algorithmic minimality | high — d=2 boundary stability |

**Phase 0 found** (see `.plans/restirpt-gris-finish.notes.md`):
- §6.2.3 is PERFORMANCE optimization in the paper, not a quality fix as PORT_NOTES.md framed it.
- §6.2.3 is path-classification at sample time (force NEE vertex AS rcVertex), not a `LightSample` hydration at replay time. Bigger surgery than PORT_NOTES.md sketched. May need new `rcLightIndex` field for analytic lights.
- §6.3 prior attempt bug hypothesis: included UCW factor; paper's `w_i = m_i F(X_i) |J_i|` has no UCW. UCW already factors via m_i for resampling.
- §6.3 and §6.1 are **independent** — Phase 2 is not a hard prerequisite for Phase 3.
- NVlabs conditional-restir-prototype implements **none of the three**; no public reference code.

Everything documented as **attempted+reverted** in `Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md` §12 stays reverted unless that phase's research updates the math.

---

## Phase 0 — Research grounding (before any code change)

Deliverable: `.plans/restirpt-gris-finish.notes.md` — a single math+code crib that all three phases work from. **One file, not three.** Update it as later phases refine understanding.

Reading list, in this order:

1. **Lin 2022 main** (`docs/references/Lin2022_GRIS_ReSTIR_PT.pdf`) — §3.4 (GRIS estimator), §4 (shift mappings), §5.2 (pairwise MIS / generalized balance heuristic). Anchor for the canonical scalar weight algebra.
2. **Lin 2022 supplemental** (`docs/references/Lin2022_GRIS_ReSTIR_PT_supplemental.pdf`) — derivation of the `ω` MIS weights, especially the multi-sample form. **This is where the Phase 3 d=2 boundary math lives.**
3. **Lin 2026 main** (`docs/references/Lin2026_ReSTIR_PT_Enhanced.pdf`) — §4 (footprint criterion, already implemented), §6.2.3 (forced NEE reconnection — Phase 1), §6.2.4 (RR-skip, already implemented), §6.3 (vector-valued weights — Phase 2). Read §6.2.3 prose for the exact replay-vs-canonical asymmetry.
4. **Lin 2026 supplemental** (`docs/references/Lin2026_ReSTIR_PT_Enhanced_supplemental.pdf`) — §5: Stage A unification (Phase 3) and the `ω₁ = M·p₁/(M·p₁+p₂)` boundary weight.
5. **NVlabs conditional ReSTIR** (`refs/NVlabs_conditional_ReSTIR/Source/Falcor/Rendering/ConditionalReSTIR/`) — search for vector weight accumulator (`weight3` / `weightVec`), forced NEE replay, and any `ω₁` factor in `Shift.slang` and `PathReservoir.slang`. Lin's group; if §6.3 has a public implementation, this is where it would be.
6. **DQLin reference** (`refs/DQLin_ReSTIR_PT/Source/RenderPasses/ReSTIRPTPass/`) — confirm the canonical replay-side `generateLightSample` call sites and what's stored on the reservoir at NEE termination.

Output of Phase 0:
- A short pseudo-code for each of the three algorithmic changes (NEE hydration, vector weight accumulation, Stage A `ω₁`).
- A list of which fields on `PathReservoir`/`PathState` are already populated and which are missing.
- Verification: at the end of Phase 0, the notes file must answer "given a stored NEE reservoir, what exact bytes do I need to reconstruct an identical `LightSample` for replay?" and "for the d=2 path with rcVertex at x_1, how is `p_2` computed and where does it come from?"

Time budget: 1 working session. Do not start Phase 1 until both questions above have answers.

---

## Phase 1 — §12 #3 Forced NEE light reconnection

**Why it's first:** independent of Phases 2/3, well-scoped, design already sketched in PORT_NOTES.md, expected to materially lift hybrid-shift acceptance on multi-light scenes (32PointLights, Sponza, Bistro).

### What's wrong now
Replay-side `traceRandomReplayPath` (and `traceTemporalUpdate`) call `generateLightSample` on the NEE-terminating bounce, drawing a *fresh* light from the alias table. The shift-validity check then compares replay's chosen light against the source reservoir's stored light, almost always mismatches, and the candidate gets rejected. This drops hybrid-shift acceptance.

### Fix sketch
Hydrate the `LightSample` from already-stored reservoir fields instead of re-sampling:

- `pathFlags.lightType` → which light array (env / emissive triangle / analytic point / area)
- `lightPdf` → pdf at sample
- `rcVertexHit` → hit point on the light (or direction for env)
- `rcVertexWi[k]` → outgoing direction (for env) / surface frame on light

### Touchpoints

| File | Function | Change |
|---|---|---|
| `Shift.slang` | `traceRandomReplayPath` | NEE-terminating branch: replace `generateLightSample(...)` with `hydrateLightSampleFromReservoir(srcReservoir)` |
| `Shift.slang` | `traceTemporalUpdate` | same |
| `Shift.slang` (new) | `hydrateLightSampleFromReservoir` | helper, reads `pathFlags.lightType` + `lightPdf` + `rcVertexHit` + `rcVertexWi[]` and rebuilds `LightSample` |
| `PathBuilder.slang` | `addNeeVertex` | confirm all four fields are populated on the reservoir at NEE termination — add any that are missing |

If a needed field is missing on the reservoir, add it to `PathReservoir.slang` (struct grow → cbuffer ABI bump → `ReSTIRPTPass.cpp` resize). Document in PORT_NOTES.

### Open algorithmic question
Does the hydrated `LightSample` go through the **same shadow ray** as a fresh sample, or is V already implicit in the reservoir's `F`? Lin 2026 §6.2.3 prose: shadow ray is re-cast in replay (occluder may differ between source and replay pixel). Do not skip the shadow ray.

### Verification
- Compile + smoke (`.scripts/smoke.sh`) — must produce 0 Inf, 0 NaN.
- `runtime/pythondist/python.exe scripts/run_ladder.py -s RPT00 -c CornellBox_32PointLights,Sponza,BistroInterior` (or whichever multi-light scenes are in the harness).
- Compare against current PORT_NOTES table. Pass = at least one of {Cornell32PL, Sponza, Bistro} improves on `mean_err` at b=4 x1, and none regress beyond noise (~2%).
- If only single-light Cornell improves, suspect a bug — the change should be neutral on single-light.

### Rollback
Single commit. If verification fails, revert + record the failure mode in PORT_NOTES under "Future additions" so the next attempt has the data.

### Exit criteria
- All scenes finite (0 Inf).
- Multi-light scenes show mean_err improvement vs current `restirpt_b{N}` baseline.
- PORT_NOTES.md §12 #3 status updated from "Open / Pending" → "Implemented".

---

## Phase 2 — §12 #4 Vector-valued resampling weights (correct re-derivation)

**Why second, not first:** Phase 3 (Stage A) needs the same MIS machinery; doing them in opposite order would mean re-deriving twice. Doing Phase 2 first sets up Phase 3.

### What went wrong on the first attempt (per PORT_NOTES.md §12 #4)
- Added `float3 weightVec` parallel to scalar `weight`.
- Accumulated `Σ in_F × J × W × misWeight`.
- Finalize: `weightVec /= p_hat × M`.
- Output: `weightVec` instead of `F × weight`.
- Result: Cornell +20%, Sponza +1920%. Math wrong.

### Hypothesis about why
PORT_NOTES already names the suspect: the `ω₁` multi-sample MIS weight from Lin 2022 supplemental Eq. §5 likely factors into the vector accumulation, not just at NEE termination. The scalar form hides this because luminance commutes with `ω₁`; the vector form doesn't.

### Phase 2.A — math re-derivation (no code)
- Read Lin 2022 supplemental §5 + Lin 2026 §6.3 + the supplemental for §6.3 carefully.
- Write out, in `.plans/restirpt-gris-finish.notes.md`:
  - The scalar GRIS weight as DQLin currently implements it (audit).
  - The Lin 2026 vector form, with every term labeled (target function, Jacobian, MIS weight, importance weight).
  - The first attempt's vector form, with every term labeled.
  - The `diff` — exactly which factor is in one and missing in the other.
- Cross-check against `refs/NVlabs_conditional_ReSTIR/.../PathReservoir.slang` (search for any `float3` accumulator in merge methods). If NVlabs ships a vector accumulator, the math is there.

**Do not write any slang until this section of the notes file is complete.** Phase 2 failed once because it skipped this step.

### Phase 2.B — implementation
Only after 2.A:

| File | Change |
|---|---|
| `PathReservoir.slang` | re-add `float3 weightVec` (already in struct, dormant). Update accumulators in `add`, `merge`, `mergeWithResamplingMIS` per the corrected math. |
| `PathReservoir.slang` | `finalizeRIS` / `finalizeGRIS` — vector divide with the right denominator (this is where the prior attempt diverged). |
| `Shift.slang` | every site that contributed to scalar `weight` must contribute the vector counterpart — audit, don't blanket-edit. |
| Output stage | `outputColor = weightVec` instead of `F × weight` (only after the merge math is verified). |

### Verification
- **Pre-test for math:** at insertion time, `weightVec.luminance() == weight` should hold to within float32 round-off (modulo the `ω₁` factor). Add an assert path under `#ifdef VEC_WEIGHT_DEBUG` that fires per-pixel and aborts if the invariant breaks. This catches the "wrong factor" failure mode immediately, without waiting for ladder runs.
- Ladder run on Cornell_1AL b=4 x1, Sponza b=1, Cornell_32PL b=4 x1.
- Pass = same or better than scalar form on every scene. (Vector form is not expected to *improve* mean_err materially — the win is chroma noise reduction. Look at per-channel variance, not just luminance error.)

### Rollback
Same as before — `float3 weightVec` field stays dormant. The code that currently writes to it can keep doing so; the corrupted math change reverts.

### Exit criteria
- VEC_WEIGHT_DEBUG assert never trips on a 1000-frame Cornell run.
- Per-channel variance (not just mean_err) lower than scalar at matched SPP on at least one scene.
- PORT_NOTES.md §12 #4 status: "Implemented; chroma noise improvement N% on scene X."

---

## Phase 3 — Stage A unification (Lin 2026 §5 supplemental)

**Why last:** highest pipeline risk, and the math machinery from Phase 2 is needed at the d=2 boundary.

### What's wrong now
Canonical mode runs RTXDI as an external direct-light feed (`disableDirectIllumination=true`, `useRTXDIDirect=true`). Lin 2026 Stage A says: turn this off, let internal NEE handle primary direct *and* indirect together. This is the algorithmically minimal form.

The first attempt failed because d=2 paths (rcVertex at x_1) need MIS weighting against d≥3 paths from the *same primary hit*, and the minimal version omitted the multi-sample MIS weight `ω₁ = M·p₁ / (M·p₁ + p₂)`. Result: 200k Inf pixels per scene.

### Phase 3.A — math
- Pin down what `p₁` and `p₂` are at the d=2 boundary in our path-flag encoding.
- Identify where `M` enters (per-pixel reservoir M, or canonical M=1?).
- Cross-check NVlabs's port: do they ship Stage A unification with the `ω₁` factor? If yes, code-check against their implementation directly.

### Phase 3.B — gated rollout
1. **Sub-phase 3.B.1:** add `ω₁` weight at d=2 boundary *while still feeding RTXDI*. The weight should evaluate to ~1 in the current configuration (because internal NEE at primary is suppressed), so this is a no-op shader change. Verify zero behaviour change.
2. **Sub-phase 3.B.2:** flip `disableDirectIllumination=false`, `useRTXDIDirect=false`, `useDirectLighting=false`. Now `ω₁` activates non-trivially. Run on Cornell first (smallest scene → fastest debug loop).
3. **Sub-phase 3.B.3:** scale to Sponza, Bistro.

If any sub-phase produces Infs, stop and diagnose. Do not skip ahead.

### Touchpoints
| File | Change |
|---|---|
| `Shift.slang` | d=2 path tree: insert `ω₁` factor at the appropriate site (TBD by Phase 3.A) |
| `PathTracer.slang` | NEE at primary hit: enable when `disableDirectIllumination=false` |
| `Params.slang` / `StaticParams.slang` | flip default config in the canonical kwarg path of the graph script |
| `scripts/ReSTIRPT_Graph.py` | re-key `restirpt` variant to `disableDirectIllumination=false` + `useRTXDIDirect=false` |
| `ReSTIRPTPass.cpp::setScene` | re-evaluate `rejectShiftBasedOnJacobian` default — note from PORT_NOTES that forcing it on broke the DI=on branch catastrophically, so this needs care |

### Verification
- Each sub-phase: 0 Inf, 0 NaN, ladder run on the target scene.
- Final Stage A: at least one of {Cornell, Sponza, Bistro} improves vs the current RTXDI-feed config; none regress.
- The "RTXDI feed" config remains a valid alternative variant in `ReSTIRPT_Graph.py` for ablation comparison.

### Rollback
Most invasive of the three — flip the four config defaults back, leave the `ω₁` weight in (it's algorithmically correct at d=2 regardless of config).

### Exit criteria
- All scenes finite.
- PORT_NOTES.md "Supported configurations" table updated: "DI feed mode" demoted from canonical to ablation; "Stage A unified" promoted to canonical.
- PORT_NOTES.md §12 status: "Stage A unification: Implemented."

---

## Cross-cutting

### Test harness
Use the existing `VisCache_LadderRPT00.py` step. The b ∈ {1, 4, 8} × {Cornell_1AL, Cornell_32PL, Sponza, BistroInterior} grid is already wired and matches the PORT_NOTES tables. Per-phase: just rerun this step, copy the new numbers into PORT_NOTES.

### Branching
Each phase ships as one or two atomic commits on `main` (per CLAUDE.md "small incremental edits"). No feature branches; no worktree — these are sequential and depend on each other. PORT_NOTES.md gets updated in the same commit as the algorithmic change.

### Stop conditions
- If Phase 1 doesn't improve any multi-light scene, do not proceed to Phase 2 — there is a bug in the implementation, not in the higher-phase math.
- If Phase 2.A re-derivation reveals the prior attempt was *correct* and the bug was elsewhere, fold the diagnosis into PORT_NOTES and skip Phase 2.B.
- If Phase 3 produces Infs in sub-phase 3.B.2 and the cause is not the `ω₁` factor, halt — there is a third missing ingredient, document it, do not paper over with clamps.

### Out of scope (for this plan, do not silently expand)
- §14 ADRRS — needs path-walk refactor in `TracePass.cs.slang`, separate plan.
- §15 firefly K calibration — orthogonal to GRIS correctness.
- BDPT-style light-subpath tracing (Hedström 2025) — separate, much larger effort.
- VisCache integration of any new field — defer to after Phase 3 ships.

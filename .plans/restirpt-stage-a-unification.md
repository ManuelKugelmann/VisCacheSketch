# Phase 3 — Stage A unification (Lin 2026 §6.1 + supplemental §5)

## What this wins

Combines the RTXDI direct-light pass and the ReSTIR PT indirect-light pass into a **single unified GRIS reservoir** that handles d=2 (direct) and d≥3 (indirect) paths from the same path tree. **Algorithmically minimal** (one resampling pass, not two), **unbiased** (paper claim: "improves quality especially on glossy highlights" because direct lighting now benefits from ReSTIR PT's GRIS shift mapping).

Stage A = "drop the external RTXDI feed, let internal NEE at x_1 generate the d=2 path, share the path tree with d≥3 paths via a multi-sample MIS weight."

## Why the previous attempt failed (2026-05-05, reverted)

Set `disableDirectIllumination=false`, `useRTXDIDirect=false`, `useDirectLighting=false`. Combined with §12 #1 footprint criterion. Result: 200k+ Inf pixels on all 3 scenes.

Root cause: d=2 paths whose `rcVertex` is at x_1 fail the GRIS shift Jacobian because they share the path tree with d≥3 paths but are **not weighted against them**. The Lin 2026 supplemental §5 prescribes the multi-sample MIS weight `m_1 = M·p_1 / (M·p_1 + p_2)` to make the two strategies share correctly. The minimal attempt omitted `m_1` entirely; the d=2 contribution was effectively double-counted relative to d≥3, producing infinite resampling weights at the boundary.

## Math (corrected)

For an NEE path x̄ with terminal vertex x_1:
- `p_1(x̄)` = NEE light sampling pdf at x_1 (RIS-augmented if M_RIS > 1)
- `p_2(x̄)` = BSDF light sampling pdf — the alternative strategy where a BSDF-sampled scatter ray happens to hit the light
- `m_1 = M·p_1 / (M·p_1 + p_2)` (multi-sample form). With M = 1 (single-sample NEE) reduces to the standard `p_1/(p_1+p_2)` MIS weight.

Symmetric `m_2 = p_2 / (M·p_1 + p_2)` for the BSDF-hit-light strategy.

Path contribution: `F(x̄) × m_1` for an NEE-terminated path, `F(x̄) × m_2` for a BSDF-terminated path that hit a light. Both flow through the same reservoir.

## Critical files

| File | Change |
|---|---|
| `Source/RenderPasses/ReSTIRPTPass/StaticParams.slang` | New `kEnableUnifiedDIGI` static-param flag, default 0 (preserves DQLin canonical). |
| `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang::nextVertex` | Primary-hit NEE branch (currently gated `!(kDisableDirectIllumination && isPrimaryHit)`): change to `!(kDisableDirectIllumination && isPrimaryHit && !kEnableUnifiedDIGI)`. Apply `m_1 = M·p_1/(M·p_1+p_2)` factor to `Lr` when isPrimaryHit + kEnableUnifiedDIGI. |
| `Source/RenderPasses/ReSTIRPTPass/PathTracer.slang::handleHit` | BSDF-hit-light branches (~line 1107 emissive, ~1574 envmap): extend single-sample `evalMIS(1, ls.pdf, 1, scatterPdf)` to multi-sample `m_2` form when `isPrimaryHit && kEnableUnifiedDIGI`. |
| `Source/RenderPasses/ReSTIRPTPass/Falcor8Compat.slang` | Add `evalMultiSampleMIS(M, p1, p2)` helper if cleaner than inlining. |
| `Source/RenderPasses/ReSTIRPTPass/ReSTIRPTPass.cpp::setScene` | Re-evaluate `rejectShiftBasedOnJacobian` default — PORT_NOTES warns Stage A means DI=on, which previously broke that branch (0 → 57k Infs). Likely keep DQLin's animated-only default and verify Stage A doesn't trip on it. |
| `scripts/ReSTIRPT_Graph.py` | New `restirpt_unified` variant: `disableDirectIllumination=false, useRTXDIDirect=false, useDirectLighting=false, enableUnifiedDIGI=true`. |
| `scripts/VisCache_Ladder00.py` | Add `restirpt_unified_b{N}` baseline alongside canonical `restirpt_b{N}` and `restirpt_bpr_b{N}` so the RTXDI-feed reference is preserved as ablation. |

## Sub-phased rollout

**3.A — math derivation** (no code). Read Lin 2026 supplemental §5 carefully, write out `m_1` and `m_2` derivations in `.plans/restirpt-gris-finish.notes.md`, identify exact insertion sites in PathTracer.slang for each. Cross-check against `refs/NVlabs_conditional_ReSTIR/` (likely no implementation since pre-2026, but worth the audit).

**3.B.1 — `m_1` weight, RTXDI feed still active** (no-op shader change). Add `m_1` factor at d=2 NEE branch + `m_2` at BSDF-hit-light branch, but gated so `kEnableUnifiedDIGI=false` (default) → branches are dead code. Verify bit-identical to current canonical via Cornell + Sponza step-00 ladder.

**3.B.2 — flip `kEnableUnifiedDIGI=true` on Cornell**. New `restirpt_unified_b{N}` variant runs Stage A. Pass criterion: 0 Inf on Cornell at b∈{1,4,8} × x∈{1,4}. If Inf → halt, do not proceed. Diagnose — most likely missing factor in `m_1` or `m_2` derivation.

**3.B.3 — scale to Sponza + Bistro**. If 3.B.2 clean, run on Sponza + Bistro. Pass criterion: at least one scene improves; none regress beyond 2% on luminance metrics. Per the paper, expect glossy-highlight improvements.

## Verification

- **3.B.1 bit-identical check**: dump scalar baseline EXR and `kEnableUnifiedDIGI=false` build EXR — must be byte-identical.
- **3.B.2 Inf check**: scan output for any non-finite pixel.
- **3.B.3 metric battery**: full ladder run, compare `restirpt_unified_b{N}` against `restirpt_b{N}` (RTXDI-feed canonical) on all of {mean_err, art5, RMSE, PSNR, MS-SSIM, FLIP, chroma_var}. Glossy-highlight test scene (currently we don't have one; CornellBox_3AreaLights or a custom Veach-Ajar variant would expose this).
- **rejectShiftBasedOnJacobian interaction**: explicitly test both `false` (default) and `true` to see if Stage A is robust to either setting.

## Risks

- **More invasive than Phase 2.** Changes the canonical config option (drops the RTXDI feed). Mitigated by keeping `restirpt_b{N}` (RTXDI-feed) as ablation reference in step 00.
- **`rejectShiftBasedOnJacobian` interaction unknown.** Per PORT_NOTES, forcing it on for the DI=on configuration previously caused 57k Infs. Stage A is fundamentally a DI=on configuration; need to verify the existing Inf-prevention guards (§1 isIntegrandInvalid, §6 reservoir-write validity) cover this case too.
- **Multi-sample MIS at primary hit** introduces a new BSDF-pdf evaluation per primary-hit pixel. Performance impact likely small but worth measuring.

## Stop conditions

- If 3.B.1 produces ANY non-bit-identical output → math derivation is wrong; halt and re-derive. Stage A core math has to round-trip cleanly through the existing pipeline before activation.
- If 3.B.2 produces Infs → root cause must be identified before retrying. Do not paper over with clamps. The `m_1` weight is the single point of failure for d=2 boundary correctness.
- If 3.B.3 shows luminance regression > 2% on any scene → Stage A is not the regression-free improvement the paper claims for this codebase. Investigate first; consider keeping Stage A as opt-in variant rather than canonical default.

## Out of scope

- **Phase 1 (§6.2.3 forced NEE reconnection)** — deferred per user, paper claim is performance not quality.
- **§14 ADRRS-without-adjoint splitting** — needs path-walk-loop refactor in `TracePass.cs.slang`; separate plan.
- **VisCache integration of Stage A** — defer until Phase 3 ships standalone. Adding cache-amortized direct-light visibility on top of unified GRIS is its own design problem.

## Cross-references

- Phase 0 research notes: `.plans/restirpt-gris-finish.notes.md`
- Parent plan: `.plans/restirpt-gris-finish.md`
- Phase 2 (§6.3 vector weights): `C:\Users\publi\.claude\plans\resilient-stirring-biscuit.md` (approved + implemented 2026-05-06)
- PORT_NOTES.md §12 #4 retro on Stage A's prior failure: `Source/RenderPasses/ReSTIRPTPass/PORT_NOTES.md`
- Lin 2026 main §6.1: `docs/references/Lin2026_ReSTIR_PT_Enhanced.pdf`
- Lin 2026 supplemental §5: `docs/references/Lin2026_ReSTIR_PT_Enhanced_supplemental.pdf`

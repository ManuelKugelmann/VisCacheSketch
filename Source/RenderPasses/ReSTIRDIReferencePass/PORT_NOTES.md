# ReSTIRDIReferencePass — byte-frozen reference

This plugin is the byte-frozen reference implementation of ReSTIR DI:
**verbatim sibling fork** of Falcor's `PathTracer` plugin with WS-ReSTIR DI
intermingled. It mirrors the `ReSTIRPTReferencePass / ReSTIRPTPass` pair
already established in this codebase.

**Why two passes:**
- `ReSTIRDIReferencePass` (this) — frozen at the **parity-with-old-code**
  state established Tick 10 of the refactor /loop. Numbers match the
  pre-refactor Falcor-PathTracer-integrated WS-ReSTIR DI to 3 decimals on
  Cornell_3AL (`R2dP2d=3.13`, `R2dP3d=3.10`, `R3dP3d=3.14`, `R3dP3d_F24P00=3.02`).
  Use as the parity yardstick whenever the active pass diverges.
- `ReSTIRDIPass` (sibling) — actively maintained; gets stripped down to
  DI-only over time. Anything you want to break/iterate on goes there.

**Pattern source:** `Source/RenderPasses/ReSTIRPTReferencePass/`. The two
ReSTIRPT plugins live side-by-side under the same arrangement.

**Maintenance contract:** any change that lands in `ReSTIRDIReferencePass`
must be a bug-fix or upstream Falcor sync, never an algorithm change.
The reference is here precisely to detect drift when the active pass
diverges. If the active pass intentionally departs (e.g., DI-only strip,
ParameterBlock unification), document it in the active pass's PORT_NOTES.md.

## 2026-05-19 — declared K-slot evolution v1 baseline

This pass is the parity yardstick for the upcoming K-slot reservoir
architecture (see `.plans/unified-reservoir-addressing.md`). Going
forward:

- `ReSTIRDIPass` evolves toward K-slot reservoirs: cell struct gains
  `K` slot count, atomic-counter insert path, all-slots-merge read.
  At K=1 (the default) it must remain bit-identical to this reference.
- `ReSTIRDIReferencePass` (this) is **strictly frozen** at the current
  algorithm. No further mechanical refactors touch it. Cleanup commits
  from earlier in this session that touched both passes in parallel
  (4f78aee, 4b32125, 695282e and earlier) were the last syncs; from
  this point onward, only the active pass evolves.

Parity validation across K-slot rollout:

| K-slot sub-step | Parity check against this pass |
|---|---|
| K=1 cbuffer field added | bit-identical rmse on RDI00 |
| K=1 atomic-counter insert (gated) | bit-identical rmse on RDI00 |
| K=1 in-cell merge (gated, reads slot[0]) | bit-identical rmse on RDI00 |
| K>1 variants | new algorithm, parity not expected (new ladder steps) |

If at any step `ReSTIRDIPass` at K=1 drifts from this reference's
rmse beyond the RNG noise floor (~0.2%), the K-slot evolution has
introduced a regression. Fix before proceeding.

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

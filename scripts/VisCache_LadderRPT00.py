"""
VisCache_LadderRPT00.py — ReSTIRPT scratch / iteration step.

Step 00 (Ladder00) is the canonical home for ALL references — vanilla,
vanilla_b{N}, restirpt_b{N} (ReSTIR mode), restirpt_bpr_b{N} (BPR mode),
plus the DI-side variants. Run step 00 to populate the canonical reference
matrix.

RPT00 is intentionally empty. It exists as a placeholder for ad-hoc ReSTIRPT
iteration runs (config sweeps, ablations) that don't belong in the canonical
step 00. When you need to sweep a knob:

    1. Copy this file to VisCache_LadderRPT01.py (or similar)
    2. Add the variant calls there
    3. Reference step 00's GTs implicitly via _resolve_gt_for_variant

Example: VisCache_LadderRPT01.py sweeps `fireflyClampK`.

Usage:
    runtime/pythondist/python.exe scripts/run_ladder.py -s 00     # canonical refs
"""
_HEADLESS_SCRIPT_DONE = True

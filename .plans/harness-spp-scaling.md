# Harness-Side SPP-Scaling Helpers — Design Note

**Status:** Filed, not implemented. stderr=0.10 supersedes the need for SPP-scaling in normal use; this is shelved for the specific case of legacy-gate comparison sweeps.

## Why this isn't built

stderr=`√(var/N) ≤ τ` is per-cell sample-count-aware by construction. ALL_STDERR (2026-05-06) confirmed `stderrThreshold = 0.10` as a strict Pareto improvement over the per-SPP vt carry table on 7 scenes. With stderr canonical, the harness doesn't need to compensate for vt being SPP-blind — the gate handles it natively.

The earlier algorithm-internal SPP-scaling implementation was reverted on the same day after the user clarified the architecture: `gSpp = mStaticParams.samplesPerPixel = 1` always (frame-accumulation mode), so scaling the slang-side cbuffer was structurally meaningless. Once that constraint was clear, two paths existed: (1) move scaling Python-side where the test's virtual SPP is known; (2) drop scaling entirely. The data made (2) the right call.

## Why we'd ever build this

A future sweep that compares **gate formulations** at fixed quality across SPPs:
- stderr=0.10 vs vt=? at x4 — per SPONZA_VT, x4 wants vt≈0.10
- stderr=0.10 vs vt=? at x16 — per SPONZA_VT, x16 wants vt≈0.001

To compare apples-to-apples, the legacy vt arm needs to use its per-SPP optimum, not a static value. Without harness-side scaling we'd hand-write two configs per SPP. With it we have one base value × scaling exponent.

This is research-comparison territory, not canonical use. We may need it once if reviewers ask for "stderr-vs-vt under fairly-tuned vt" — otherwise no.

## Implementation sketch

5–10 LOC in `scripts/VisCache_LadderCommon.py`:

```python
# Calibration empirically anchored at refSpp=4 from SPONZA_CT/VT 2026-05-06.
SPP_REF = 4

def spp_scaled_vt(vt_base, spp, *, k=3.32, spp_ref=SPP_REF):
    """Scale varThreshold for fair comparison across SPPs.

    vt(refSpp=4) = vt_base; vt(spp=16) ≈ vt_base / 100 with k=3.32.

    Calibration source: SPONZA_VT 2026-05-06 (vt=0.10 at x4, vt=0.001 at x16
    on Sponza ct=8 cell4×4 bayer2×2). For other base configs the calibration
    may differ; treat k as a per-config tuning knob.
    """
    return vt_base * (spp_ref / max(spp, 1)) ** k


def spp_scaled_ct(ct_base, spp, *, k=1.5, spp_ref=SPP_REF):
    """Scale bootThreshold for fair comparison across SPPs.

    ct(refSpp=4) = ct_base; ct(spp=16) ≈ ct_base * 8 with k=1.5.

    Calibration source: SPONZA_CT 2026-05-06 (ct=8 knee at x4,
    ct=64 monotonic-best at x16 on Sponza ct-canonical).
    """
    return max(1, round(ct_base * (max(spp, 1) / spp_ref) ** k))
```

Usage in a comparison sweep:

```python
for spp in [4, 16]:
    variants.append((f"vt_scaled_spp{spp}", {
        ...
        "varThreshold":   spp_scaled_vt(0.10, spp),
        "bootThreshold":  spp_scaled_ct(8, spp),
        "stderrThreshold": 0.0,   # legacy vt path
    }))
    variants.append((f"stderr_010_spp{spp}", {
        ...
        "stderrThreshold": 0.10,  # canonical
    }))
```

Run at MF_CONFIGS = [(0,0,4,1), (0,0,16,1)] — but only emit (variant, spp) pairs where the variant's tag matches the spp.

(That last constraint is the awkward part — `run_variants` renders every variant at every SPP. Either filter post-hoc in analysis, or extend `run_variants` to accept a per-variant SPP whitelist. Decide when implementing.)

## When to implement

Trigger conditions (any one):
1. Reviewer / paper §13 requests fair gate-vs-gate comparison across SPPs with legacy vt at its per-SPP optimum.
2. We discover a regime where stderr underperforms a hand-tuned vt — at that point we'd want both approaches in the harness for diff testing.
3. Someone outside the project wants to reproduce the SPONZA_VT result and needs the calibration formulas as runnable Python rather than buried CSV cells.

Otherwise skip.

## Estimated effort

- Helpers: ~10 LOC, ~5 min.
- Run-variants per-SPP whitelist (if needed): ~30 min.
- Sweep + analysis if a fair comparison is requested: ~1 hour.

**Total: 5 min – 1.5 hours** depending on scope.

## Why this lives in `.plans/` and not in the code

Adding the helpers without a concrete use case is engineering-on-spec — fine practice but pure code-debt accumulation against an uncertain need. stderr=0.10 is the production answer; vt-based comparison is a research footnote we may or may not need to write. File the design, build only if the trigger fires.

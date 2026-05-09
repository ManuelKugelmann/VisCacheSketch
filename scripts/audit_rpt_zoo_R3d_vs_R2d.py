"""
audit_rpt_zoo_R3d_vs_R2d.py — R3d vs R2d audit on ReSTIRPT zoo data.

Mirrors the parallel agent's RDI00 R3d audit (37d9b3d) on PT side:
"is R3d's win driven by one outlier scene or is it consistent across
the matrix?" Reads `runtime/captures/ladder/RPT_ZOO/stats.csv` and
emits per-scene + cumulative deltas of mean_err_pct between R3d /
R2dR3d / vanilla and R2d-baseline.

Usage:
  runtime/pythondist/python.exe scripts/audit_rpt_zoo_R3d_vs_R2d.py [SPP] [--md]

  SPP defaults to 16 (the canonical comparison point); pass 1 / 4 to
  audit the cold-cell or mid-converged regimes instead.
  --md emits a markdown table for direct LADDERLOG paste-in.

Output (default text mode):
  - Per-scene table: vanilla / R2d / R2dR3d / R3d err%
  - d(R3d - R2d), d(R3d - vanilla), d(R2dR3d - vanilla)
  - Per-scene relative-to-vanilla %
  - Cumulative sums + outlier flag (share > 50% of cum |d|)
"""
import os, sys, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV  = os.path.join(ROOT, "runtime", "captures", "ladder", "RPT_ZOO", "stats.csv")
# Vanilla rows live in step 00, not the ZOO step. Load both.
CSV_GT = os.path.join(ROOT, "runtime", "captures", "ladder", "00", "stats.csv")

_args = [a for a in sys.argv[1:] if a]
MD = "--md" in _args
ALL_SPP = "--all" in _args
_spp_args = [a for a in _args if a not in ("--md", "--all")]
SPP = int(_spp_args[0]) if _spp_args else 16

if not os.path.exists(CSV):
    sys.exit(f"[audit] no CSV at {CSV} — run RPT_ZOO ladder first")

# rows[(scene, variant, spp)] = mean_err_pct
rows = {}
for csv_path in (CSV, CSV_GT):
    if not os.path.exists(csv_path):
        continue
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                spp_v = int(r["spp"])
                err   = float(r["mean_err_pct"]) if r.get("mean_err_pct") else None
                if err is None:
                    continue
            except (KeyError, ValueError):
                continue
            rows[(r["scene"], r["variant"], spp_v)] = err

scenes = sorted({k[0] for k in rows.keys()})

# Variant tags as written by run_baseline_ReSTIRPT_*: "restirpt_R2d_b3" etc.
def get(scene, variant, spp):
    return rows.get((scene, variant, spp))


def emit_audit(spp, md_mode):
    """Emit the audit table for a single SPP. Returns (cum_r3d_r2d, cum_r3d_van, cum_r2d3d_van)."""
    if md_mode:
        print(f"### RPT_ZOO R-axis audit @ SPP={spp}")
        print()
        print(f"| Scene | vanilla | R2d | R2dR3d | R3d | d(R3d-R2d) | R3d/van% | R2dR3d/van% |")
        print(f"| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    else:
        print(f"# RPT_ZOO R3d-vs-R2d audit @ SPP={spp}")
        print(f"# Source: {CSV}")
        print()
        fmt_hdr = f"{'scene':<32} {'vanilla':>9} {'R2d':>9} {'R2dR3d':>9} {'R3d':>9}   {'d R3d-R2d':>10} {'d R3d-van':>10} {'d R2dR3d-van':>13}"
        print(fmt_hdr)
        print("-" * len(fmt_hdr))

    cum_r3d_r2d = 0.0
    cum_r3d_van = 0.0
    cum_r2d3d_van = 0.0
    deltas = []
    for s in scenes:
        van = next((v for tag in ("vanilla_b4", "vanilla", "vanilla_b1", "vanilla_b8")
                    for v in [get(s, tag, spp)] if v is not None), None)
        r2d = next((v for tag in (f"restirpt_R2d_b{b}" for b in (4, 3, 8)) for v in [get(s, tag, spp)] if v is not None), None)
        r2d3d = next((v for tag in (f"restirpt_R2dR3d_b{b}" for b in (4, 3, 8)) for v in [get(s, tag, spp)] if v is not None), None)
        r3d = next((v for tag in (f"restirpt_R3d_b{b}" for b in (4, 3, 8)) for v in [get(s, tag, spp)] if v is not None), None)
        if any(x is None for x in (van, r2d, r2d3d, r3d)):
            miss = [n for n, v in (("van", van), ("R2d", r2d), ("R2dR3d", r2d3d), ("R3d", r3d)) if v is None]
            if md_mode:
                print(f"| {s} | _missing: {','.join(miss)}_ | | | | | | |")
            else:
                print(f"{s:<32}  (missing: {','.join(miss)})")
            continue
        d_r3d_r2d  = r3d - r2d
        d_r3d_van  = r3d - van
        d_r2d3d_van = r2d3d - van
        cum_r3d_r2d += d_r3d_r2d
        cum_r3d_van += d_r3d_van
        cum_r2d3d_van += d_r2d3d_van
        deltas.append((s, d_r3d_r2d, d_r3d_van, d_r2d3d_van))
        if md_mode:
            r3d_pct = 100.0 * (r3d - van) / van if van > 1e-9 else 0.0
            r2d3d_pct = 100.0 * (r2d3d - van) / van if van > 1e-9 else 0.0
            sign = lambda v: f"{v:+.1f}"
            print(f"| {s} | {van:.3f} | {r2d:.3f} | {r2d3d:.3f} | {r3d:.3f} | {d_r3d_r2d:+.3f} | {sign(r3d_pct)}% | {sign(r2d3d_pct)}% |")
        else:
            print(f"{s:<32} {van:>9.5f} {r2d:>9.5f} {r2d3d:>9.5f} {r3d:>9.5f}   {d_r3d_r2d:>+10.5f} {d_r3d_van:>+10.5f} {d_r2d3d_van:>+13.5f}")
    if md_mode:
        print(f"| **CUM** | | | | | **{cum_r3d_r2d:+.3f}** | **{cum_r3d_van:+.3f}pp** | **{cum_r2d3d_van:+.3f}pp** |")
        print()
    else:
        print("-" * len(fmt_hdr))
        print(f"{'CUMULATIVE':<32} {'':>9} {'':>9} {'':>9} {'':>9}   {cum_r3d_r2d:>+10.5f} {cum_r3d_van:>+10.5f} {cum_r2d3d_van:>+13.5f}")
        print()
    if not md_mode and deltas and abs(cum_r3d_r2d) > 1e-9:
        print("# Outlier check (d R3d-R2d):")
        for s, d, _, _ in deltas:
            share = d / cum_r3d_r2d
            flag = "  <- OUTLIER" if abs(share) > 0.5 else ""
            print(f"  {s:<32} share={share:>+6.1%}{flag}")
        print()
    if abs(cum_r3d_r2d) < 0.01:
        verdict = f"R3d ~= R2d at SPP={spp} (|cum d| < 0.01%) - no clear win."
    elif cum_r3d_r2d < 0:
        verdict = f"R3d wins R2d at SPP={spp} by cum d = {cum_r3d_r2d:+.4f}pp."
    else:
        verdict = f"R3d LOSES to R2d at SPP={spp} by cum d = {cum_r3d_r2d:+.4f}pp."
    if md_mode:
        print(f"**Verdict @ SPP={spp}:** {verdict}")
        print()
    else:
        print(f"# Verdict: {verdict}")
    return cum_r3d_r2d, cum_r3d_van, cum_r2d3d_van


if ALL_SPP:
    for s in (1, 4, 16):
        emit_audit(s, MD)
else:
    emit_audit(SPP, MD)

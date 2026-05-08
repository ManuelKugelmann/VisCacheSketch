"""
audit_rpt_zoo_R3d_vs_R2d.py — R3d vs R2d audit on ReSTIRPT zoo data.

Mirrors the parallel agent's RDI00 R3d audit (37d9b3d) on PT side:
"is R3d's win driven by one outlier scene or is it consistent across
the matrix?" Reads `runtime/captures/ladder/RPT_ZOO/stats.csv` and
emits per-scene + cumulative deltas of mean_err_pct between R3d /
R2dR3d / vanilla and R2d-baseline.

Usage:
  runtime/pythondist/python.exe scripts/audit_rpt_zoo_R3d_vs_R2d.py [SPP]

  SPP defaults to 16 (the canonical comparison point); pass 1 / 4 to
  audit the cold-cell or mid-converged regimes instead.

Output:
  - Per-scene table: vanilla / R2d / R2dR3d / R3d err%
  - Δ(R3d − R2d), Δ(R3d − vanilla), Δ(R2dR3d − vanilla)
  - Cumulative sums (uniform + scene-weighted if SCENE_WEIGHTS available)
  - Outlier flag: scene whose |Δ| > 50% of cumulative |Δ|
"""
import os, sys, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV  = os.path.join(ROOT, "runtime", "captures", "ladder", "RPT_ZOO", "stats.csv")

SPP = int(sys.argv[1]) if len(sys.argv) > 1 else 16

if not os.path.exists(CSV):
    sys.exit(f"[audit] no CSV at {CSV} — run RPT_ZOO ladder first")

# rows[(scene, variant, spp)] = mean_err_pct
rows = {}
with open(CSV, newline="") as f:
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

print(f"# RPT_ZOO R3d-vs-R2d audit @ SPP={SPP}")
print(f"# Source: {CSV}")
print()
fmt_hdr = f"{'scene':<32} {'vanilla':>9} {'R2d':>9} {'R2dR3d':>9} {'R3d':>9}   {'Δ R3d-R2d':>10} {'Δ R3d-van':>10} {'Δ R2dR3d-van':>13}"
print(fmt_hdr)
print("-" * len(fmt_hdr))

cum_r3d_r2d = 0.0
cum_r3d_van = 0.0
cum_r2d3d_van = 0.0
deltas_per_scene = []

for s in scenes:
    van = get(s, "vanilla", SPP)
    r2d = get(s, "restirpt_R2d_b3", SPP)
    r2d3d = get(s, "restirpt_R2dR3d_b3", SPP)
    r3d = get(s, "restirpt_R3d_b3", SPP)
    if any(x is None for x in (van, r2d, r2d3d, r3d)):
        miss = [n for n, v in (("van", van), ("R2d", r2d), ("R2dR3d", r2d3d), ("R3d", r3d)) if v is None]
        print(f"{s:<32}  (missing: {','.join(miss)})")
        continue

    d_r3d_r2d  = r3d - r2d
    d_r3d_van  = r3d - van
    d_r2d3d_van = r2d3d - van
    cum_r3d_r2d += d_r3d_r2d
    cum_r3d_van += d_r3d_van
    cum_r2d3d_van += d_r2d3d_van
    deltas_per_scene.append((s, d_r3d_r2d, d_r3d_van, d_r2d3d_van))
    print(f"{s:<32} {van:>9.5f} {r2d:>9.5f} {r2d3d:>9.5f} {r3d:>9.5f}   {d_r3d_r2d:>+10.5f} {d_r3d_van:>+10.5f} {d_r2d3d_van:>+13.5f}")

print("-" * len(fmt_hdr))
print(f"{'CUMULATIVE':<32} {'':>9} {'':>9} {'':>9} {'':>9}   {cum_r3d_r2d:>+10.5f} {cum_r3d_van:>+10.5f} {cum_r2d3d_van:>+13.5f}")
print()

# Outlier detection: any scene whose |Δ R3d-R2d| > 50% of |cum|.
if deltas_per_scene and abs(cum_r3d_r2d) > 1e-9:
    print("# Outlier check (Δ R3d-R2d):")
    for s, d, _, _ in deltas_per_scene:
        share = d / cum_r3d_r2d
        flag = "  ← OUTLIER" if abs(share) > 0.5 else ""
        print(f"  {s:<32} share={share:>+6.1%}{flag}")
print()

# Verdict
if abs(cum_r3d_r2d) < 0.01:
    print(f"# Verdict: R3d ≈ R2d at SPP={SPP} (|cum Δ| < 0.01%) — no clear win.")
elif cum_r3d_r2d < 0:
    print(f"# Verdict: R3d wins R2d at SPP={SPP} by cum Δ = {cum_r3d_r2d:+.4f}%.")
else:
    print(f"# Verdict: R3d LOSES to R2d at SPP={SPP} by cum Δ = {cum_r3d_r2d:+.4f}%.")

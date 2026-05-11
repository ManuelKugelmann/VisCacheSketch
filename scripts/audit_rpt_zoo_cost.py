"""
audit_rpt_zoo_cost.py - quality vs cost analysis for the R-axis variants.

Reads gpu_total_ms from runtime/captures/ladder/RPT_ZOO/stats.csv +
mean_err_pct, and emits per-scene cost ratios + quality-per-ms metrics.

Helps answer:
  - Does R3d's quality win come at a compute cost premium or savings?
  - Is the R2dR3d hybrid the sweet spot (cell + pixel-fallback)?
  - Where does the R3d pure-3D mode buy back its bias tax?

Note: gpu_total_ms includes setup + warmup overhead in the ladder
runner (~3 min/frame on Cornell). Absolute values are not real-time-
relevant; RELATIVE ratios (variant-vs-variant on the same scene) are
the useful signal.

Pure-Python tool; no shader paths touched.
"""
import os, sys, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV  = os.path.join(ROOT, "runtime", "captures", "ladder", "RPT_ZOO", "stats.csv")
SPP  = int(sys.argv[1]) if len(sys.argv) > 1 else 16


def load_rows():
    rows = {}
    if not os.path.exists(CSV):
        sys.exit(f"[cost] {CSV} missing")
    with open(CSV, newline="") as f:
        for r in csv.DictReader(f):
            try:
                spp = int(r["spp"])
                err = float(r["mean_err_pct"]) if r.get("mean_err_pct") else None
                ms  = float(r["gpu_total_ms"]) if r.get("gpu_total_ms") else None
            except (KeyError, ValueError):
                continue
            if err is None or ms is None:
                continue
            rows[(r["scene"], r["variant"], spp)] = (err, ms)
    return rows


def get_first(rows, scene, tags, spp):
    for t in tags:
        v = rows.get((scene, t, spp))
        if v is not None:
            return v
    return None


def main():
    rows = load_rows()
    scenes = sorted({k[0] for k in rows.keys()})

    print(f"# RPT_ZOO cost audit @ SPP={SPP}  (gpu_total_ms; ladder run includes warmup overhead)")
    print()
    fmt_hdr = f"{'scene':<28} {'R2d err':>8} {'R2d ms':>10}  {'R2dR3d err':>11} {'R2dR3d ms':>11} {'R2dR3d/R2d':>11}  {'R3d err':>9} {'R3d ms':>10} {'R3d/R2d':>9}"
    print(fmt_hdr)
    print("-" * len(fmt_hdr))

    cum_r3d_speedup = 0.0
    cum_r2d3d_speedup = 0.0
    n = 0
    for s in scenes:
        r2d  = get_first(rows, s, ("restirpt_R2d_b4", "restirpt_R2d_b3"), SPP)
        r2d3 = get_first(rows, s, ("restirpt_R2dR3d_b4", "restirpt_R2dR3d_b3"), SPP)
        r3d  = get_first(rows, s, ("restirpt_R3d_b4", "restirpt_R3d_b3"), SPP)
        if not (r2d and r2d3 and r3d):
            print(f"{s:<28}  (incomplete data)")
            continue
        r2d_err, r2d_ms = r2d
        r2d3_err, r2d3_ms = r2d3
        r3d_err, r3d_ms = r3d
        if r2d_ms <= 0:
            print(f"{s:<28}  (R2d ms invalid)")
            continue
        r2d3_ratio = r2d3_ms / r2d_ms
        r3d_ratio  = r3d_ms / r2d_ms
        cum_r3d_speedup   += r3d_ratio
        cum_r2d3d_speedup += r2d3_ratio
        n += 1
        print(f"{s:<28} {r2d_err:>8.3f} {r2d_ms:>10.1f}  {r2d3_err:>11.3f} {r2d3_ms:>11.1f} {r2d3_ratio:>10.3f}x  {r3d_err:>9.3f} {r3d_ms:>10.1f} {r3d_ratio:>8.3f}x")

    if n > 0:
        print("-" * len(fmt_hdr))
        mean_r2d3 = cum_r2d3d_speedup / n
        mean_r3d  = cum_r3d_speedup / n
        print(f"{'mean ratios':<28} {'':>8} {'':>10}  {'':>11} {'':>11} {mean_r2d3:>10.3f}x  {'':>9} {'':>10} {mean_r3d:>8.3f}x")
        print()
        print(f"# {n} scenes averaged.")
        print(f"# R2dR3d cost ratio vs R2d (mean): {mean_r2d3:.3f}x  ({'+' if mean_r2d3 > 1 else ''}{(mean_r2d3 - 1) * 100:.1f}% overhead)")
        print(f"# R3d    cost ratio vs R2d (mean): {mean_r3d:.3f}x  ({'+' if mean_r3d > 1 else ''}{(mean_r3d - 1) * 100:.1f}% overhead)")
        if mean_r3d < 1.0:
            print(f"# R3d is FASTER than R2d on average ({(1.0 - mean_r3d) * 100:.1f}% speedup) — pixel-buffer writes dropped, cell-pool only.")
        elif mean_r3d > 1.0:
            print(f"# R3d is slower than R2d on average — cell-pool atomic-CAS overhead exceeds pixel-write savings.")


if __name__ == "__main__":
    main()

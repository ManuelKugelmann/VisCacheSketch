"""
make_spp_convergence_plot.py - SPP-convergence line plot per scene.

Shows how vanilla / R2d / R2dR3d / R3d converge across SPP={1,4,16}
in OkLab mean_err_pct. Reads RPT_ZOO + step 00 CSVs.

The plot makes the cross-SPP story visible at a glance:
- Cornell scenes: vanilla converges fastest (steepest slope), ReSTIR
  variants flatten quickly (own bias floor).
- Sponza / BistroInterior: vanilla converges normally, R2d FAILS TO
  CONVERGE (error climbs as SPP grows because DQLin's per-pixel
  reservoir accumulates fireflies). R3d converges similarly to vanilla.

Output: docs/devlog/plates/spp_convergence.png

Pure-Python tool; no shader paths touched.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV  = os.path.join(ROOT, "runtime", "captures", "ladder", "RPT_ZOO", "stats.csv")
CSV_GT = os.path.join(ROOT, "runtime", "captures", "ladder", "00", "stats.csv")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit("[spp-plot] matplotlib missing")


def load_rows():
    rows = {}
    for p in (CSV, CSV_GT):
        if not os.path.exists(p):
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    spp = int(r["spp"])
                    err = float(r["mean_err_pct"]) if r.get("mean_err_pct") else None
                except (KeyError, ValueError):
                    continue
                if err is None:
                    continue
                rows[(r["scene"], r["variant"], spp)] = err
    return rows


def get(rows, scene, variant_tags, spp):
    """Try each tag in order; return first hit."""
    for t in variant_tags:
        v = rows.get((scene, t, spp))
        if v is not None:
            return v
    return None


def main():
    rows = load_rows()
    if not rows:
        sys.exit(f"[spp-plot] no rows in {CSV} or {CSV_GT}")

    scenes = sorted({k[0] for k in rows.keys()})
    spps = [1, 4, 16]

    fig, axes = plt.subplots(2, 4, figsize=(16, 7), squeeze=False)
    axes = axes.flatten()
    colors = {"vanilla": "#444", "R2d": "#1f77b4", "R2dR3d": "#2ca02c", "R3d": "#d62728"}

    for i, scene in enumerate(scenes):
        if i >= len(axes):
            break
        ax = axes[i]
        for label, tags in [
            ("vanilla", ("vanilla_b4", "vanilla", "vanilla_b1")),
            ("R2d",     ("restirpt_R2d_b4", "restirpt_R2d_b3")),
            ("R2dR3d",  ("restirpt_R2dR3d_b4", "restirpt_R2dR3d_b3")),
            ("R3d",     ("restirpt_R3d_b4", "restirpt_R3d_b3")),
        ]:
            xs, ys = [], []
            for spp in spps:
                v = get(rows, scene, tags, spp)
                if v is not None:
                    xs.append(spp)
                    ys.append(v)
            if xs:
                ax.plot(xs, ys, marker="o", color=colors[label], label=label, linewidth=2)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(spps)
        ax.set_xticklabels([str(s) for s in spps])
        ax.set_xlabel("SPP")
        ax.set_ylabel("mean_err_pct (OkLab, log)")
        ax.set_title(scene, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="best")

    # Hide unused axes.
    for j in range(len(scenes), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("RPT_ZOO SPP convergence — vanilla vs R2d/R2dR3d/R3d (b=4, OkLab%)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(ROOT, "docs", "devlog", "plates", "spp_convergence.png")
    fig.savefig(out, dpi=120)
    print(f"[spp-plot] wrote {out}")


if __name__ == "__main__":
    main()

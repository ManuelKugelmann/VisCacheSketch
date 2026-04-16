"""
VisCache_Progression.py — ladder-wide progression plot.

For every step with captured stats, picks the *best* variant per
(scene, SPP) — criterion: lowest `rays_traced_pct` (most saved rays).
Plots those winners across steps as a 3-panel stacked figure:

  rays traced %        ← proves each step reaches lower rays
  error Δ %            ← proves we didn't trade quality for it
  noise Δ %            ← complementary screen-space metric

X axis is step index; one colored series per scene × SPP (solid = x1,
dashed = x4). Step 00 is skipped (vanilla baseline has no variant to
pick). Output: `captures/ladder/overview_progression.png`, also mirrored
into `captures/ladder/overview_progression_summary.png` for doclinks.

Usage:
    runtime/pythondist/python.exe scripts/VisCache_Progression.py
"""
import os
import csv
import sys
import glob


# Progression shows only the two primary SPPs so every step has comparable
# endpoints — higher SPPs appear only in the sample-count sweep (step 04).
PROGRESSION_SPPS = (1, 4)


def _gather_winners(ladder_root):
    """Return {step: {(scene, spp): row}} with row picked by lowest rays,
    restricted to SPPs in PROGRESSION_SPPS."""
    out = {}
    for csv_path in sorted(glob.glob(os.path.join(ladder_root, "*", "stats.csv"))):
        step = os.path.basename(os.path.dirname(csv_path))
        if not step.isdigit():
            continue
        if step == "00":
            continue  # vanilla — no variants to pick
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        winners = {}
        for r in rows:
            scene = r.get("scene")
            try:
                spp = int(r.get("spp") or 0)
                rays = float(r.get("rays_traced_pct") or 0.0)
            except (TypeError, ValueError):
                continue
            if spp not in PROGRESSION_SPPS:
                continue
            key = (scene, spp)
            cur = winners.get(key)
            if cur is None or rays < float(cur["rays_traced_pct"]):
                winners[key] = r
        if winners:
            out[step] = winners
    return out


def _float(row, key):
    v = row.get(key)
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def plot_progression(ladder_root="captures/ladder",
                     out_path="captures/ladder/overview_progression.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    winners = _gather_winners(ladder_root)
    if not winners:
        print(f"[progression] no stats under {ladder_root}")
        return None

    steps     = sorted(winners.keys())
    scenes    = sorted({scene for w in winners.values() for (scene, _) in w})
    spps      = sorted({spp   for w in winners.values() for (_, spp) in w})

    # Per-scene hue + marker (shape stays consistent across SPPs so the
    # scene's point cloud reads as one object); SPP encoded only by size +
    # darkness (small/light = x1, larger/darker = x4). Line style marks SPP
    # too (solid = x1, dashed = x4) so intertwined lines stay legible.
    palette       = plt.cm.tab10.colors
    scene_markers = ("o", "s", "D", "^", "v", "P", "X", "*")
    scene_c       = {s: palette[i % len(palette)]       for i, s in enumerate(scenes)}
    scene_m       = {s: scene_markers[i % len(scene_markers)] for i, s in enumerate(scenes)}

    def _size_for_spp(spp):
        import math
        idx = max(0, int(math.log2(max(spp, 1))))
        return 40 + idx * 14  # x1→40, x2→54, x4→68, x8→82, x16→96

    def _darken(color, spp):
        import math
        idx = max(0, int(math.log2(max(spp, 1))))
        f = min(0.6, 0.15 * idx)
        return (color[0] * (1 - f), color[1] * (1 - f), color[2] * (1 - f))

    ls_for = lambda spp: "-" if spp == 1 else "--"

    metrics = [
        ("rays_traced_pct",   "rays traced %",  (0, 105)),
        ("error_delta_pct",   "error Δ %",      None),
        ("noise_delta_pct",   "noise Δ %",      None),
    ]

    fig, axes = plt.subplots(3, 1, figsize=(max(9, 0.7 * len(steps) + 4), 10),
                             sharex=True, constrained_layout=True)
    for ax, (key, ylabel, ylim) in zip(axes, metrics):
        for scene in scenes:
            for spp in spps:
                xs, ys = [], []
                for i, step in enumerate(steps):
                    row = winners[step].get((scene, spp))
                    if row is None:
                        continue
                    v = _float(row, key)
                    if v is None:
                        continue
                    xs.append(i)
                    ys.append(v)
                if xs:
                    dark = _darken(scene_c[scene], spp)
                    # Connecting line (edge-dark, thin) — then the markers on top
                    # so size/darkness dominates the visual weight.
                    ax.plot(xs, ys, ls=ls_for(spp), color=dark,
                            linewidth=1.2, alpha=0.75, zorder=2)
                    ax.scatter(xs, ys, marker=scene_m[scene],
                               s=_size_for_spp(spp), c=[dark],
                               edgecolors=dark, linewidths=0.8,
                               zorder=3, label=f"{scene} x{spp}")
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)
        if ylim:
            ax.set_ylim(*ylim)
        if key.endswith("_delta_pct"):
            ax.axhline(0, color="black", linewidth=0.5, alpha=0.4)

    axes[-1].set_xticks(list(range(len(steps))))
    axes[-1].set_xticklabels([f"step {s}" for s in steps], rotation=45, ha="right")
    axes[0].set_title("Ladder progression — best (lowest-rays) variant per step, scene, SPP")
    axes[0].legend(loc="center left", bbox_to_anchor=(1.01, 0.5),
                   fontsize=8, frameon=True)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[progression] -> {out_path}")

    summary_path = os.path.join(ladder_root, "overview_progression_summary.png")
    import shutil
    shutil.copy2(out_path, summary_path)
    print(f"[progression] -> {summary_path}")
    return out_path


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # Resolve relative to runtime/ where Mogwai CWD is; run_ladder.py does the same.
    root = os.environ.get("LADDER_ROOT", "captures/ladder")
    plot_progression(ladder_root=root,
                     out_path=os.path.join(root, "overview_progression.png"))

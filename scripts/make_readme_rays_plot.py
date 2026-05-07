"""Generate the README headline plot: rays_traced_pct across scenes × bounce depths.

Reads canonical numbers from the relevant ladder CSVs (CORNELL_MB,
SPONZA_MB, BISTRO_MB) and produces docs/rays_saved_matrix.png — a
grouped-bar chart showing the cache's algorithmic rays-saved story
across the 7-scene matrix at b ∈ {0, 1, 4}.

Run:
    runtime/pythondist/python.exe scripts/make_readme_rays_plot.py
"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_csv(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path)))


def find(rows, scene_match, variant_contains, spp=4):
    for r in rows:
        if scene_match in r.get("scene", "") \
           and variant_contains in r.get("variant", "") \
           and int(r.get("spp", 0)) == spp:
            return float(r.get("rays_traced_pct", "100"))
    return None


# Scenes in order, with display labels
SCENES = [
    ("CornellBox_1PointLight",   "C_1PL"),
    ("CornellBox_1AreaLight",    "C_1AL"),
    ("CornellBox_3AreaLights",   "C_3AL"),
    ("CornellBox_32PointLights", "C_32PL"),
    ("Sponza",                   "Sponza"),
    ("BistroInterior",           "BistroInt"),
    ("BistroExterior",           "BistroExt"),
]

cornell_mb = load_csv(os.path.join(ROOT, "runtime/captures/ladder/CORNELL_MB/stats.csv"))
sponza_mb  = load_csv(os.path.join(ROOT, "runtime/captures/ladder/SPONZA_MB/stats.csv"))
bistro_mb  = load_csv(os.path.join(ROOT, "runtime/captures/ladder/BISTRO_MB/stats.csv"))

# Data for the grouped bar chart: one row per bounce depth, one entry per scene
data = {0: [], 1: [], 4: []}
for scene_key, _label in SCENES:
    if scene_key.startswith("CornellBox"):
        rows = cornell_mb
    elif scene_key == "Sponza":
        rows = sponza_mb
    else:
        rows = bistro_mb
    for b in (0, 1, 4):
        if scene_key == "Sponza":
            v = find(rows, scene_key, f"viscache_canonical_vt010_b{b}")
            if v is None:
                v = find(rows, scene_key, f"viscache_canonical_vt001_b{b}")
        else:
            v = find(rows, scene_key, f"viscache_canonical_b{b}")
        data[b].append(v if v is not None else float("nan"))

labels = [lbl for _, lbl in SCENES]
x = np.arange(len(labels))
width = 0.27

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.set_facecolor("#fafafa")

# Bounce-depth bars: lighter shade for b=0, darker for b=4
colors = {0: "#9bb0c8", 1: "#5074a8", 4: "#243f6b"}
for i, b in enumerate((0, 1, 4)):
    offset = (i - 1) * width
    vals = data[b]
    bars = ax.bar(x + offset, vals, width, label=f"b = {b}", color=colors[b],
                  edgecolor="white", linewidth=0.6)
    for bar, v in zip(bars, vals):
        if not np.isnan(v):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1.2,
                    f"{v:.0f}", ha="center", va="bottom", fontsize=7.5,
                    color="#333")

# Vanilla reference line at 100%
ax.axhline(100, color="#a04040", linewidth=1.2, linestyle="--", alpha=0.7)
ax.text(0.0, 102, "vanilla (no cache) = 100%", ha="left", va="bottom",
        fontsize=8, color="#a04040", style="italic")

ax.set_ylim(0, 115)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("Shadow rays traced (% of vanilla)", fontsize=10)
ax.set_title("Cache rays_traced_pct across scenes × bounce depth (lower = more rays saved)",
             fontsize=11, pad=12)
ax.legend(loc="lower right", title="Bounce depth", fontsize=9, title_fontsize=9,
          framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.yaxis.grid(True, linestyle=":", alpha=0.4)
ax.set_axisbelow(True)

# Annotate headline savings — pick endpoints: best win + Sponza b=4
ax.annotate("94% rays saved\n(C_1PL, b=4)",
            xy=(0 + width, data[4][0]),
            xytext=(0.4, 30),
            fontsize=8, ha="left",
            arrowprops=dict(arrowstyle="->", color="#333", lw=0.7))
ax.annotate("74% rays saved\n(Sponza, b=4)\nSPONZA_MB8 asymptote ~76%",
            xy=(4 + width, data[4][4]),
            xytext=(5.4, 75),
            fontsize=8, ha="left",
            arrowprops=dict(arrowstyle="->", color="#333", lw=0.7))

plt.tight_layout()
out_path = os.path.join(ROOT, "docs/rays_saved_matrix.png")
fig.savefig(out_path, dpi=130, bbox_inches="tight")
print(f"Wrote {out_path}")

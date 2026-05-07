"""Generate the README RTXDI-parity comparison plot.

Per-scene OkLab perceptual error at x4 SPP for vanilla / RTXDI /
restir_2d (ours) / restir_3d (ours, world-space). Shows the 6/7-scene
quality wins over RTXDI and the 2D/3D structural-equivalence claim.

Numbers from devlog/DEVLOG.md "RTXDI Baseline — Final Result" + paper §13.5.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (scene_label, vanilla, rtxdi, restir_2d, restir_3d) — OkLab err% vs x4096 GT
DATA = [
    ("C_1AL",     1.39, 2.18, 2.15, 2.16),
    ("C_1PL",     0.21, 1.39, 0.21, 0.21),
    ("C_3AL",     2.97, 2.60, 3.55, 3.55),
    ("C_32PL",    5.36, 3.73, 3.31, 3.31),
    ("Sponza",    6.23, 7.08, 6.49, 6.47),
    ("BistroInt", 16.96, 10.73, 9.54, 9.53),
    ("BistroExt", 18.12, 13.23, 10.88, 10.85),
]

labels = [d[0] for d in DATA]
vanilla   = [d[1] for d in DATA]
rtxdi     = [d[2] for d in DATA]
restir_2d = [d[3] for d in DATA]
restir_3d = [d[4] for d in DATA]

x = np.arange(len(labels))
width = 0.20

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.set_facecolor("#fafafa")

bars_v   = ax.bar(x - 1.5 * width, vanilla,   width, label="vanilla",
                  color="#999999", edgecolor="white", linewidth=0.6)
bars_r   = ax.bar(x - 0.5 * width, rtxdi,     width, label="RTXDI (NVIDIA)",
                  color="#76b900", edgecolor="white", linewidth=0.6)
bars_2d  = ax.bar(x + 0.5 * width, restir_2d, width, label="restir_2d (ours)",
                  color="#3a6fa3", edgecolor="white", linewidth=0.6)
bars_3d  = ax.bar(x + 1.5 * width, restir_3d, width, label="restir_3d (ours)",
                  color="#1c3d5e", edgecolor="white", linewidth=0.6)

# Numeric labels
for bars in (bars_v, bars_r, bars_2d, bars_3d):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + 0.25,
                f"{h:.2f}", ha="center", va="bottom", fontsize=7,
                color="#333")

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("Mean OkLab error % vs x4096 GT (lower is better)", fontsize=10)
ax.set_title("Quality at x4 SPP: vanilla vs RTXDI vs ours (6 of 7 scenes win, cumulative −4.81pp ahead)",
             fontsize=11, pad=12)
ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.yaxis.grid(True, linestyle=":", alpha=0.4)
ax.set_axisbelow(True)
ax.set_ylim(0, max(vanilla) * 1.15)

plt.tight_layout()
out_path = os.path.join(ROOT, "docs/rtxdi_parity.png")
fig.savefig(out_path, dpi=130, bbox_inches="tight")
print(f"Wrote {out_path}")

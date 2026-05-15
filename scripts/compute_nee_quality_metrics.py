"""
compute_nee_quality_metrics.py — post-processing for compare_nee_quality.py.

Loads the 4 EXRs captured by compare_nee_quality.py, computes the standard
metric battery vs the GT, prints a comparison table.

Run from project root:
    runtime/pythondist/python.exe scripts/compute_nee_quality_metrics.py [scene_name]
"""

import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viscache_exr import compute_research_metrics_hdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = sys.argv[1] if len(sys.argv) > 1 else "CornellBox_32PointLights"
CAP_DIR = os.path.join(ROOT, "runtime", "captures", "nee_quality", SCENE)


def find_exr(prefix):
    matches = glob.glob(os.path.join(CAP_DIR, f"{prefix}.AccumulatePass.output.*.exr"))
    return sorted(matches)[-1] if matches else None


def main():
    gt_matches = sorted(glob.glob(os.path.join(CAP_DIR, "gt_x*.AccumulatePass.output.*.exr")))
    if not gt_matches:
        print(f"[ERROR] no GT EXR in {CAP_DIR}", file=sys.stderr)
        sys.exit(1)
    gt = gt_matches[-1]
    print(f"[gt] {os.path.basename(gt)}")

    variants = [("vanilla", "vanilla_x4"),
                ("restirdi", "restirdi_x4"),
                ("restirnee_K16", "restirnee_x4")]

    print(f"\n=== quality comparison @ x4 SPP vs GT@x1024 — scene={SCENE} ===")
    cols = ["variant", "rmse", "psnr_db", "relmse", "smape", "ms_ssim", "flip"]
    header = " | ".join(f"{c:>13}" for c in cols)
    print(header)
    print("-" * len(header))

    rows = []
    for label, prefix in variants:
        path = find_exr(prefix)
        if not path:
            print(f"  [skip] {label}: no EXR found")
            continue
        m = compute_research_metrics_hdr(path, gt)
        if not m:
            print(f"  [skip] {label}: metric computation failed")
            continue
        rows.append((label, m))
        row = [label] + [f"{m.get(k, float('nan')):.5f}" for k in cols[1:]]
        print(" | ".join(f"{v:>13}" for v in row))

    # Comparison commentary
    if len(rows) >= 2:
        print()
        vanilla = next((m for n, m in rows if n == "vanilla"), None)
        for name, m in rows:
            if name == "vanilla" or vanilla is None:
                continue
            for k in ("rmse", "psnr_db", "relmse", "ms_ssim", "flip"):
                if vanilla.get(k) is None or m.get(k) is None:
                    continue
                delta = m[k] - vanilla[k]
                better = (delta < 0) if k != "psnr_db" and k != "ms_ssim" else (delta > 0)
                arrow = "DN" if (k != "psnr_db" and k != "ms_ssim") else "UP"
                sign = "+" if delta >= 0 else ""
                tag = "BETTER" if better else "WORSE "
                print(f"  {name} vs vanilla: {k:>10} {tag} ({sign}{delta:.5f}, want {arrow})")


if __name__ == "__main__":
    main()

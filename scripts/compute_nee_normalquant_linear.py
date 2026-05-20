"""Linear-HDR metrics for compare_nee_normalquant.py captures."""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_exr import compute_research_metrics_hdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = sys.argv[1] if len(sys.argv) > 1 else "CornellBox_32PointLights"
CELL_FP = int(sys.argv[2] if len(sys.argv) > 2 else 1)
CAP_DIR = os.path.join(ROOT, "runtime", "captures", "nee_normalquant", SCENE)


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

    variants = [("nee_F16", "nee_F16_x4")]
    for nq in (60, 45):
        for K, lo in [(1, 0), (4, 0), (4, 1)]:
            variants.append((f"nq{nq}_K{K}lo{lo}",
                             f"nee_F16R3d_nq{nq}_K{K}lo{lo}_fp{CELL_FP}_x4"))

    print(f"\n=== NEE normalACoarse 45° vs 60° × K-slot @ x4 SPP — scene={SCENE} fp={CELL_FP} ===")
    cols = ["variant", "rmse", "psnr_db", "relmse", "ms_ssim", "flip"]
    header = " | ".join(f"{c:>15}" for c in cols)
    print(header)
    print("-" * len(header))
    for label, prefix in variants:
        path = find_exr(prefix)
        if not path:
            print(f"  [skip] {label}: no EXR ({prefix})")
            continue
        m = compute_research_metrics_hdr(path, gt) or {}
        if not m:
            continue
        row = [label]
        for k in cols[1:]:
            v = m.get(k)
            row.append("nan" if v is None else f"{v:.5f}")
        print(" | ".join(f"{v:>15}" for v in row))


if __name__ == "__main__":
    main()

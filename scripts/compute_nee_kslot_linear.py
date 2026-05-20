"""Linear-HDR-only metrics for NEE K-slot captures (OkLab path OOMs at HD)."""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from viscache_exr import compute_research_metrics_hdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = sys.argv[1] if len(sys.argv) > 1 else "CornellBox_32PointLights"
CELL_FP = int(sys.argv[2] if len(sys.argv) > 2 else 1)
SPP_TAG = sys.argv[3] if len(sys.argv) > 3 else "x4"
CAP_DIR = os.path.join(ROOT, "runtime", "captures", "nee_kslot", SCENE)


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

    variants = [("nee_F16", f"nee_F16_{SPP_TAG}")]
    variants += [(f"K{K}lo{lo}_fp{CELL_FP}",
                  f"nee_F16R3d_K{K}lo{lo}_fp{CELL_FP}_{SPP_TAG}")
                 for K in (1, 4, 8) for lo in (0, 1, 2)
                 if not (K == 1 and lo > 0)]

    print(f"\n=== NEE K-slot quality @ {SPP_TAG} SPP vs GT@x1024 — scene={SCENE} fp={CELL_FP} ===")
    cols = ["variant", "rmse", "psnr_db", "relmse", "ms_ssim", "flip"]
    header = " | ".join(f"{c:>13}" for c in cols)
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
        print(" | ".join(f"{v:>13}" for v in row))


if __name__ == "__main__":
    main()

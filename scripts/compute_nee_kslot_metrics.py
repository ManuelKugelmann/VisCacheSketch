"""
compute_nee_kslot_metrics.py — metrics for compare_nee_kslot.py captures.

Parallel of compute_nee_quality_metrics.py but indexes the K-slot variant
naming (nee_F16R3d_K{1,4,8}lo{0,1,2}_fp{N}_x{spp}) and reports full battery.

Usage:
    runtime/pythondist/python.exe scripts/compute_nee_kslot_metrics.py [scene] [fp]
"""
import os, sys, glob, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viscache_exr import compute_research_metrics_hdr, compute_render_error_signed_hdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = sys.argv[1] if len(sys.argv) > 1 else "CornellBox_32PointLights"
CELL_FP = int(sys.argv[2] if len(sys.argv) > 2 else 1)
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

    variants = [("nee_F16",          "nee_F16_x4")]
    variants += [(f"K{K}lo{lo}_fp{CELL_FP}",
                  f"nee_F16R3d_K{K}lo{lo}_fp{CELL_FP}_x4")
                 for K in (1, 4, 8) for lo in (0, 1, 2)
                 if not (K == 1 and lo > 0)]   # K=1 lo>0 not in capture set

    nee_path = find_exr("nee_F16_x4")

    def metrics_for(path):
        m = compute_research_metrics_hdr(path, gt) or {}
        with tempfile.TemporaryDirectory() as td:
            out_png = os.path.join(td, "err.png")
            oklab = compute_render_error_signed_hdr(path, nee_path or path, gt, out_png)
        if oklab:
            m["err_pct"]    = oklab.get("err_delta_pct")
            m["blob_pct"]   = oklab.get("err_delta_blob_pct")
            m["art_3_pct"]  = oklab.get("err_artifact_3_pct")
            m["art_5_pct"]  = oklab.get("err_artifact_5_pct")
            m["art_11_pct"] = oklab.get("err_artifact_11_pct")
        return m

    print(f"\n=== NEE K-slot quality @ x4 SPP vs GT@x1024 — scene={SCENE} fp={CELL_FP} ===")

    cols_linear = ["variant", "rmse", "psnr_db", "relmse", "ms_ssim", "flip"]
    cols_oklab  = ["variant", "err_pct", "blob_pct", "art_3_pct", "art_5_pct", "art_11_pct"]

    def print_table(rows_, cols):
        header = " | ".join(f"{c:>13}" for c in cols)
        print(header)
        print("-" * len(header))
        for label, m in rows_:
            row = [label]
            for k in cols[1:]:
                v = m.get(k)
                row.append("nan" if v is None else f"{v:.5f}")
            print(" | ".join(f"{v:>13}" for v in row))

    rows = []
    for label, prefix in variants:
        path = find_exr(prefix)
        if not path:
            print(f"  [skip] {label}: no EXR found ({prefix})")
            continue
        m = metrics_for(path)
        if not m:
            print(f"  [skip] {label}: metric computation failed")
            continue
        rows.append((label, m))

    print("\n[linear-HDR luminance]")
    print_table(rows, cols_linear)
    print("\n[OkLab perceptual + worst-region]")
    print_table(rows, cols_oklab)


if __name__ == "__main__":
    main()

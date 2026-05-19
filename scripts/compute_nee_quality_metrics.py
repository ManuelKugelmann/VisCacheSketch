"""
compute_nee_quality_metrics.py — post-processing for compare_nee_quality.py.

Loads the captured EXRs and computes the full metric battery vs GT:
  Linear-luminance HDR (compute_research_metrics_hdr):
    rmse, psnr_db, relmse, smape, mape, ms_ssim, flip
  OkLab perceptual + artifact-region (compute_render_error_signed_hdr):
    err_pct        — mean OkLab(render,GT) as % of OkLab max
    blob_pct       — Gaussian-blurred worst-region OkLab err
    art_3/5/11_pct — median-filtered worst-region (kernel 3/5/11 px)

CLAUDE.md mandates the full battery (err%, art5%, RMSE, PSNR are the
minimum); single-metric analysis misses anti-correlated trade-offs.

Run from project root:
    runtime/pythondist/python.exe scripts/compute_nee_quality_metrics.py [scene_name]
"""

import os, sys, glob, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viscache_exr import compute_research_metrics_hdr, compute_render_error_signed_hdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = sys.argv[1] if len(sys.argv) > 1 else "CornellBox_32PointLights"
CAP_DIR = os.path.join(ROOT, "runtime", "captures", "nee_quality", SCENE)


def find_exr(prefix):
    matches = glob.glob(os.path.join(CAP_DIR, f"{prefix}.AccumulatePass.output.*.exr"))
    return sorted(matches)[-1] if matches else None


# Metric direction: which way is BETTER?
# Higher-is-better for psnr_db / ms_ssim; lower-is-better for everything else.
HIGHER_BETTER = {"psnr_db", "ms_ssim"}


def metric_better(name, delta):
    """delta = variant - vanilla. Returns True if variant is better."""
    return (delta > 0) if name in HIGHER_BETTER else (delta < 0)


def main():
    gt_matches = sorted(glob.glob(os.path.join(CAP_DIR, "gt_x*.AccumulatePass.output.*.exr")))
    if not gt_matches:
        print(f"[ERROR] no GT EXR in {CAP_DIR}", file=sys.stderr)
        sys.exit(1)
    gt = gt_matches[-1]
    print(f"[gt] {os.path.basename(gt)}")

    # Variant naming follows the project taxonomy: F## = fresh K-RIS count,
    # R2d = per-pixel reservoir (DI), R3d = world-space cell reservoir. _b1
    # marks single-bounce-only (matches DI's native primary-hit scope).
    #
    # Single-bounce trio (vanilla_b1, restirdi, nee_F16_b1) — like-for-like:
    #   - vanilla_b1   : K=1 NEE at primary hit, no resampling
    #   - restirdi     : F16 + R2d per-pixel + temporal + spatial + (optional pool)
    #   - nee_F16_b1   : pure F16 K-RIS at primary hit (NOT ReSTIR — no reuse)
    # The vanilla_b1 → restirdi gap shows what R2d-reuse buys on top of K-RIS;
    # the nee_F16_b1 → restirdi gap isolates that reuse machinery's value
    # since both have identical F16 fresh streams.
    #
    # Multi-bounce arms exercise F16 at every non-Delta vertex through
    # MAX_BOUNCES. nee_F16R3d adds 3D cell-reservoir reuse (identity-stream
    # merge); a proper "ReSTIR NEE = ReSTIR DI for multi-bounce" still needs
    # per-vertex temporal/spatial reuse with Bitterli weighted merge.
    variants = [("vanilla_b1",     "vanilla_b1_x4"),
                ("restirdi_F16R2d", "restirdi_F16R2d_x4"),
                ("nee_F16_b1",     "nee_F16_b1_x4"),
                ("vanilla",        "vanilla_x4"),
                ("nee_F16",        "nee_F16_x4"),
                ("nee_F16R3d",     "nee_F16R3d_x4")]

    vanilla_path = find_exr("vanilla_x4")

    # Combined per-variant dict: linear HDR + OkLab/artifact metrics.
    def metrics_for(path):
        m = compute_research_metrics_hdr(path, gt) or {}
        # OkLab + artifact battery — writes a debug PNG to a temp path we
        # don't need; we only want the returned dict.
        with tempfile.TemporaryDirectory() as td:
            out_png = os.path.join(td, "err.png")
            oklab = compute_render_error_signed_hdr(path, vanilla_path or path, gt, out_png)
        if oklab:
            m["err_pct"]    = oklab.get("err_delta_pct")
            m["blob_pct"]   = oklab.get("err_delta_blob_pct")
            m["art_3_pct"]  = oklab.get("err_artifact_3_pct")
            m["art_5_pct"]  = oklab.get("err_artifact_5_pct")
            m["art_11_pct"] = oklab.get("err_artifact_11_pct")
        return m

    print(f"\n=== quality comparison @ x4 SPP vs GT@x1024 — scene={SCENE} ===")
    # Two stacked tables — the linear-HDR row stays wide-readable, the
    # OkLab/artifact row carries the perceptual + worst-region story.
    cols_linear = ["variant", "rmse", "psnr_db", "relmse", "smape", "mape", "ms_ssim", "flip"]
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
            print(f"  [skip] {label}: no EXR found")
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

    # Per-variant verdict vs vanilla across the full battery — call out
    # anti-correlated metric disagreements explicitly.
    if len(rows) >= 2:
        print("\n[verdict vs vanilla]")
        vanilla = next((m for n, m in rows if n == "vanilla"), None)
        if vanilla is None:
            return
        verdict_keys = ("rmse", "psnr_db", "relmse", "smape", "ms_ssim", "flip",
                        "err_pct", "blob_pct", "art_5_pct")
        for name, m in rows:
            if name == "vanilla":
                continue
            wins = []
            losses = []
            for k in verdict_keys:
                vv, mv = vanilla.get(k), m.get(k)
                if vv is None or mv is None:
                    continue
                delta = mv - vv
                if metric_better(k, delta):
                    wins.append(k)
                else:
                    losses.append(k)
            n_w = len(wins); n_l = len(losses)
            print(f"  {name}: {n_w} better / {n_l} worse  (wins: {','.join(wins) or '—'};  losses: {','.join(losses) or '—'})")
            for k in verdict_keys:
                vv, mv = vanilla.get(k), m.get(k)
                if vv is None or mv is None:
                    continue
                delta = mv - vv
                tag = "BETTER" if metric_better(k, delta) else "WORSE "
                arrow = "UP" if k in HIGHER_BETTER else "DN"
                sign = "+" if delta >= 0 else ""
                print(f"    {k:>10} {tag} ({sign}{delta:.5f}, want {arrow})")


if __name__ == "__main__":
    main()
